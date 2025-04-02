from nonebot import logger

from ..sticker_pack import pack_manager
from ..sticker_pack.manager import StickerPackManager
from ..sticker_pack.pack import StickerPack
from .shared import alc

registered_commands: dict[str, set[str]] = {}


@pack_manager.add_callback
def reregister_shortcuts(_: StickerPackManager, pack: StickerPack):
    registered = registered_commands.get(pack.slug)
    if not registered:
        registered = registered_commands[pack.slug] = set[str]()

    available = not pack.unavailable
    new_commands = {
        *pack.merged_config.commands,
        *pack.merged_config.extend_commands,
    }
    if available:
        should_register = new_commands - registered
        should_unregister = registered - new_commands
    else:
        should_register = None
        should_unregister = registered.copy()

    logger.debug(
        f"Pack `{pack.slug}` state changed, reregistering shortcuts"
        f" - {registered} -> {new_commands}, {available=}"
        f", {should_register=}, {should_unregister=}",
    )

    if should_register:
        for x in should_register:
            msg = alc.shortcut(x, arguments=["generate", pack.slug], prefix=True)
            logger.debug(msg)
            registered.add(x)

    if should_unregister:
        for x in should_unregister:
            msg = alc.shortcut(x, delete=True)
            logger.debug(msg)
            registered.remove(x)
