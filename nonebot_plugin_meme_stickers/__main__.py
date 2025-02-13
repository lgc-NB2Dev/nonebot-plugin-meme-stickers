from arclet.alconna import Alconna, Args, MultiVar, Option, Subcommand, store_true
from nonebot_plugin_alconna import AlconnaMatcher, on_alconna

from .models import SkiaEncodedImageFormatType, SkiaFontStyleType, SkiaTextAlignType

alc = Alconna(
    "meme-stickers",
    Subcommand(
        "generate",
        Args[
            "slug#贴纸包代号",
            str,
        ][
            "sticker_id#贴纸包内贴纸 ID",
            int,
        ][
            "text#贴纸文本",
            str,
        ],
        Option(
            "-x",
            Args["x", float],
            help_text="文本基线 X 坐标",
        ),
        Option(
            "-y",
            Args["y", float],
            help_text="文本基线 Y 坐标",
        ),
        Option(
            "--align",
            Args["align", SkiaTextAlignType],
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
            Args["font_style", SkiaFontStyleType],
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
            Args["image-format", SkiaEncodedImageFormatType],
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
        "generate-interactive",
        Args["slug#贴纸包代号", str],
        help_text="交互式生成贴纸",
    ),
    Subcommand(
        "packs",
        Subcommand(
            "list",
            Option(
                "--online|-o",
                action=store_true,
                help_text="显示 Hub 上的贴纸列表",
            ),
            help_text="查看贴纸包列表",
        ),
        Subcommand(
            "update",
            Args[
                "slugs#要下载或更新的贴纸包代号",
                MultiVar(str, "*"),
            ],
            Option(
                "--all|-a",
                action=store_true,
                help_text="更新所有贴纸包",
            ),
            Option(
                "--force|-f",
                action=store_true,
                help_text="忽略本地版本，强制更新",
            ),
            help_text="下载或从 Hub 更新贴纸包",
        ),
        Subcommand(
            "delete",
            Args[
                "slugs#要删除的贴纸包代号",
                MultiVar(str, "*"),
            ],
            Option(
                "--yes|-y",
                action=store_true,
                help_text="跳过确认提示",
            ),
            help_text="删除本地贴纸包",
        ),
        help_text="管理贴纸包",
    ),
)
m_cls = on_alconna(
    alc,
    auto_send_output=True,
    use_cmd_start=True,
    use_cmd_sep=True,
)


@m_cls.assign("generate")
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_cls.assign("generate-interactive")
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_cls.assign("packs.list")
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_cls.assign("packs.update")
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_cls.assign("packs.delete")
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_cls.assign("$main")
async def _(m: AlconnaMatcher):
    await m.finish("开发中")
