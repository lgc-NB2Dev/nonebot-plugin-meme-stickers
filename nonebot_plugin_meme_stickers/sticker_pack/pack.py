from functools import cached_property
from pathlib import Path
from typing import Optional

from cookit import deep_merge
from cookit.pyd import type_dump_python, type_validate_json

from ..consts import CONFIG_FILENAME, MANIFEST_FILENAME, UPDATING_FLAG_FILENAME
from ..utils import dump_readable_model
from ..utils.operation import op_val_formatter
from .models import HubStickerPackInfo, StickerPackConfig, StickerPackManifest


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

        self.ref_outdated = False
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
        return self.merged_config.disabled or self.updating or self.ref_outdated

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


op_val_formatter(StickerPack)(lambda it: f"[{it.slug}] {it.manifest.name}")
