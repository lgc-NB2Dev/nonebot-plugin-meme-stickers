from cookit.pyd import type_validate_json

from .models import HubManifest, StickerPackManifest, StickersHubFileSource
from .source_fetch import fetch_github_source


async def fetch_hub() -> HubManifest:
    return type_validate_json(
        HubManifest,
        (await fetch_github_source(StickersHubFileSource)).text,
    )


async def fetch_hub_and_packs() -> tuple[HubManifest, dict[str, StickerPackManifest]]:
    pass
