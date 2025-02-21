import shutil
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar
from typing_extensions import TypeAlias, Unpack

from cookit import deep_merge
from cookit.pyd import type_dump_python, type_validate_json
from nonebot import logger

from nonebot_plugin_meme_stickers.sticker_pack.update import update_sticker_pack

from ..consts import CONFIG_FILENAME, MANIFEST_FILENAME, UPDATING_FLAG_FILENAME
from ..utils import dump_readable_model
from ..utils.file_source import ReqKwargs
from ..utils.operation import op_val_formatter
from .models import HubStickerPackInfo, StickerPackConfig, StickerPackManifest

PackStateChangedCb: TypeAlias = Callable[["StickerPack"], Any]
TC = TypeVar("TC", bound=PackStateChangedCb)


class StickerPack:
    def __init__(
        self,
        base_path: Path,
        state_change_callbacks: Optional[list[PackStateChangedCb]] = None,
        init_notify: bool = True,
    ):
        self.base_path = base_path
        self.state_change_callbacks = state_change_callbacks or []

        self._cached_merged_config: Optional[StickerPackConfig] = None
        self._ref_outdated = False

        self.reload_manifest(notify=False)
        self.reload_config(notify=False)

        if init_notify:
            self.call_callbacks()

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
    def deleted(self) -> bool:
        return not self.manifest_path.exists()

    @property
    def ref_outdated(self) -> bool:
        return self._ref_outdated

    @property
    def unavailable(self) -> bool:
        return (
            self.merged_config.disabled
            or self.ref_outdated
            or self.updating
            or self.deleted
        )

    def set_ref_outdated(self, notify: bool = True):
        self._ref_outdated = True
        if notify:
            self.call_callbacks()

    def add_callback(self, cb: TC) -> TC:
        self.state_change_callbacks.append(cb)
        return cb

    def call_callbacks(self):
        for cb in self.state_change_callbacks:
            cb(self)

    def reload_manifest(self, notify: bool = True):
        self.manifest = type_validate_json(
            StickerPackManifest,
            self.manifest_path.read_text("u8"),
        )
        if notify:
            self.call_callbacks()

    def reload_config(self, notify: bool = True):
        self._cached_merged_config = None
        if self.config_path.exists():
            self.config: StickerPackConfig = type_validate_json(
                StickerPackConfig,
                self.config_path.read_text("u8"),
            )
        else:
            self.config = StickerPackConfig()
            self.save_config(notify=False)
        if notify:
            self.call_callbacks()

    def reload(self, notify: bool = True):
        self.reload_manifest(notify=False)
        self.reload_config(notify=False)
        if notify:
            self.call_callbacks()

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

    def save_config(self, notify: bool = True):
        self._cached_merged_config = None
        (self.base_path / CONFIG_FILENAME).write_text(
            dump_readable_model(self.config, exclude_unset=True),
        )
        if notify:
            self.call_callbacks()

    def save_manifest(self, notify: bool = True):
        (self.base_path / MANIFEST_FILENAME).write_text(
            dump_readable_model(self.manifest, exclude_unset=True),
        )
        if notify:
            self.call_callbacks()

    def save(self, notify: bool = True):
        self.save_config(notify=False)
        self.save_manifest(notify=False)
        if notify:
            self.call_callbacks()

    async def update(
        self,
        manifest: Optional[StickerPackManifest] = None,
        notify: bool = True,
        **req_kw: Unpack[ReqKwargs],
    ):
        s = self.merged_config.update_source
        if not s:
            raise NotImplementedError("This pack has no update source")
        await update_sticker_pack(
            self.base_path,
            s,
            manifest,
            self.call_callbacks if notify else None,
            **req_kw,
        )
        self.reload(notify=False)
        if notify:
            self.call_callbacks()

    def delete(self, notify: bool = True):
        self.manifest_path.unlink()
        if notify:
            self.call_callbacks()
        shutil.rmtree(
            self.base_path,
            ignore_errors=True,
            onerror=lambda _, f, e: logger.warning(
                f"Failed to delete `{f}`: {type(e).__name__}: {e}",
            ),
        )
        logger.info(f"Deleted pack `{self.slug}`")


op_val_formatter(StickerPack)(lambda it: f"[{it.slug}] {it.manifest.name}")
