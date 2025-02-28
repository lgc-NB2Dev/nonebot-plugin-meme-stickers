import asyncio
import shutil
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Optional
from typing_extensions import Unpack

from cookit.pyd import type_validate_json
from nonebot import logger

from ..consts import CONFIG_FILENAME, MANIFEST_FILENAME, UPDATING_FLAG_FILENAME
from ..utils import calc_checksum_from_file, dump_readable_model
from ..utils.file_source import (
    FileSource,
    ReqKwargs,
    fetch_source,
    with_kw_cli,
    with_kw_sem,
)
from .hub import fetch_manifest, fetch_optional_checksum
from .models import StickerPackConfig, StickerPackManifest


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


@dataclass
class UpdatedResourcesInfo:
    assets: set[str]
    fonts: set[str]


async def update_sticker_pack(
    pack_path: Path,
    source: FileSource,
    manifest: Optional[StickerPackManifest] = None,
    file_update_start_callback: Optional[Callable[[], Any]] = None,
    **req_kw: Unpack[ReqKwargs],
):
    slug = pack_path.name

    if (pack_path / UPDATING_FLAG_FILENAME).exists():
        raise RuntimeError(f"Pack `{slug}` is updating")

    if manifest is None:
        logger.debug(f"Fetching manifest of pack `{slug}`")
        manifest = await fetch_manifest(source, **req_kw)

    logger.debug(f"Fetching resource file checksums of pack `{slug}`")
    checksum = await fetch_optional_checksum(source, **req_kw)

    logger.debug(f"Collecting files need to update for pack `{slug}`")

    # collect files should be downloaded
    local_files = (
        set(collect_local_files(pack_path)) if pack_path.exists() else set[str]()
    )
    remote_files = set(collect_manifest_files(manifest))

    # 1. files that are not exist in local pack folder
    files_should_download = remote_files - local_files

    # 2. files not in local pack folder, but remote exists. (shared files)
    #    if these files exist in local, remove them from files_should_download
    exist_files_not_in_pack_dir = {
        x for x in files_should_download if (pack_path / x).exists()
    }
    files_should_download -= exist_files_not_in_pack_dir

    # 3. files both exists in local and remote,
    #    but checksum not match, or not exist in remote checksum
    file_both_exist = (
        # avoid editing local_files set
        # to avoid accidentally remove shared files using by other packs in next step
        {*local_files, *exist_files_not_in_pack_dir} & remote_files
    )
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
    downloaded_count = 0

    async def download(base: Path, path: str):
        nonlocal downloaded_count
        r = await fetch_source(source, path, **req_kw)
        p = base / path
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

    @contextmanager
    def file_updating_ctx():
        pack_path.mkdir(parents=True, exist_ok=True)
        flag_path = pack_path / UPDATING_FLAG_FILENAME
        flag_path.touch()
        if file_update_start_callback:
            file_update_start_callback()
        try:
            yield
        finally:
            flag_path.unlink()

    def move_files(tmp_dir: Path):
        for path in files_should_download:
            src_p = tmp_dir / path
            dst_p = pack_path / path
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src_p, dst_p)

    def after_ops():
        # collect files should remove from local
        files_should_remove = local_files - remote_files
        if files_should_remove:
            logger.info(
                f"Removing {len(files_should_remove)} not needed files from pack `{slug}`",
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
        (pack_path / MANIFEST_FILENAME).write_text(
            dump_readable_model(manifest, exclude_defaults=True, exclude_unset=True),
            "u8",
        )

        config_path = pack_path / CONFIG_FILENAME
        config = (
            type_validate_json(StickerPackConfig, config_path.read_text("u8"))
            if config_path.exists()
            else StickerPackConfig()
        )
        config.update_source = source
        config_path.write_text(
            dump_readable_model(config, exclude_unset=True),
            "u8",
        )

    tmp_dir_ctx = TemporaryDirectory() if download_total else nullcontext()
    with tmp_dir_ctx as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str) if tmp_dir_str else None

        if tmp_dir:
            logger.info(
                f"Pack `{slug}`"
                f" collected {download_total} files will update from remote,"
                f" downloading to temp dir",
            )
            async with with_kw_cli(req_kw), with_kw_sem(req_kw):
                await asyncio.gather(
                    *(download(tmp_dir, x) for x in files_should_download),
                )
        else:
            logger.info(f"No files need to update for pack `{slug}`")

        with file_updating_ctx():
            if tmp_dir:
                logger.info(f"Moving downloaded files to data dir of pack `{slug}`")
                move_files(tmp_dir)
            after_ops()

    external_fonts_updated = {
        x.path for x in manifest.external_fonts if x.path in files_should_download
    }
    if external_fonts_updated:
        logger.warning(f"Base path: {pack_path}")
        logger.warning(f"Pack `{slug}` updated with the following external font(s).")
        logger.warning(f"贴纸包 `{slug}` 更新了如下额外字体文件，")
        logger.warning(
            "Don't forget to install them into system then restart bot to use!",
        )
        logger.warning(
            "请不要忘记安装这些字体文件到系统中，然后重启 Bot 以正常使用本插件功能！",
        )
        for x in external_fonts_updated:
            logger.warning(f"  - {x}")

    logger.info(f"Successfully updated pack `{slug}`")
    return UpdatedResourcesInfo(
        assets=files_should_download - external_fonts_updated,
        fonts=external_fonts_updated,
    )
