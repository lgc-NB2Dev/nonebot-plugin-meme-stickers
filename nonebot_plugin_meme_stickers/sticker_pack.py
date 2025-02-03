import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from typing_extensions import Unpack

from cookit.loguru import warning_suppress
from cookit.pyd import type_dump_python, type_validate_json
from nonebot import logger

from .config import config
from .models import (
    CHECKSUM_FILENAME,
    CONFIG_FILENAME,
    MANIFEST_FILENAME,
    ChecksumDict,
    FileSource,
    HubManifest,
    HubStickerPackInfo,
    StickerPackConfig,
    StickerPackManifest,
    StickersHubFileSource,
)
from .source_fetch import (
    ReqKwargs,
    create_client,
    fetch_github_source,
    fetch_source,
    global_req_sem,
)


async def fetch_hub(**req_kw: Unpack[ReqKwargs]) -> HubManifest:
    return type_validate_json(
        HubManifest,
        (await fetch_github_source(StickersHubFileSource, **req_kw)).text,
    )


async def fetch_manifest(
    source: FileSource,
    **req_kw: Unpack[ReqKwargs],
) -> StickerPackManifest:
    return type_validate_json(
        StickerPackManifest,
        (await fetch_source(source, MANIFEST_FILENAME, **req_kw)).text,
    )


async def fetch_checksum(
    source: FileSource,
    **req_kw: Unpack[ReqKwargs],
) -> ChecksumDict:
    return type_validate_json(
        ChecksumDict,
        (await fetch_source(source, CHECKSUM_FILENAME, **req_kw)).text,
    )


async def fetch_hub_and_packs(
    **req_kw: Unpack[ReqKwargs],
) -> tuple[HubManifest, dict[str, StickerPackManifest]]:
    hub = await fetch_hub(**req_kw)

    async def fetch(source: FileSource) -> Optional[StickerPackManifest]:
        with warning_suppress(f"Failed to fetch manifest from {source}"):
            return await fetch_manifest(source, **req_kw)
        return None

    packs = await asyncio.gather(*(fetch(x.source) for x in hub))
    packs_dict = {h.slug: p for h, p in zip(hub, packs) if p is not None}
    return hub, packs_dict


def calc_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def calc_checksum_from_file(path: Path) -> str:
    return calc_checksum(path.read_bytes())


def collect_manifest_files(manifest: StickerPackManifest) -> list[str]:
    files: list[str] = []
    if manifest.default_sticker_params.base_image:
        files.append(manifest.default_sticker_params.base_image)
    for char in manifest.characters.values():
        files.extend(x.base_image for x in char if x.base_image)
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


def dump_readable_model(obj: object, **type_dump_kw) -> str:
    return json.dumps(
        type_dump_python(obj, **type_dump_kw),
        indent=2,
        ensure_ascii=False,
    )


async def update_sticker_pack(
    info: HubStickerPackInfo,
    manifest: Optional[StickerPackManifest] = None,
    **req_kw: Unpack[ReqKwargs],
):
    if "cli" not in req_kw:
        req_kw["cli"] = create_client()

    if manifest is None:
        logger.debug(f"Fetching manifest of pack `{info.slug}`")
        manifest = await fetch_manifest(info.source, **req_kw)

    checksum = {}
    logger.debug(f"Fetching resource file checksums of pack `{info.slug}`")
    with warning_suppress(f"Failed to fetch checksum from source {info.source}"):
        checksum = await fetch_checksum(info.source, **req_kw)

    logger.debug(f"Collecting files need to update for pack `{info.slug}`")
    base_path = config.meme_stickers_data_dir / info.slug
    local_files = collect_local_files(base_path) if base_path.exists() else []
    remote_files = collect_manifest_files(manifest)

    # collect files should be downloaded
    local_files_set = set(local_files)
    remote_files_set = set(remote_files)

    # 1. files that are not exist in local
    files_should_download = remote_files_set - local_files_set

    # 2. files both exists in local and remote,
    #    but checksum not match, or not exist in remote checksum
    file_both_exist = set(local_files) & set(remote_files)
    both_exist_checksum = {
        x: calc_checksum_from_file(base_path / x) for x in file_both_exist
    }
    files_should_download.update(
        x for x, c in both_exist_checksum.items() if checksum.get(x) != c
    )

    download_total = len(files_should_download)

    async def do_update(tmp_dir_path: Path):
        if "sem" not in req_kw:
            req_kw["sem"] = global_req_sem

        downloaded_count = 0

        async def download(path: str):
            nonlocal downloaded_count
            r = await fetch_source(info.source, path, **req_kw)
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
                    f"Downloaded of pack `{info.slug}`: {path}"
                ),
            )

        await asyncio.gather(*(download(x) for x in files_should_download))

        logger.info(f"Moving downloaded files to data dir of pack `{info.slug}`")
        for path in files_should_download:
            src_p = tmp_dir_path / path
            dst_p = base_path / path
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src_p, dst_p)

    if not download_total:
        logger.info(f"No files need to update for pack `{info.slug}`")
    else:
        logger.info(
            f"Pack `{info.slug}`"
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
            f" from pack `{info.slug}`",
        )
        for path in files_should_remove:
            (base_path / path).unlink()

    # remove empty folders
    empty_folders = tuple(
        p for p in base_path.rglob("*") if p.is_dir() and not any(p.iterdir())
    )
    if empty_folders:
        logger.info(
            f"Removing {len(empty_folders)} empty folders from pack `{info.slug}`",
        )
        for p in empty_folders:
            p.rmdir()

    logger.debug(f"Updating manifest and config of pack `{info.slug}`")

    # update manifest
    manifest_path = base_path / MANIFEST_FILENAME
    manifest_path.write_text(dump_readable_model(manifest, exclude_defaults=True))

    # update update_source from config
    config_path = base_path / CONFIG_FILENAME
    if not config_path.exists():
        config_data = StickerPackConfig()
    else:
        config_data = type_validate_json(
            StickerPackConfig,
            config_path.read_text("u8"),
        )
    config_data.update_source = info.source
    config_path.write_text(dump_readable_model(config_data))

    logger.info(f"Successfully updated pack `{info.slug}`")
