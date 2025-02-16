# ruff: noqa: E402

import asyncio

from nonebot import get_driver
from nonebot.plugin import PluginMetadata, inherit_supported_adapters, require

require("nonebot_plugin_alconna")

from .__main__ import DESCRIPTION, NAME
from .config import ConfigModel, config
from .sticker_pack import pack_manager

__version__ = "0.1.0"
__plugin_meta__ = PluginMetadata(
    name=NAME,
    description=DESCRIPTION,
    usage="指令：meme-stickers",
    type="application",
    homepage="https://github.com/lgc-NB2Dev/nonebot-plugin-meme-stickers",
    config=ConfigModel,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"License": "MIT", "Author": "LgCookie"},
)

driver = get_driver()


@driver.on_startup
async def _():
    pack_manager.reload(clear_updating_flags=True)

    if config.meme_sticker_auto_update:
        await asyncio.create_task(pack_manager.update(force=config.force_update))
