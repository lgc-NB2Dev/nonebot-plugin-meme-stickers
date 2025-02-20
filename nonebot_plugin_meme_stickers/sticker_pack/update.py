import asyncio
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from typing_extensions import Unpack

from nonebot import logger

from ..consts import CONFIG_FILENAME, MANIFEST_FILENAME, UPDATING_FLAG_FILENAME
from ..utils import calc_checksum_from_file
from ..utils.file_source import (
    FileSource,
    ReqKwargs,
    create_client,
    create_req_sem,
    fetch_source,
)
from .hub import fetch_manifest, fetch_optional_checksum
from .models import StickerPackManifest
from .pack import StickerPack


def collect_manifest_files(manifest: StickerPackManifest) -> list[str]:
    files: list[str] = []
    if manifest.external_fonts:
        files.extend(x.path for x in manifest.external_fonts)
    if manifest.default_sticker_params.base_image:
        files.append(manifest.default_sticker_params.base_image)
    grid = manifest.sticker_grid
    files.extend(
        x
        for x in (
            grid.default_params.background,
            grid.category_override_params.background,
            *(x.background for x in grid.stickers_override_params.values()),
        )
        if isinstance(x, str)
    )
    files.extend(img for x in manifest.stickers if (img := x.params.base_image))
    return files


def collect_local_files(path: Path) -> list[str]:
    ignored_paths = {
        (path / x)
        for x in {
            MANIFEST_FILENAME,
            # CHECKSUM_FILENAME,  # we don't save this in local
            CONFIG_FILENAME,
        }
    }
    return [
        x.relative_to(path).as_posix()
        for x in path.rglob("*")
        if x.is_file() and x not in ignored_paths
    ]


# TODO refactor sticker pack manage, improve pack state change event emit
async def update_sticker_pack(
    pack_path: Path,
    source: FileSource,
    manifest: Optional[StickerPackManifest] = None,
    **req_kw: Unpack[ReqKwargs],
) -> StickerPack:
    slug = pack_path.name

    if (pack_path / UPDATING_FLAG_FILENAME).exists():
        raise RuntimeError(f"Pack `{slug}` is updating")

    if "cli" not in req_kw:
        req_kw["cli"] = create_client()

    if manifest is None:
        logger.debug(f"Fetching manifest of pack `{slug}`")
        manifest = await fetch_manifest(source, **req_kw)

    logger.debug(f"Fetching resource file checksums of pack `{slug}`")
    checksum = await fetch_optional_checksum(source, **req_kw)

    logger.debug(f"Collecting files need to update for pack `{slug}`")
    local_files = collect_local_files(pack_path) if pack_path.exists() else []
    remote_files = collect_manifest_files(manifest)

    # collect files should be downloaded
    local_files_set = set(local_files)
    remote_files_set = set(remote_files)

    # 1. files that are not exist in local
    files_should_download = remote_files_set - local_files_set

    # 2. files both exists in local and remote,
    #    but checksum not match, or not exist in remote checksum
    file_both_exist = set(local_files) & set(remote_files)
    if checksum:
        both_exist_checksum = {
            x: calc_checksum_from_file(pack_path / x) for x in file_both_exist
        }
        files_should_download.update(
            x for x, c in both_exist_checksum.items() if checksum.get(x) != c
        )
    else:
        files_should_download.update(file_both_exist)

    download_total = len(files_should_download)

    @contextmanager
    def update_flag_file_ctx():
        if not pack_path.exists():
            pack_path.mkdir(parents=True, exist_ok=True)
        flag_path = pack_path / UPDATING_FLAG_FILENAME
        flag_path.touch()
        yield
        flag_path.unlink()

    async def do_update(tmp_dir_path: Path):
        if "sem" not in req_kw:
            req_kw["sem"] = create_req_sem()

        downloaded_count = 0

        async def download(path: str):
            nonlocal downloaded_count
            r = await fetch_source(source, path, **req_kw)
            p = tmp_dir_path / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(r.content)
            downloaded_count += 1
            is_info = downloaded_count % 10 == 0 or (
                downloaded_count in (1, download_total)
            )
            logger.log(
                "INFO" if is_info else "DEBUG",
                (
                    f"[{downloaded_count} / {download_total}] "
                    f"Downloaded of pack `{slug}`: {path}"
                ),
            )

        await asyncio.gather(*(download(x) for x in files_should_download))

        logger.info(f"Moving downloaded files to data dir of pack `{slug}`")
        for path in files_should_download:
            src_p = tmp_dir_path / path
            dst_p = pack_path / path
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src_p, dst_p)

    with update_flag_file_ctx():
        if not download_total:
            logger.info(f"No files need to update for pack `{slug}`")
        else:
            logger.info(
                f"Pack `{slug}`"
                f" collected {download_total} files will update from remote,"
                f" downloading to temp dir",
            )
            with TemporaryDirectory() as tmp_dir:
                await do_update(Path(tmp_dir))

        # collect files should remove from local
        files_should_remove = local_files_set - remote_files_set
        if files_should_remove:
            logger.info(
                f"Removing {len(files_should_remove)} not needed files"
                f" from pack `{slug}`",
            )
            for path in files_should_remove:
                (pack_path / path).unlink()

        # remove empty folders
        empty_folders = tuple(
            p for p in pack_path.rglob("*") if p.is_dir() and not any(p.iterdir())
        )
        if empty_folders:
            logger.info(
                f"Removing {len(empty_folders)} empty folders from pack `{slug}`",
            )
            for p in empty_folders:
                p.rmdir()

        logger.debug(f"Updating manifest and config of pack `{slug}`")
        pack = StickerPack(
            base_path=pack_path,
            init_manifest=manifest,
        )
        pack.config.update_source = source
        pack.save_config()

    external_fonts_updated = {
        x.path for x in manifest.external_fonts if x.path in files_should_download
    }
    if external_fonts_updated:
        logger.warning(f"Pack `{slug}` updated these external font(s):")
        for x in external_fonts_updated:
            logger.warning(f"  - {(pack_path / x).resolve()}")
        logger.warning(
            "Don't forget to install them into system then restart bot to use!",
        )
        logger.warning(
            f"贴纸包 `{slug}` 更新了如上额外字体文件，"
            f"请不要忘记安装这些字体文件到系统中，然后重启 Bot 以正常使用本插件功能！",
        )

    logger.info(f"Successfully updated pack `{slug}`")
    return pack
