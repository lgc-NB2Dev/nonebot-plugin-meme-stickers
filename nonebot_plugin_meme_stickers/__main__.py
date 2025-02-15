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
from nonebot_plugin_alconna import (
    AlconnaMatcher,
    Query,
    on_alconna,
)

NAME = "Meme Stickers"
DESCRIPTION = "一站式制作 PJSK 样式表情包"

alc = Alconna(
    "meme-stickers",
    Subcommand(
        "generate",
        Args(
            Arg("slug#贴纸包代号", Optional[str]),
            Arg("sticker#贴纸 ID", Optional[str]),
            Arg("text#贴纸文本", Optional[str]),
        ),
        Option(
            "-x|--x",
            Args["x", Optional[float]],
            help_text="文本基线 X 坐标",
        ),
        Option(
            "-y|--y",
            Args["y", Optional[float]],
            help_text="文本基线 Y 坐标",
        ),
        Option(
            "--align",
            Args["align", Optional[str]],
            help_text="文本对齐方式",
        ),
        Option(
            "--rotate",
            Args["rotate", Optional[float]],
            help_text="文本旋转角度",
        ),
        Option(
            "--color",
            Args["color", Optional[str]],
            help_text="文本颜色",
        ),
        Option(
            "--stroke-color",
            Args["stroke_color", Optional[str]],
            help_text="文本描边颜色",
        ),
        Option(
            "--stroke-width-factor",
            Args["stroke_width_factor", Optional[float]],
            help_text="文本描边宽度系数",
        ),
        Option(
            "--font-size",
            Args["font_size", Optional[float]],
            help_text="文本字号",
        ),
        Option(
            "--font-style",
            Args["font_style", Optional[str]],
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
            Args["image_format", Optional[str]],
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


m_generate = m_cls.dispatch("~generate")


@m_generate.handle()
async def _(
    m: AlconnaMatcher,
    slug: Optional[str] = None,
    sticker: Optional[str] = None,
    text: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    align: Optional[str] = None,
    rotate: Optional[float] = None,
    color: Optional[str] = None,
    stroke_color: Optional[str] = None,
    stroke_width_factor: Optional[float] = None,
    font_size: Optional[float] = None,
    font_style: Optional[str] = None,
    image_format: Optional[str] = None,
    q_auto_resize: Query[Optional[bool]] = Query("~auto_resize.value", None),
    q_no_auto_resize: Query[Optional[bool]] = Query(
        "~no_auto_resize.value",
        default=False,
    ),
    q_debug: Query[bool] = Query("~debug.value", default=False),
):
    await m.send(str(locals()).replace(", ", ",\n"))


m_packs_cls = m_cls.dispatch("~packs")

m_packs_list_cls = m_packs_cls.dispatch("~list")


@m_packs_list_cls.handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


m_packs_reload_cls = m_packs_cls.dispatch("~reload")


@m_packs_reload_cls.handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


m_packs_install_cls = m_packs_cls.dispatch("~install")


@m_packs_install_cls.handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


m_packs_update_cls = m_packs_cls.dispatch("~update")


@m_packs_update_cls.handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


m_packs_delete_cls = m_packs_cls.dispatch("~delete")


@m_packs_delete_cls.handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


# fallback help


@m_packs_cls.handle()
@m_cls.assign("$main")
async def _(m: AlconnaMatcher):
    await m.finish(alc.get_help())
