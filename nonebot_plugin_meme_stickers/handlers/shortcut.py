from nonebot import logger

from ..sticker_pack import pack_manager
from ..sticker_pack.manager import StickerPackManager
from ..sticker_pack.pack import StickerPack
from .shared import alc, m_cls

registered_commands: dict[str, set[str]] = {}


@pack_manager.add_callback
def reregister_shortcuts(_: StickerPackManager, pack: StickerPack):
    available = not pack.unavailable
    registered = registered_commands.get(pack.slug)
    new_commands = (
        {
            *pack.merged_config.commands,
            *pack.merged_config.extend_commands,
        }
        if available
        else None
    )

    logger.debug(
        f"Pack `{pack.slug}` state changed, reregistering shortcuts"
        f" ({available=}, `{registered}` -> `{new_commands}`)",
    )

    if registered:
        for x in registered:
            msg = alc.shortcut(x, delete=True)
            logger.debug(msg)
        del registered_commands[pack.slug]

    if new_commands:
        for x in new_commands:
            m_cls.shortcut(x, arguments=["generate", pack.slug], prefix=True)
        registered_commands[pack.slug] = new_commands
