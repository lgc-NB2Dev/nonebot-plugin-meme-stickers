from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, Union
from typing_extensions import TypeAlias, Unpack

from cookit.loguru import warning_suppress
from nonebot import logger

from ..consts import MANIFEST_FILENAME, UPDATING_FLAG_FILENAME
from ..utils.file_source import FileSource, ReqKwargs
from ..utils.operation import OpInfo, OpIt
from .models import StickerPackManifest
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
        if pack.deleted:
            self.packs.remove(pack)
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
        return p

    def reload(self, clear_updating_flags: bool = False):
        for x in self.packs:
            x.set_ref_outdated()
        self.packs.clear()

        op_info = OpInfo[Union[str, StickerPack]]()

        if not self.base_path.exists():
            logger.info("Data dir not exist, skip load")
            return op_info
            # self.base_path.mkdir(parents=True)

        slugs = (
            x.name
            for x in self.base_path.iterdir()
            if x.is_dir() and (x / MANIFEST_FILENAME).exists()
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
                logger.debug(f"Successfully loaded pack `{slug}`")

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
        return self.find_pack_with_checker(
            lambda x: x.slug.lower() == query or x.manifest.name.lower() == query,
            include_unavailable,
        )

    async def install(
        self,
        slug: str,
        source: FileSource,
        manifest: Optional[StickerPackManifest] = None,
        **req_kw: Unpack[ReqKwargs],
    ) -> tuple[StickerPack, UpdatedResourcesInfo]:
        if self.find_pack_by_slug(slug):
            raise ValueError(f"Pack `{slug}` already loaded")
        pack_path = self.base_path / slug
        res = await update_sticker_pack(pack_path, source, manifest, **req_kw)
        pack = self.load_pack(slug)
        return pack, res
