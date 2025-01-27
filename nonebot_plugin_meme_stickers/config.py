from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel


class ConfigModel(BaseModel):
    meme_stickers_data_dir: Path = Path("./data/meme_stickers")


config: ConfigModel = get_plugin_config(ConfigModel)
