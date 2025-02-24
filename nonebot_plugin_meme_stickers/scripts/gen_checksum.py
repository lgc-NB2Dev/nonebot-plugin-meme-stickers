from pathlib import Path

from nonebot import logger

from ..consts import CHECKSUM_FILENAME
from ..sticker_pack import pack_manager
from ..sticker_pack.models import StickerPackManifest
from ..sticker_pack.update import collect_manifest_files
from ..utils import calc_checksum_from_file, dump_readable_model


def calc_n_write_checksum(
    base_path: Path,
    manifest: StickerPackManifest,
) -> dict[str, str]:
    files = collect_manifest_files(manifest)
    checksums = [(f, calc_checksum_from_file(base_path / f)) for f in files]
    checksum_dict = dict(sorted(checksums, key=lambda x: x[0].split("/")))
    (base_path / CHECKSUM_FILENAME).write_text(dump_readable_model(checksum_dict), "u8")
    return checksum_dict


def main():
    pack_manager.reload()
    for p in pack_manager.packs:
        calc_n_write_checksum(p.base_path, p.manifest)
        logger.success(f"Wrote {CHECKSUM_FILENAME} in sticker pack `{p.slug}`")
