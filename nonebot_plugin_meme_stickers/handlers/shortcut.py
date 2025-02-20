from arclet.alconna import command_manager
from cookit.loguru import warning_suppress
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
    new_commands = set(
        *pack.merged_config.commands,
        *pack.merged_config.extend_commands,
    )

    logger.debug(
        f"Pack `{pack.slug}` state changed, reregistering shortcuts"
        f" (current state {'' if pack_available else 'un'}available"
        f", registered {registered}"
        f", new {new_commands})",
    )

    if registered:
        for x in registered:
            with warning_suppress(f"Failed to delete shortcut {x}"):
                command_manager.delete_shortcut(alc, x)
        del registered_commands[pack.slug]

    if not pack.unavailable:
        for x in new_commands:
            with warning_suppress(f"Failed to register shortcut {x}"):
                alc.shortcut(x, arguments=["generate", pack.slug])
        registered_commands[pack.slug] = new_commands
