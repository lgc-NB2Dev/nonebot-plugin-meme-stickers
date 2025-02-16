from pathlib import Path
from typing import Optional

from cookit.pyd import get_alias_model
from nonebot import get_plugin_config
from pydantic import Field

BaseConfigModel = get_alias_model(lambda x: f"meme_stickers_{x}")


class ConfigModel(BaseConfigModel):
    proxy: Optional[str] = Field(None, alias="proxy")

    data_dir: Path = Path("./data/meme_stickers")

    github_url_template: str = (
        "https://raw.githubusercontent.com/{owner}/{repo}/{ref_path}/{path}"
    )
    retry_times: int = 3
    req_concurrency: int = 8

    meme_sticker_auto_update: bool = True
    force_update: bool = False

    prompt_retries: int = 3
    prompt_timeout: int = 30


config: ConfigModel = get_plugin_config(ConfigModel)
