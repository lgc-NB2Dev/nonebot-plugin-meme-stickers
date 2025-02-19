import asyncio
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, Union
from typing_extensions import TypeAlias

from cookit.loguru import warning_suppress
from nonebot import logger

from ..consts import MANIFEST_FILENAME, UPDATING_FLAG_FILENAME
from ..utils.file_source import create_req_sem
from ..utils.operation import OpInfo, OpIt
from .hub import fetch_hub, fetch_optional_manifest
from .models import HubManifest, StickerPackManifest
from .pack import StickerPack
from .update import update_sticker_pack

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

    def _call_reload_hooks(self):
        for x in self.reload_hooks:
            x(self)

    def reload(self, clear_updating_flags: bool = False):
        for x in self.packs:
            x.ref_outdated = True
        self.packs.clear()

        opt_info = OpInfo[str]()

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
                    opt_info.skipped.append(OpIt(path.name, "更新中"))
                    logger.info(f"Pack `{path.name}` is updating, skip load")
                    continue
                (path / UPDATING_FLAG_FILENAME).unlink()
                logger.warning(f"Cleared updating flag of pack `{path.name}`")

            try:
                self.packs.append(StickerPack(path))
            except Exception as e:
                opt_info.failed.append(OpIt(path.name, exc=e))
                with warning_suppress(f"Failed to load pack `{path.name}`"):
                    raise
            else:
                opt_info.succeed.append(OpIt(path.name))
                logger.debug(f"Successfully loaded pack `{path.name}`")

        logger.success(f"Successfully loaded {len(self.packs)} packs")
        self._call_reload_hooks()
        return opt_info

    def find_pack_with_checker(
        self,
        checker: Callable[[StickerPack], bool],
        include_unavailable: bool = False,
    ) -> Optional[StickerPack]:
        packs = self.packs if include_unavailable else self.available_packs
        return next((x for x in packs if checker(x)), None)

    def find_pack_by_slug(
        self,
        slug: str,
        include_unavailable: bool = False,
    ) -> Optional[StickerPack]:
        return self.find_pack_with_checker(
            lambda x: x.slug == slug,
            include_unavailable,
        )

    def find_pack(
        self,
        query: str,
        include_unavailable: bool = False,
    ) -> Optional[StickerPack]:
        query = query.lower()
        return self.find_pack_with_checker(
            lambda x: x.slug.lower() == query or x.manifest.name.lower() == query,
            include_unavailable,
        )

    async def update(
        self,
        packs: Optional[Iterable[str]] = None,
        force: bool = False,
    ) -> OpInfo[str]:
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

        opt_info = OpInfo[str]()

        for p in will_update.copy():
            local_v = p.manifest.version
            if (not (m := manifests[p.slug])) or (
                (not force) and (m.version <= local_v)
            ):
                will_update.remove(p)
                opt_info.skipped.append(
                    OpIt(p.slug, "无须更新" if m else "获取贴纸包信息失败"),
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
                opt_info.failed.append(OpIt(p.slug, exc=e))
                with warning_suppress(f"Update sticker pack `{p.slug}` failed"):
                    raise
            else:
                opt_info.succeed.append(OpIt(p.slug))

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
    ) -> OpInfo:
        opt_info = OpInfo[str]()

        if hub is None:
            logger.info("Fetching hub manifest")
            hub = await fetch_hub()

        sem = create_req_sem()

        async def ins(slug: str):
            if (self.base_path / slug).exists():
                logger.warning("Pack `{slug}` already exists")
                opt_info.failed.append(OpIt(slug, "贴纸包已存在"))
                return

            info = next((x for x in hub if x.slug == slug), None)
            if info is None:
                logger.warning("Pack `{slug}` not found in hub")
                opt_info.failed.append(OpIt(slug, "未在 Hub 中找到对应贴纸包"))
                return

            try:
                await update_sticker_pack(
                    self.base_path / slug,
                    info.source,
                    manifests[slug] if manifests else None,
                    sem=sem,
                )
            except Exception as e:
                opt_info.failed.append(OpIt(slug, exc=e))
                with warning_suppress(f"Install sticker pack `{slug}` failed"):
                    raise
            else:
                opt_info.succeed.append(OpIt(slug))

        logger.info(f"Installing sticker packs: {', '.join(packs)}")
        await asyncio.gather(*(ins(x) for x in packs))
        logger.info(
            f"Install finished,"
            f" {len(opt_info.succeed)} succeed, {len(opt_info.failed)} failed",
        )
        self.reload()
        return opt_info

    def delete(self, pack: StickerPack):
        pack.ref_outdated = True
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
