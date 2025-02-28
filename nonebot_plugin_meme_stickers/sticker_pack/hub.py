import asyncio
from pathlib import Path
from typing import Optional
from typing_extensions import Unpack

from cookit.loguru import warning_suppress
from cookit.pyd import model_copy, type_validate_json

from ..consts import CHECKSUM_FILENAME, HUB_MANIFEST_FILENAME, MANIFEST_FILENAME
from ..draw.pack_list import StickerPackCardParams
from ..utils import calc_checksum
from ..utils.file_source import (
    FileSource,
    FileSourceGitHubBranch,
    ReqKwargs,
    fetch_github_source,
    fetch_source,
    with_kw_sem,
)
from .models import ChecksumDict, HubManifest, HubStickerPackInfo, StickerPackManifest

STICKERS_HUB_FILE_SOURCE = FileSourceGitHubBranch(
    owner="lgc-NB2Dev",
    repo="meme-stickers-hub",
    branch="main",
    path=HUB_MANIFEST_FILENAME,
)


async def fetch_hub(**req_kw: Unpack[ReqKwargs]) -> HubManifest:
    return type_validate_json(
        HubManifest,
        (await fetch_github_source(STICKERS_HUB_FILE_SOURCE, **req_kw)).text,
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
    hub = await fetch_hub(**req_kw)

    async with with_kw_sem(req_kw):
        packs = await asyncio.gather(
            *(fetch_optional_manifest(x.source, **req_kw) for x in hub),
        )
    packs_dict = {h.slug: p for h, p in zip(hub, packs) if p is not None}
    return hub, packs_dict


async def temp_sticker_card_params(
    cache_dir: Path,
    hub: HubManifest,
    manifests: dict[str, StickerPackManifest],
    checksums: Optional[dict[str, ChecksumDict]] = None,
    **req_kw: Unpack[ReqKwargs],
) -> list[StickerPackCardParams]:
    async def task(i: int, info: HubStickerPackInfo):
        manifest = manifests[info.slug]
        sticker = model_copy(manifest.resolved_sample_sticker)

        sticker_hash = (
            checksums.get(info.slug, {}).get(sticker.base_image) if checksums else None
        )
        if (not sticker_hash) or (not (cache_dir / sticker_hash).exists()):
            cache_dir.mkdir(parents=True, exist_ok=True)
            resp = await fetch_source(info.source, sticker.base_image, **req_kw)
            if not sticker_hash:
                sticker_hash = calc_checksum(resp.content)
            (cache_dir / sticker_hash).write_bytes(resp.content)

        sticker.base_image = sticker_hash
        return StickerPackCardParams(
            base_path=cache_dir,
            sample_sticker_params=sticker,
            name=manifest.name,
            slug=info.slug,
            description=manifest.description,
            index=str(i),
        )

    async with with_kw_sem(req_kw):
        return await asyncio.gather(*(task(i, x) for i, x in enumerate(hub, 1)))
