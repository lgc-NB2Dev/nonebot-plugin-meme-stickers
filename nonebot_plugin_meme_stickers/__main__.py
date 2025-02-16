from typing import Optional

from arclet.alconna import (
    Alconna,
    Arg,
    Args,
    CommandMeta,
    MultiVar,
    Option,
    Subcommand,
    store_true,
)
from nonebot_plugin_alconna import AlconnaMatcher, Query, on_alconna

NAME = "Meme Stickers"
DESCRIPTION = "一站式制作 PJSK 样式表情包"

alc = Alconna(
    "meme-stickers",
    Subcommand(
        "generate",
        Args(  # not using Optional to avoid subcommand match
            Arg("slug?#贴纸包代号", str),
            Arg("sticker?#贴纸 ID", str),
            Arg("text?#贴纸文本", str),
        ),
        Option(
            "-x|--x",
            Args["x", float],
            help_text="文本基线 X 坐标",
        ),
        Option(
            "-y|--y",
            Args["y", float],
            help_text="文本基线 Y 坐标",
        ),
        Option(
            "--align",
            Args["align", str],
            help_text="文本对齐方式",
        ),
        Option(
            "--rotate",
            Args["rotate", float],
            help_text="文本旋转角度",
        ),
        Option(
            "--color",
            Args["color", str],
            help_text="文本颜色",
        ),
        Option(
            "--stroke-color",
            Args["stroke_color", str],
            help_text="文本描边颜色",
        ),
        Option(
            "--stroke-width-factor",
            Args["stroke_width_factor", float],
            help_text="文本描边宽度系数",
        ),
        Option(
            "--font-size",
            Args["font_size", float],
            help_text="文本字号",
        ),
        Option(
            "--font-style",
            Args["font_style", str],
            help_text="文本字体风格",
        ),
        Option(
            "--auto-resize",
            action=store_true,
            help_text="启用自动调整文本位置与尺寸",
        ),
        Option(
            "--no-auto-resize",
            action=store_true,
            help_text="禁用自动调整文本位置与尺寸",
        ),
        Option(
            "--image-format",
            Args["image_format", str],
            help_text="输出文件类型",
        ),
        Option(
            "--debug",
            action=store_true,
            help_text="启用调试模式",
        ),
        help_text="生成贴纸",
    ),
    Subcommand(
        "packs",
        Subcommand(
            "list",
            Option(
                "-o|--online",
                action=store_true,
                help_text="显示 Hub 上的贴纸列表",
            ),
            help_text="查看本地或 Hub 上的贴纸包列表",
        ),
        Subcommand(
            "reload",
            help_text="重新加载本地贴纸包",
        ),
        Subcommand(
            "install",
            Args[
                "slugs#要下载的贴纸包代号",
                MultiVar(str, "+"),
            ],
            help_text="从 Hub 下载贴纸包",
        ),
        Subcommand(
            "update",
            Args[
                "slugs?#要更新的贴纸包代号",
                MultiVar(str, "+"),
            ],
            Option(
                "-a|--all",
                action=store_true,
                help_text="更新所有贴纸包",
            ),
            Option(
                "-f|--force",
                action=store_true,
                help_text="忽略本地版本，强制更新",
            ),
            help_text="从 Hub 更新贴纸包",
        ),
        Subcommand(
            "delete",
            Args[
                "slugs#要删除的贴纸包代号",
                MultiVar(str, "+"),
            ],
            Option(
                "-y|--yes",
                action=store_true,
                help_text="跳过确认提示",
            ),
            help_text="删除本地贴纸包",
        ),
        help_text="管理贴纸包",
    ),
    meta=CommandMeta(
        description=DESCRIPTION,
    ),
)
m_cls = on_alconna(
    alc,
    skip_for_unmatch=False,
    auto_send_output=True,
    use_cmd_start=True,
    use_cmd_sep=True,
)


@m_cls.dispatch("~generate").handle()
async def _(
    m: AlconnaMatcher,
    # args
    q_slug: Query[Optional[str]] = Query("~slug", None),
    q_sticker: Query[Optional[str]] = Query("~sticker", None),
    q_text: Query[Optional[str]] = Query("~text", None),
    # opts with args
    q_x: Query[Optional[float]] = Query("~x", None),
    q_y: Query[Optional[float]] = Query("~y", None),
    q_align: Query[Optional[str]] = Query("~align", None),
    q_rotate: Query[Optional[float]] = Query("~rotate", None),
    q_color: Query[Optional[str]] = Query("~color", None),
    q_stroke_color: Query[Optional[str]] = Query("~stroke_color", None),
    q_stroke_width_factor: Query[Optional[float]] = Query("~stroke_width_factor", None),
    q_font_size: Query[Optional[float]] = Query("~font_size", None),
    q_font_style: Query[Optional[str]] = Query("~font_style", None),
    q_image_format: Query[Optional[str]] = Query("~image_format", None),
    # opts without args
    q_auto_resize: Query[Optional[bool]] = Query("~auto_resize.value", None),
    q_no_auto_resize: Query[Optional[bool]] = Query("~no_auto_resize.value", None),
    q_debug: Query[bool] = Query("~debug.value", default=False),
):
    await m.send(str(locals()).replace(", ", ",\n"))


m_packs_cls = m_cls.dispatch("~packs")


@m_packs_cls.dispatch("~list").handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_packs_cls.dispatch("~reload").handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_packs_cls.dispatch("~install").handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_packs_cls.dispatch("~update").handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_packs_cls.dispatch("~update").handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


# fallback help
@m_cls.assign("$main")
async def _(m: AlconnaMatcher):
    await m.finish(alc.get_help())
