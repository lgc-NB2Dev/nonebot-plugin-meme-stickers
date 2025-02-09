import asyncio
import hashlib
import json
import shutil
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from typing_extensions import Unpack

from cookit import deep_merge
from cookit.loguru import warning_suppress
from cookit.loguru.common import logged_suppress
from cookit.pyd import type_dump_python, type_validate_json
from nonebot import logger

from .config import config
from .models import (
    CHECKSUM_FILENAME,
    CONFIG_FILENAME,
    MANIFEST_FILENAME,
    UPDATING_FLAG_FILENAME,
    ChecksumDict,
    FileSource,
    HubManifest,
    HubStickerPackInfo,
    StickerPackConfig,
    StickerPackConfigMerged,
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


class StickerPack:
    def __init__(
        self,
        base_path: Path,
        manifest_init: Optional[StickerPackManifest] = None,
        config_init: Optional[StickerPackConfig] = None,
    ):
        self.base_path = base_path
        if manifest_init:
            self.manifest = manifest_init
            self.save_manifest()
        else:
            self.reload_manifest()

        if config_init:
            self.config = config_init
            self.save_config()
        else:
            self.reload_config()

        self._cached_merged_config: Optional[StickerPackConfigMerged] = None

    @cached_property
    def manifest_path(self):
        return self.base_path / MANIFEST_FILENAME

    @cached_property
    def config_path(self):
        return self.base_path / CONFIG_FILENAME

    def reload_manifest(self):
        self.manifest = type_validate_json(
            StickerPackManifest,
            self.manifest_path.read_text("u8"),
        )

    def reload_config(self):
        self._cached_merged_config = None
        if self.config_path.exists():
            self.config: StickerPackConfig = type_validate_json(
                StickerPackConfig,
                self.config_path.read_text("u8"),
            )
        else:
            self.config = StickerPackConfig()
            self.save_config()

    def reload(self):
        self.reload_manifest()
        self.reload_config()

    @property
    def merged_config(self) -> StickerPackConfigMerged:
        """
        remember to call `save_config` or `update_config` after modified config,
        merged_config cache will clear after these operations
        """
        if not self._cached_merged_config:
            self._cached_merged_config = StickerPackConfigMerged(
                **deep_merge(
                    type_dump_python(
                        self.manifest.default_config,
                        exclude_defaults=True,
                        exclude_none=True,
                    ),
                    type_dump_python(
                        self.config,
                        exclude_defaults=True,
                        exclude_none=True,
                    ),
                ),
            )
        return self._cached_merged_config

    def save_config(self):
        self._cached_merged_config = None
        (self.base_path / CONFIG_FILENAME).write_text(
            dump_readable_model(self.config),
        )

    def save_manifest(self):
        (self.base_path / MANIFEST_FILENAME).write_text(
            dump_readable_model(self.manifest, exclude_defaults=True),
        )

    def save(self):
        self.save_config()
        self.save_manifest()


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


async def fetch_optional_manifest(
    source: FileSource,
    **req_kw: Unpack[ReqKwargs],
) -> Optional[StickerPackManifest]:
    with warning_suppress(f"Failed to fetch manifest from {source}"):
        return await fetch_manifest(source, **req_kw)
    return None


async def fetch_checksum(
    source: FileSource,
    **req_kw: Unpack[ReqKwargs],
) -> ChecksumDict:
    return type_validate_json(
        ChecksumDict,
        (await fetch_source(source, CHECKSUM_FILENAME, **req_kw)).text,
    )


async def fetch_optional_checksum(
    source: FileSource,
    **req_kw: Unpack[ReqKwargs],
) -> Optional[ChecksumDict]:
    with warning_suppress(f"Failed to fetch checksum from {source}"):
        return await fetch_checksum(source, **req_kw)
    return None


async def fetch_hub_and_packs(
    **req_kw: Unpack[ReqKwargs],
) -> tuple[HubManifest, dict[str, StickerPackManifest]]:
    if "sem" not in req_kw:
        req_kw["sem"] = global_req_sem

    hub = await fetch_hub(**req_kw)

    packs = await asyncio.gather(
        *(fetch_optional_manifest(x.source, **req_kw) for x in hub),
    )
    packs_dict = {h.slug: p for h, p in zip(hub, packs) if p is not None}
    return hub, packs_dict


def calc_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def calc_checksum_from_file(path: Path) -> str:
    return calc_checksum(path.read_bytes())


def collect_manifest_files(manifest: StickerPackManifest) -> list[str]:
    files: list[str] = []
    if manifest.external_fonts:
        files.extend(x.path for x in manifest.external_fonts)
    if manifest.default_sticker_params.base_image:
        files.append(manifest.default_sticker_params.base_image)
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
) -> StickerPack:
    base_path = config.meme_stickers_data_dir / info.slug
    if (base_path / UPDATING_FLAG_FILENAME).exists():
        raise RuntimeError(f"Pack `{info.slug}` is updating")

    if "cli" not in req_kw:
        req_kw["cli"] = create_client()

    if manifest is None:
        logger.debug(f"Fetching manifest of pack `{info.slug}`")
        manifest = await fetch_manifest(info.source, **req_kw)

    logger.debug(f"Fetching resource file checksums of pack `{info.slug}`")
    checksum = await fetch_optional_checksum(info.source, **req_kw)

    logger.debug(f"Collecting files need to update for pack `{info.slug}`")
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
    if checksum:
        both_exist_checksum = {
            x: calc_checksum_from_file(base_path / x) for x in file_both_exist
        }
        files_should_download.update(
            x for x, c in both_exist_checksum.items() if checksum.get(x) != c
        )
    else:
        files_should_download.update(file_both_exist)

    download_total = len(files_should_download)

    @contextmanager
    def update_flag_file_ctx():
        if not base_path.exists():
            base_path.mkdir(parents=True, exist_ok=True)
        flag_path = base_path / UPDATING_FLAG_FILENAME
        flag_path.touch()
        yield
        flag_path.unlink()

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

    with update_flag_file_ctx():
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
        pack = StickerPack(
            base_path=base_path,
            manifest_init=manifest,
        )
        pack.config.update_source = info.source
        pack.save_config()

    external_fonts_updated = {
        x.path for x in manifest.external_fonts if x.path in files_should_download
    }
    if external_fonts_updated:
        logger.warning(f"Pack `{info.slug}` updated these external font(s):")
        for x in external_fonts_updated:
            logger.warning(f"  - {(base_path / x).resolve()}")
        logger.warning(
            "Don't forget to install them into system then restart bot to use!",
        )
        logger.warning(
            f"贴纸包 `{info.slug}` 更新了如上额外字体文件，"
            f"请不要忘记安装这些字体文件到系统中，然后重启 Bot 以正常使用本插件功能！",
        )

    logger.info(f"Successfully updated pack `{info.slug}`")
    return pack


class StickerPackManager:
    def __init__(
        self,
        base_path: Path,
        init_clear_updating_flags: bool = False,
    ) -> None:
        self.base_path = base_path
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True)
        self.packs: dict[str, StickerPack] = {}
        self.reload(init_clear_updating_flags)

    def reload(self, clear_updating_flags: bool = False):
        self.packs.clear()
        paths = (
            self.base_path / x
            for x in self.base_path.iterdir()
            if x.is_dir() and (x / MANIFEST_FILENAME).exists()
        )

        for path in paths:
            if (path / UPDATING_FLAG_FILENAME).exists():
                if not clear_updating_flags:
                    logger.info(f"Pack `{path.name}` is updating, skip load")
                    continue
                (path / UPDATING_FLAG_FILENAME).unlink()
                logger.warning(f"Cleared updating flag of pack `{path.name}`")

            with warning_suppress(f"Failed to load pack `{path.name}`"):
                self.packs[path.name] = StickerPack(path)
                logger.debug(f"Successfully loaded pack `{path.name}`")

        logger.success(f"Successfully loaded {len(self.packs)} packs")

    async def update(self):
        logger.info("Collecting sticker packs need to update")
        update_packs_info = [
            HubStickerPackInfo(slug=k, source=s)
            for k, v in self.packs.items()
            if (
                (s := v.merged_config.update_source)
                and (not (v.base_path / UPDATING_FLAG_FILENAME).exists())
            )
        ]
        update_packs_manifest = await asyncio.gather(
            *(
                fetch_optional_manifest(x.source, sem=global_req_sem)
                for x in update_packs_info
            ),
        )
        packs_will_update: list[tuple[HubStickerPackInfo, StickerPackManifest]] = []
        for x, m in zip(update_packs_info, update_packs_manifest):
            local_v = self.packs[x.slug].manifest.version
            if m and local_v < m.version:
                packs_will_update.append((x, m))
            else:
                logger.debug(
                    f"Skip update sticker pack `{x.slug}`"
                    f" (local ver {local_v}, remote ver {m.version if m else 'Unknown'})",
                )

        for x in packs_will_update:
            del self.packs[x[0].slug]

        async def up(info: HubStickerPackInfo, manifest: StickerPackManifest) -> bool:
            with logged_suppress(f"Update sticker pack `{info.slug}` failed"):
                await update_sticker_pack(info, manifest, sem=global_req_sem)
                return True
            return False

        logger.info(f"Updating {len(packs_will_update)} sticker packs")
        results = await asyncio.gather(*(up(*x) for x in packs_will_update))
        true_count = sum(1 for x in results if x)
        false_count = len(results) - true_count
        logger.info(f"Update finished, {true_count} succeed, {false_count} failed")

        self.reload()


pack_manager = StickerPackManager(
    config.meme_stickers_data_dir,
    init_clear_updating_flags=True,
)
