# ruff: noqa: E402

import asyncio

from nonebot import get_driver
from nonebot.plugin import PluginMetadata, inherit_supported_adapters, require

require("nonebot_plugin_alconna")

from .config import ConfigModel, config
from .consts import AUTHOR, DESCRIPTION, NAME
from .handlers import load_handlers
from .sticker_pack import pack_manager

__version__ = "0.1.0"
__plugin_meta__ = PluginMetadata(
    name=NAME,
    description=DESCRIPTION,
    usage="使用指令 meme-stickers 查看帮助",
    type="application",
    homepage="https://github.com/lgc-NB2Dev/nonebot-plugin-meme-stickers",
    config=ConfigModel,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"License": "MIT", "Author": AUTHOR},
)


load_handlers()


driver = get_driver()


@driver.on_startup
async def _():
    pack_manager.reload(clear_updating_flags=True)

    if config.auto_update:
        await asyncio.create_task(pack_manager.update(force=config.force_update))
