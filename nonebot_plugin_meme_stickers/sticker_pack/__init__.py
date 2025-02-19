from ..config import config
from .manager import StickerPackManager

pack_manager = StickerPackManager(config.data_dir)
