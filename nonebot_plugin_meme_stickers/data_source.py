from .config import config
from .models import StickerPackManifest


async def download_sticker_pack(pack: StickerPackManifest, download_name: str) -> None:
    base_path = config.meme_stickers_data_dir / download_name
