from pathlib import Path
from typing import Optional

from nonebot import get_plugin_config
from pydantic import BaseModel


class ConfigModel(BaseModel):
    proxy: Optional[str] = None

    meme_stickers_data_dir: Path = Path("./data/meme_stickers")
    meme_stickers_github_url_template: str = (
        "https://raw.githubusercontent.com/{owner}/{repo}/{ref_path}/{path}"
    )
    meme_stickers_retry_times: int = 3
    meme_stickers_req_concurrency: int = 8


config: ConfigModel = get_plugin_config(ConfigModel)
