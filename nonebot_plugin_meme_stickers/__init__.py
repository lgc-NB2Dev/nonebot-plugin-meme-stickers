# ruff: noqa: E402

from nonebot.plugin import PluginMetadata, inherit_supported_adapters, require

require("nonebot_plugin_alconna")

from . import __main__ as __main__
from .config import ConfigModel

__version__ = "0.1.0"
__plugin_meta__ = PluginMetadata(
    name="Meme Stickers",
    description="一站式制作 PJSK 样式表情包",
    usage="暂无",
    type="application",
    homepage="https://github.com/lgc-NB2Dev/nonebot-plugin-meme-stickers",
    config=ConfigModel,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"License": "MIT", "Author": "LgCookie"},
)
