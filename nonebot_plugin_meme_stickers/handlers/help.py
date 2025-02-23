import skia
from nonebot_plugin_alconna import UniMessage

from ..draw.tools import (
    SYSTEM_MONOSPACE_FONTS,
    make_surface_for_picture,
    save_image,
    text_to_picture,
)
from .shared import alc, m_cls


# fallback help
@m_cls.assign("$main")
async def _():
    img = save_image(
        make_surface_for_picture(
            text_to_picture(alc.get_help(), font_families=SYSTEM_MONOSPACE_FONTS),
        ),
        skia.kPNG,
    )
    await UniMessage.image(raw=img).finish()
