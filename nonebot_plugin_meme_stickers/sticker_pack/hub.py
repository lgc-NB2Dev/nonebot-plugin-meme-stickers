import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from typing_extensions import Unpack

from cookit.loguru import warning_suppress
from cookit.pyd import model_copy, type_validate_json
from yarl import URL

from ..consts import CHECKSUM_FILENAME, HUB_MANIFEST_FILENAME, MANIFEST_FILENAME
from ..draw.pack_list import StickerPackCardParams
from ..utils.file_source import (
    FileSource,
    FileSourceGitHubBranch,
    ReqKwargs,
    create_req_sem,
    fetch_github_source,
    fetch_source,
)
from .models import (
    ChecksumDict,
    HubManifest,
    HubStickerPackInfo,
    StickerPackManifest,
)

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
    if "sem" not in req_kw:
        req_kw["sem"] = create_req_sem()

    hub = await fetch_hub(**req_kw)

    packs = await asyncio.gather(
        *(fetch_optional_manifest(x.source, **req_kw) for x in hub),
    )
    packs_dict = {h.slug: p for h, p in zip(hub, packs) if p is not None}
    return hub, packs_dict


# 唉一开始就没设计好，整出来这么个玩意
@asynccontextmanager
async def temp_sticker_card_params(
    hub: HubManifest,
    manifests: dict[str, StickerPackManifest],
    **req_kw: Unpack[ReqKwargs],
) -> AsyncIterator[list[StickerPackCardParams]]:
    if "sem" not in req_kw:
        req_kw["sem"] = create_req_sem()

    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)

        async def task(i: int, info: HubStickerPackInfo):
            sticker = model_copy(manifests[info.slug].resolved_sample_sticker)
            resp = await fetch_source(info.source, sticker.base_image)

            filename = f"{info.slug}_{URL(sticker.base_image).name}"
            (path / filename).write_bytes(resp.content)
            sticker.base_image = filename

            manifest = manifests[info.slug]
            return StickerPackCardParams(
                base_path=path,
                sample_sticker_params=sticker,
                name=manifest.name,
                slug=info.slug,
                description=manifest.description,
                index=str(i),
            )

        cards = await asyncio.gather(*(task(i, x) for i, x in enumerate(hub, 1)))
        yield cards
