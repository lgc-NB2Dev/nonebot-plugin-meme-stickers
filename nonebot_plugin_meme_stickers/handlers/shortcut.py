from nonebot import logger

from ..sticker_pack import pack_manager
from ..sticker_pack.manager import StickerPackManager
from ..sticker_pack.pack import StickerPack
from .shared import alc

registered_commands: dict[str, set[str]] = {}


@pack_manager.add_callback
def reregister_shortcuts(_: StickerPackManager, pack: StickerPack):
    pack_available = not pack.unavailable
    registered = registered_commands.get(pack.slug)
    new_commands = (
        {
            *pack.merged_config.commands,
            *pack.merged_config.extend_commands,
        }
        if pack_available
        else None
    )

    logger.debug(
        f"Pack `{pack.slug}` state changed, reregistering shortcuts"
        f" (`{registered}` -> `{new_commands}`)",
    )

    if registered:
        for x in registered:
            msg = alc.shortcut(x, delete=True)
            logger.debug(msg)
        del registered_commands[pack.slug]

    if new_commands:
        for x in new_commands:
            msg = alc.shortcut(x, arguments=["generate", pack.slug], prefix=True)
            logger.debug(msg)
        registered_commands[pack.slug] = new_commands
