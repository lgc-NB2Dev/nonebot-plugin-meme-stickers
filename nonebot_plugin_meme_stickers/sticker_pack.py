import asyncio
import hashlib
import json
import shutil
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Generic, NamedTuple, Optional, TypeVar, Union
from typing_extensions import TypeAlias, Unpack

from cookit import deep_merge
from cookit.loguru import warning_suppress
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
    StickerPackManifest,
    StickersHubFileSource,
)
from .source_fetch import (
    ReqKwargs,
    create_client,
    create_req_sem,
    fetch_github_source,
    fetch_source,
)

T = TypeVar("T")
T2 = TypeVar("T2")


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

        self._cached_merged_config: Optional[StickerPackConfig] = None

    @cached_property
    def slug(self) -> str:
        return self.base_path.name

    @cached_property
    def manifest_path(self):
        return self.base_path / MANIFEST_FILENAME

    @cached_property
    def config_path(self):
        return self.base_path / CONFIG_FILENAME

    @cached_property
    def hub_manifest_info(self) -> Optional[HubStickerPackInfo]:
        if not (s := self.merged_config.update_source):
            return None
        return HubStickerPackInfo(slug=self.slug, source=s)

    @property
    def updating(self) -> bool:
        return (self.base_path / UPDATING_FLAG_FILENAME).exists()

    @property
    def unavailable(self) -> bool:
        return self.merged_config.disabled or self.updating

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
    def merged_config(self) -> StickerPackConfig:
        """
        remember to call `save_config` or `update_config` after modified config,
        merged_config cache will clear after these operations
        """
        if not self._cached_merged_config:
            self._cached_merged_config = StickerPackConfig(
                **deep_merge(
                    type_dump_python(self.manifest.default_config, exclude_unset=True),
                    type_dump_python(self.config, exclude_unset=True),
                    skip_merge_paths={"commands"},
                ),
            )
        return self._cached_merged_config

    def save_config(self):
        self._cached_merged_config = None
        (self.base_path / CONFIG_FILENAME).write_text(
            dump_readable_model(self.config, exclude_unset=True),
        )

    def save_manifest(self):
        (self.base_path / MANIFEST_FILENAME).write_text(
            dump_readable_model(self.manifest, exclude_unset=True),
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
        req_kw["sem"] = create_req_sem()

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
            manifest_init=manifest,
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


class ValueWithReason(NamedTuple, Generic[T, T2]):
    value: T
    info: T2


@dataclass
class StickerPackOperationInfo(Generic[T]):
    succeed: list[T] = field(default_factory=list)
    failed: list[ValueWithReason[T, BaseException]] = field(default_factory=list)
    skipped: list[ValueWithReason[T, str]] = field(default_factory=list)


ManagerReloadHook: TypeAlias = Callable[["StickerPackManager"], Any]
TMH = TypeVar("TMH", bound=ManagerReloadHook)


class StickerPackManager:
    def __init__(
        self,
        base_path: Path,
        reload_hooks: Union[
            ManagerReloadHook,
            Iterable[ManagerReloadHook],
            None,
        ] = None,
        init_auto_load: bool = False,
        init_load_clear_updating_flags: bool = False,
    ) -> None:
        self.base_path = base_path
        self.packs: list[StickerPack] = []
        self.reload_hooks: list[ManagerReloadHook] = (
            []
            if reload_hooks is None
            else ([reload_hooks] if callable(reload_hooks) else list(reload_hooks))
        )
        if init_auto_load:
            self.reload(init_load_clear_updating_flags)

    @property
    def available_packs(self) -> list[StickerPack]:
        return [x for x in self.packs if not x.unavailable]

    def register_reload_hook(self, func: TMH) -> TMH:
        self.reload_hooks.append(func)
        return func

    def reload(self, clear_updating_flags: bool = False):
        self.packs.clear()

        opt_info = StickerPackOperationInfo[str]()

        if not self.base_path.exists():
            logger.info("Data dir not exist, skip load")
            return opt_info
            # self.base_path.mkdir(parents=True)

        paths = (
            self.base_path / x
            for x in self.base_path.iterdir()
            if x.is_dir() and (x / MANIFEST_FILENAME).exists()
        )

        for path in paths:
            if (path / UPDATING_FLAG_FILENAME).exists():
                if not clear_updating_flags:
                    opt_info.skipped.append(ValueWithReason(path.name, "更新中"))
                    logger.info(f"Pack `{path.name}` is updating, skip load")
                    continue
                (path / UPDATING_FLAG_FILENAME).unlink()
                logger.warning(f"Cleared updating flag of pack `{path.name}`")

            try:
                self.packs.append(StickerPack(path))
            except Exception as e:
                opt_info.failed.append(ValueWithReason(path.name, e))
                with warning_suppress(f"Failed to load pack `{path.name}`"):
                    raise
            else:
                opt_info.succeed.append(path.name)
                logger.debug(f"Successfully loaded pack `{path.name}`")

        logger.success(f"Successfully loaded {len(self.packs)} packs")
        return opt_info

    def find_pack_by_slug(
        self,
        slug: str,
        include_unavailable: bool = False,
    ) -> Optional[StickerPack]:
        return next(
            (
                x
                for x in (self.packs if include_unavailable else self.available_packs)
                if x.slug == slug
            ),
            None,
        )

    def find_pack(
        self,
        query: str,
        include_unavailable: bool = False,
    ) -> Optional[StickerPack]:
        query = query.lower()
        return next(
            (
                x
                for x in (self.packs if include_unavailable else self.available_packs)
                if x.slug == query or x.manifest.name.lower() == query
            ),
            None,
        )

    async def update(
        self,
        packs: Optional[Iterable[str]] = None,
        force: bool = False,
    ) -> StickerPackOperationInfo:
        logger.info("Collecting sticker packs need to update")

        sem = create_req_sem()

        will_update = [
            x
            for x in self.packs
            if (
                ((packs is None) or (x.slug in packs))
                and x.merged_config.update_source
                and (not x.updating)
            )
        ]

        async def fetch_manifest(p: StickerPack):
            assert p.merged_config.update_source
            return (
                p.slug,
                await fetch_optional_manifest(p.merged_config.update_source, sem=sem),
            )

        manifests = dict(
            await asyncio.gather(*(fetch_manifest(x) for x in will_update)),
        )

        opt_info = StickerPackOperationInfo[str]()

        for p in will_update.copy():
            local_v = p.manifest.version
            if (not (m := manifests[p.slug])) or (
                (not force) and (m.version <= local_v)
            ):
                will_update.remove(p)
                opt_info.skipped.append(
                    ValueWithReason(p.slug, "无须更新" if m else "获取贴纸包信息失败"),
                )
                logger.debug(
                    f"Skip update sticker pack `{p.slug}`"
                    f" (local ver {local_v}, remote ver {m.version if m else 'Unknown'})",
                )

        if not will_update:
            logger.info("No sticker pack need to update")
            return opt_info

        # for p in will_update:
        #     self.packs.remove(p)

        async def up(p: StickerPack):
            assert p.merged_config.update_source

            try:
                await update_sticker_pack(
                    self.base_path / p.slug,
                    p.merged_config.update_source,
                    manifests[p.slug],
                    sem=sem,
                )
            except Exception as e:
                opt_info.failed.append(ValueWithReason(p.slug, e))
                with warning_suppress(f"Update sticker pack `{p.slug}` failed"):
                    raise
            else:
                opt_info.succeed.append(p.slug)

        logger.info(
            f"Updating {len(will_update)} sticker packs"
            f": {', '.join(x.slug for x in will_update)}",
        )
        await asyncio.gather(*(up(x) for x in will_update))
        logger.info(
            f"Update finished,"
            f" {len(opt_info.succeed)} succeed, {len(opt_info.failed)} failed",
        )
        self.reload()

        return opt_info

    async def install(
        self,
        packs: Iterable[str],
        hub: Optional[HubManifest] = None,
        manifests: Optional[dict[str, StickerPackManifest]] = None,
    ) -> StickerPackOperationInfo:
        opt_info = StickerPackOperationInfo[str]()

        if hub is None:
            logger.info("Fetching hub manifest")
            hub = await fetch_hub()

        sem = create_req_sem()

        async def ins(slug: str):
            if (self.base_path / slug).exists():
                logger.warning("Pack `{slug}` already exists")
                opt_info.failed.append(
                    ValueWithReason(slug, RuntimeError("贴纸包已存在")),
                )
                return

            info = next((x for x in hub if x.slug == slug), None)
            if info is None:
                logger.warning("Pack `{slug}` not found in hub")
                opt_info.failed.append(
                    ValueWithReason(slug, RuntimeError("未在 Hub 中找到对应贴纸包")),
                )
                return

            try:
                await update_sticker_pack(
                    self.base_path / slug,
                    info.source,
                    manifests[slug] if manifests else None,
                    sem=sem,
                )
            except Exception as e:
                opt_info.failed.append(ValueWithReason(slug, e))
                with warning_suppress(f"Install sticker pack `{slug}` failed"):
                    raise
            else:
                opt_info.succeed.append(slug)

        logger.info(f"Installing sticker packs: {', '.join(packs)}")
        await asyncio.gather(*(ins(x) for x in packs))
        logger.info(
            f"Install finished,"
            f" {len(opt_info.succeed)} succeed, {len(opt_info.failed)} failed",
        )
        self.reload()
        return opt_info

    def delete(self, pack: StickerPack):
        self.packs.remove(pack)
        shutil.rmtree(
            pack.base_path,
            ignore_errors=True,
            onerror=lambda _, f, e: logger.warning(
                f"Failed to delete `{f}`: {type(e).__name__}: {e}",
            ),
        )
        logger.info(f"Deleted pack `{pack.slug}`")
        self.reload()


pack_manager = StickerPackManager(config.data_dir)
