import asyncio
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, Union
from typing_extensions import TypeAlias, Unpack

from cookit import nullcontext
from cookit.loguru import warning_suppress
from nonebot import logger

from ..consts import MANIFEST_FILENAME, UPDATING_FLAG_FILENAME
from ..utils.file_source import ReqKwargs, create_req_sem
from ..utils.operation import OpInfo, OpIt
from .models import HubStickerPackInfo, StickerPackManifest
from .pack import StickerPack
from .update import UpdatedResourcesInfo, update_sticker_pack

PackStateChangedCbFromManager: TypeAlias = Callable[
    ["StickerPackManager", StickerPack],
    Any,
]
TC = TypeVar("TC", bound=PackStateChangedCbFromManager)


class StickerPackManager:
    def __init__(
        self,
        base_path: Path,
        init_auto_load: bool = False,
        init_load_clear_updating_flags: bool = False,
        state_change_callbacks: Optional[list[PackStateChangedCbFromManager]] = None,
    ) -> None:
        self.base_path = base_path
        self.packs: list[StickerPack] = []
        self.state_change_callbacks = state_change_callbacks or []
        if init_auto_load:
            self.reload(init_load_clear_updating_flags)

    @property
    def available_packs(self) -> list[StickerPack]:
        return [x for x in self.packs if not x.unavailable]

    def add_callback(self, func: TC) -> TC:
        self.state_change_callbacks.append(func)
        return func

    def wrapped_call_callbacks(self, pack: StickerPack) -> None:
        if pack.ref_outdated or pack.deleted:
            self.packs.remove(pack)
            logger.debug(f"Unloaded pack `{pack.slug}`")
        for cb in self.state_change_callbacks:
            cb(self, pack)

    def load_pack(self, slug: str, clear_updating_flags: bool = False) -> StickerPack:
        path = self.base_path / slug

        if (path / UPDATING_FLAG_FILENAME).exists() and clear_updating_flags:
            (path / UPDATING_FLAG_FILENAME).unlink()
            logger.warning(f"Cleared updating flag of pack `{path.name}`")

        p = StickerPack(
            path,
            state_change_callbacks=[self.wrapped_call_callbacks],
        )
        self.packs.append(p)
        logger.debug(f"Loaded pack `{slug}`")
        return p

    def reload(self, clear_updating_flags: bool = False):
        logger.debug("Unloading packs")
        for x in self.packs.copy():
            x.set_ref_outdated()

        op_info = OpInfo[Union[str, StickerPack]]()

        if not self.base_path.exists():
            logger.info("Data dir not exist, skip load")
            return op_info
            # self.base_path.mkdir(parents=True)

        logger.info("Reloading packs")
        slugs = (
            x.name
            for x in self.base_path.iterdir()
            if (
                x.is_dir()
                and (not x.name.startswith("_"))
                and (x / MANIFEST_FILENAME).exists()
            )
        )
        for slug in slugs:
            try:
                p = self.load_pack(slug, clear_updating_flags)
            except Exception as e:
                op_info.failed.append(OpIt(slug, exc=e))
                with warning_suppress(f"Failed to load pack `{slug}`"):
                    raise
            else:
                op_info.succeed.append(OpIt(p))

        logger.success(f"Successfully loaded {len(self.packs)} packs")
        return op_info

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
        packs = self.packs if include_unavailable else self.available_packs
        if query.isdigit() and 1 <= (x := int(query)) <= len(packs):
            return packs[x - 1]
        return self.find_pack_with_checker(
            lambda x: x.slug.lower() == query or x.manifest.name.lower() == query,
            include_unavailable,
        )

    async def install(
        self,
        infos: list[HubStickerPackInfo],
        manifest: Optional[StickerPackManifest] = None,
        **req_kw: Unpack[ReqKwargs],
    ) -> tuple[OpInfo[Union[StickerPack, str]], dict[str, UpdatedResourcesInfo]]:
        if p := next((self.find_pack_by_slug(x.slug) for x in infos), None):
            raise ValueError(f"Pack `{p.slug}` already loaded")

        op_info = OpInfo[Union[StickerPack, str]]()

        async def do_install(info: HubStickerPackInfo):
            pack_path = self.base_path / info.slug
            try:
                res = await update_sticker_pack(
                    pack_path,
                    info.source,
                    manifest,
                    **req_kw,
                )
                pack = self.load_pack(info.slug)
            except Exception as e:
                op_info.failed.append(OpIt(info.slug, exc=e))
                with warning_suppress(f"Failed to install pack `{info.slug}`"):
                    raise
            else:
                op_info.succeed.append(OpIt(pack))
            return res

        # restrict install concurrency **counted by packs**
        sem = nullcontext() if req_kw.get("sem") else create_req_sem()

        async def with_sem_install(info: HubStickerPackInfo):
            async with sem:
                return await do_install(info)

        res = await asyncio.gather(*(with_sem_install(x) for x in infos))
        return op_info, {p.slug: v for p, v in zip(infos, res)}

    async def update_all(self, force: bool = False, **req_kw: Unpack[ReqKwargs]):
        return await update_packs(self.packs, force=force, **req_kw)


async def update_packs(
    packs: list[StickerPack],
    force: bool = False,
    **req_kw: Unpack[ReqKwargs],
) -> tuple[OpInfo[StickerPack], dict[str, UpdatedResourcesInfo]]:
    op_info = OpInfo[StickerPack]()

    async def update(p: StickerPack):
        if p.deleted:
            p.set_ref_outdated()
            logger.warning(f"Found loaded pack `{p.slug}` has been manually deleted!!!")
            return None

        if p.updating:
            op_info.skipped.append(OpIt(p, "已在更新中"))
            logger.warning(f"Pack `{p.slug}` is updating, skip")
            return None

        try:
            r = await p.update(force=force, **req_kw)
        except NotImplementedError:
            op_info.skipped.append(OpIt(p, "无更新源"))
            logger.warning(f"Pack `{p.slug}` has no update source, skip")
            return None
        except Exception as e:
            op_info.failed.append(OpIt(p, exc=e))
            with warning_suppress(f"Failed to update pack `{p.slug}`"):
                raise
        else:
            if r:
                op_info.succeed.append(OpIt(p))
            else:
                op_info.skipped.append(OpIt(p, "无须更新"))
            return r

    # restrict update concurrency **counted by packs**
    sem = nullcontext() if req_kw.get("sem") else create_req_sem()

    async def with_sem_update(p: StickerPack):
        async with sem:
            return await update(p)

    res = await asyncio.gather(*(with_sem_update(p) for p in packs.copy()))
    updated_info = {p.slug: v for p, v in zip(packs, res) if v}
    return op_info, updated_info
