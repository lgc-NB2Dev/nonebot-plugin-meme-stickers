from typing import Optional

import skia
from arclet.alconna import Arg, Args, Option, store_true
from cookit.pyd import model_copy
from nonebot_plugin_alconna import AlconnaMatcher, Query, UniMessage
from nonebot_plugin_waiter import prompt

from ..config import config, resolve_color_to_tuple
from ..consts import RELATIVE_FLOAT_PARAM
from ..draw.sticker import make_sticker_picture_from_params
from ..draw.tools import (
    FONT_STYLE_FUNC_MAP,
    IMAGE_FORMAT_MAP,
    TEXT_ALIGN_MAP,
    make_surface_for_picture,
    save_image,
)
from ..utils import resolve_relative_num
from .shared import (
    alc,
    create_illegal_finisher,
    exception_notify,
    find_dict_value_with_notify,
    find_packs_with_notify,
    handle_idx_command,
    handle_prompt_common_commands,
    m_cls,
    sticker_pack_select,
    sticker_select,
)

alc.subcommand(
    "generate",
    Args(  # not using Optional to avoid subcommand match
        Arg("pack?", str, notice="贴纸包 ID / 代号 / 名称"),
        Arg("sticker?", str, notice="贴纸 ID / 名称"),
        Arg("text?", str, notice="贴纸文本"),
    ),
    Option(
        "-x|--x",
        Args["x", RELATIVE_FLOAT_PARAM],
        help_text="文本基线 X 坐标（以 ^ 开头指偏移值）",
    ),
    Option(
        "-y|--y",
        Args["y", RELATIVE_FLOAT_PARAM],
        help_text="文本基线 Y 坐标（以 ^ 开头指偏移值）",
    ),
    Option(
        "-a|--align",
        Args["align", str],
        help_text="文本对齐方式",
    ),
    Option(
        "-r|--rotate",
        Args["rotate", RELATIVE_FLOAT_PARAM],
        help_text="文本旋转角度（以 ^ 开头指偏移值）",
    ),
    Option(
        "-c|--color",
        Args["color", str],
        help_text="文本颜色",
    ),
    Option(
        "-C|--stroke-color",
        Args["stroke_color", str],
        help_text="文本描边颜色",
    ),
    Option(
        "-W|--stroke-width-factor",
        Args["stroke_width_factor", RELATIVE_FLOAT_PARAM],
        help_text="文本描边宽度系数",
    ),
    Option(
        "-s|--font-size",
        Args["font_size", RELATIVE_FLOAT_PARAM],
        help_text="文本字号（以 ^ 开头指偏移值）",
    ),
    Option(
        "-S|--font-style",
        Args["font_style", str],
        help_text="文本字体风格",
    ),
    Option(
        "-A|--auto-resize",
        action=store_true,
        help_text=(
            "启用自动调整文本位置与尺寸"
            "（默认启用，当 x 或 y 参数指定时会自动禁用，需要携带此参数以使用）"
        ),
    ),
    Option(
        "-N|--no-auto-resize",
        action=store_true,
        help_text="禁用自动调整文本位置与尺寸",
    ),
    Option(
        "-f|--image-format",
        Args["image_format", str],
        help_text="输出文件类型",
    ),
    Option(
        "-b|--background",
        Args["background", str],
        help_text="当文件类型为 jpeg 时图片的背景色",
    ),
    Option(
        "-D|--debug",
        action=store_true,
        help_text="启用调试模式",
    ),
    help_text="生成贴纸",
    alias=["g", "gen"],
)


async def prompt_sticker_text() -> str:
    await UniMessage("请发送你想要写在贴纸上的文本").send()
    illegal_finish = create_illegal_finisher()
    while True:
        txt, _ = await handle_prompt_common_commands(
            await prompt("", timeout=config.prompt_timeout),
        )
        if txt:
            return txt
        await illegal_finish()
        await UniMessage("文本不能为空，请重新发送").send()


@m_cls.dispatch("~generate").handle()
async def _(
    m: AlconnaMatcher,
    # args
    q_pack: Query[Optional[str]] = Query("~pack", None),
    q_sticker: Query[Optional[str]] = Query("~sticker", None),
    q_text: Query[Optional[str]] = Query("~text", None),
    # opts with args
    q_x: Query[Optional[str]] = Query("~x.x", None),
    q_y: Query[Optional[str]] = Query("~y.y", None),
    q_align: Query[Optional[str]] = Query("~align.align", None),
    q_rotate: Query[Optional[str]] = Query("~rotate.rotate", None),
    q_color: Query[Optional[str]] = Query("~color.color", None),
    q_stroke_color: Query[Optional[str]] = Query("~stroke_color.stroke_color", None),
    q_stroke_width_factor: Query[Optional[str]] = Query(
        "~stroke_width_factor.stroke_width_factor",
        None,
    ),
    q_font_size: Query[Optional[str]] = Query("~font_size.font_size", None),
    q_font_style: Query[Optional[str]] = Query("~font_style.font_style", None),
    q_image_format: Query[Optional[str]] = Query("~image_format.image_format", None),
    q_background: Query[Optional[str]] = Query("~background.background", default=None),
    # opts without args
    q_auto_resize: Query[Optional[bool]] = Query("~auto-resize.value", None),
    q_no_auto_resize: Query[Optional[bool]] = Query("~no-auto-resize.value", None),
    q_debug: Query[bool] = Query("~debug.value", default=False),
):
    if q_align.result and (q_align.result not in TEXT_ALIGN_MAP):
        await m.finish(f"文本对齐方式 `{q_align.result}` 未知")

    async with exception_notify(f"颜色 `{q_color.result}` 格式不正确"):
        color = resolve_color_to_tuple(q_color.result) if q_color.result else None

    async with exception_notify(f"颜色 `{q_stroke_color.result}` 格式不正确"):
        stroke_color = (
            resolve_color_to_tuple(q_stroke_color.result)
            if q_stroke_color.result
            else None
        )

    if q_font_style.result and (q_font_style.result not in FONT_STYLE_FUNC_MAP):
        await m.finish(f"字体风格 `{q_font_style.result}` 未知")

    image_format = (
        await find_dict_value_with_notify(
            IMAGE_FORMAT_MAP,
            q_image_format.result,
            f"图片格式 `{q_image_format.result}` 未知",
        )
        if q_image_format.result
        else IMAGE_FORMAT_MAP[config.default_sticker_image_format]
    )

    async with exception_notify(
        f"颜色 `{q_background.result}` 格式不正确",
        (ValueError,),
    ):
        background = (
            skia.Color(*resolve_color_to_tuple(q_background.result))
            if q_background.result
            else config.default_sticker_background
        )

    pack = (
        (await find_packs_with_notify(q_pack.result))[0]
        if q_pack.result
        else await sticker_pack_select()
    )

    sticker = (
        (
            handle_idx_command(q_sticker.result, pack.manifest.resolved_stickers)
            or pack.manifest.find_sticker_by_name(q_sticker.result)
        )
        if q_sticker.result
        else await sticker_select(pack)
    )
    if not sticker:
        await m.finish(f"未找到贴纸 `{q_sticker.result}`")

    params = model_copy(sticker.params)

    text = q_text.result or await prompt_sticker_text()
    params.text = text

    if q_x.result:
        params.text_x = resolve_relative_num(q_x.result, params.text_x)
    if q_y.result:
        params.text_y = resolve_relative_num(q_y.result, params.text_y)
    if q_align.result:
        params.text_align = q_align.result
    if q_rotate.result:
        params.text_rotate_degrees = resolve_relative_num(
            q_rotate.result,
            params.text_rotate_degrees,
        )
    if color:
        params.text_color = color
    if stroke_color:
        params.stroke_color = stroke_color
    if q_stroke_width_factor.result:
        params.stroke_width_factor = resolve_relative_num(
            q_stroke_width_factor.result,
            params.stroke_width_factor,
        )
    if q_font_size.result:
        params.font_size = resolve_relative_num(q_font_size.result, params.font_size)
    if q_font_style.result:
        params.font_style = q_font_style.result

    auto_resize = not (q_x.result or q_y.result)
    if auto_resize and q_no_auto_resize.result:
        auto_resize = False
    if (not auto_resize) and q_auto_resize.result:
        auto_resize = True

    img = save_image(
        make_surface_for_picture(
            make_sticker_picture_from_params(
                pack.base_path,
                params,
                auto_resize,
                debug=q_debug.result,
            ),
            background if image_format == skia.kJPEG else None,
        ),
        image_format,
    )
    msg = UniMessage.image(raw=img)
    # if q_debug.result:
    #     msg += f"auto_resize = {auto_resize}"
    await msg.finish()
