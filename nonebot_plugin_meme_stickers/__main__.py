from contextlib import asynccontextmanager
from typing import Any, Callable, NoReturn, Optional, Union
from typing_extensions import TypeAlias

import skia
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
from cookit import TypeDecoCollector
from nonebot import logger
from nonebot.adapters import Message as BaseMessage
from nonebot.exception import NoneBotException
from nonebot.typing import T_State
from nonebot_plugin_alconna import AlconnaMatcher, Query, UniMessage, on_alconna
from nonebot_plugin_waiter import prompt

from .config import config
from .draw import (
    draw_sticker_pack_grid,
    draw_sticker_pack_grid_from_packs,
    save_image,
    temp_sticker_card_params,
)
from .sticker_pack import (
    StickerPack,
    StickerPackOperationInfo,
    ValueWithReason,
    fetch_hub_and_packs,
    pack_manager,
)
from .utils import format_error

NAME = "Meme Stickers"
DESCRIPTION = "一站式制作 PJSK 样式表情包"

alc = Alconna(
    "meme-stickers",
    Subcommand(
        "generate",
        Args(  # not using Optional to avoid subcommand match
            Arg("pack?#贴纸包 ID / 代号 / 名称", str),
            Arg("sticker?#贴纸 ID / 名称", str),
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
            Option(
                "-N|--no-unavailable",
                action=store_true,
                help_text="不显示无法使用的贴纸包",
            ),
            help_text="查看本地或 Hub 上的贴纸包列表",
        ),
        Subcommand(
            "reload",
            help_text="重新加载本地贴纸包",
        ),
        Subcommand(
            "install",
            Args["slugs#要下载的贴纸包代号", MultiVar(str, "+")],
            help_text="从 Hub 下载贴纸包",
        ),
        Subcommand(
            "update",
            Args["packs?#要更新的贴纸包 ID / 代号 / 名称", MultiVar(str, "+")],
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
            Args["packs#要删除的贴纸包 ID / 代号 / 名称", MultiVar(str, "+")],
            Option(
                "-y|--yes",
                action=store_true,
                help_text="跳过确认提示",
            ),
            help_text="删除本地贴纸包",
        ),
        Subcommand(
            "disable",
            Args["packs#要删除的贴纸包 ID / 代号 / 名称", MultiVar(str, "+")],
            help_text="删除本地贴纸包",
        ),
        Subcommand(
            "enable",
            Args["packs#要删除的贴纸包 ID / 代号 / 名称", MultiVar(str, "+")],
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

EXIT_COMMANDS = ("0", "e", "exit", "q", "quit", "取消", "退出")


@asynccontextmanager
async def exception_notify(
    msg: str,
    types: Optional[tuple[type[BaseException]]] = None,
):
    try:
        yield
    except NoneBotException:
        raise
    except Exception as e:
        if types and (not isinstance(e, types)):
            raise
        logger.exception(msg.format(e=str(e), type=type(e).__name__))
        await UniMessage(msg).finish()


async def exit_finish() -> NoReturn:
    await UniMessage("已退出选择").finish()


async def timeout_finish() -> NoReturn:
    await UniMessage("等待超时，已退出选择").finish()


async def handle_prompt_common_commands(
    msg: Optional[BaseMessage],
) -> tuple[str, BaseMessage]:
    if not msg:
        await timeout_finish()
    txt = msg.extract_plain_text().strip()
    cmd = txt.lower()
    if cmd in EXIT_COMMANDS:
        await exit_finish()
    return txt, msg


def create_illegal_finisher():
    count = 0

    async def func():
        nonlocal count
        count += 1
        if count >= config.prompt_retries:
            await UniMessage("回复错误次数过多，已退出选择").finish()

    return func


async def sticker_pack_select(include_unavailable: bool = False) -> StickerPack:
    packs = pack_manager.packs if include_unavailable else pack_manager.available_packs
    if not packs:
        await UniMessage("当前无可用贴纸包").finish()

    async with exception_notify("图片绘制失败"):  # fmt: skip
        pack_list_img = save_image(
            draw_sticker_pack_grid_from_packs(packs),
            skia.kJPEG,
        )
    await (
        UniMessage.image(raw=pack_list_img)
        .text(
            "以上为当前可用贴纸包\n"
            f"请在 {config.prompt_timeout} 秒内发送贴纸包 序号 / 代号 / 名称 进行选择",
        )
        .send()
    )

    illegal_finish = create_illegal_finisher()
    while True:
        txt, _ = await handle_prompt_common_commands(await prompt(""))
        if txt.isdigit() and (1 <= (idx := int(txt)) <= len(pack_manager.packs)):
            return pack_manager.packs[idx - 1]
        if pack := pack_manager.find_pack(txt):
            return pack
        await illegal_finish()
        await UniMessage("未找到对应贴纸包，请重新发送").send()


async def find_packs_with_notify(
    *queries: str,
    include_unavailable: bool = False,
) -> list[StickerPack]:
    packs: list[StickerPack] = []
    for query in queries:
        if not (pack := pack_manager.find_pack(query, include_unavailable)):
            await UniMessage(f"未找到贴纸包 `{query}`").finish()
        packs.append(pack)
    return packs


OptItTypes: TypeAlias = Union[str, StickerPack]
OptItFormatter: TypeAlias = Callable[[Any, Optional[str]], str]

OptInfoTypes: TypeAlias = Union[BaseException, str]
OptInfoFormatter: TypeAlias = Callable[[Any], str]

opt_it_formatter = TypeDecoCollector[OptItTypes, OptItFormatter]()
opt_info_formatter = TypeDecoCollector[OptInfoTypes, OptInfoFormatter]()

opt_it_formatter(str)(lambda it, info: f"  - {it}: {info}" if info else f"  - {it}")
opt_it_formatter(StickerPack)(
    lambda it, info: f"  - [{it.slug}] {it.manifest.name}{f': {info}' if info else ''}",
)

opt_info_formatter(str)(lambda x: x)
opt_info_formatter(BaseException)(format_error)


def format_opt_it(it: OptItTypes, info: Union[OptInfoTypes, None] = None) -> str:
    return opt_it_formatter.get_from_type_or_instance(it)(
        it,
        opt_info_formatter.get_from_type_or_instance(info)(info) if info else None,
    )


def format_opt_info(
    opt: Union[StickerPackOperationInfo[str], StickerPackOperationInfo[StickerPack]],
):
    txt: list[str] = []
    if opt.succeed:
        txt.append(f"成功 ({len(opt.succeed)} 个)：")
        txt.extend(format_opt_it(it) for it in opt.succeed)
    if opt.skipped:
        txt.append(f"跳过 ({len(opt.skipped)} 个)：")
        txt.extend(format_opt_it(it.value, it.info) for it in opt.skipped)
    if opt.failed:
        txt.append(f"失败 ({len(opt.failed)} 个)：")
        txt.extend(format_opt_it(it.value, it.info) for it in opt.failed)
    return "\n".join(txt)


@m_cls.dispatch("~generate").handle()
async def _(
    m: AlconnaMatcher,
    # args
    q_pack: Query[Optional[str]] = Query("~pack", None),
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
    q_auto_resize: Query[Optional[bool]] = Query("~auto-resize.value", None),
    q_no_auto_resize: Query[Optional[bool]] = Query("~no-auto-resize.value", None),
    q_debug: Query[bool] = Query("~debug.value", default=False),
):
    pack = (
        (await find_packs_with_notify(q_pack.result))[0]
        if q_pack.result
        else await sticker_pack_select()
    )

    await m.send(str(locals()).replace(", ", ",\n"))


m_packs_cls = m_cls.dispatch("~packs")


@m_packs_cls.dispatch("~list").handle()
async def _(
    q_online: Query[bool] = Query("~online.value", default=False),
    q_no_unavailable: Query[bool] = Query("~no-unavailable.value", default=False),
):
    if q_online.result:
        async with exception_notify("从 Hub 获取贴纸包列表与信息失败"):
            hub, manifests = await fetch_hub_and_packs()
        if not manifests:
            await UniMessage("Hub 上无可用贴纸包").finish()

        async with exception_notify("下载用于预览的贴纸失败"), temp_sticker_card_params(hub, manifests) as params, exception_notify("图片绘制失败"):  # fmt: skip
            pic = save_image(draw_sticker_pack_grid(params), skia.kJPEG)
        await UniMessage.image(raw=pic).text("以上为 Hub 中可用的贴纸包列表").finish()

    packs = (
        pack_manager.available_packs if q_no_unavailable.result else pack_manager.packs
    )
    if not packs:
        await UniMessage("当前无可用贴纸包").finish()
    async with exception_notify("图片绘制失败"):  # fmt: skip
        pic = save_image(
            draw_sticker_pack_grid_from_packs(packs),
            skia.kJPEG,
        )
    await UniMessage.image(raw=pic).text("以上为本地可用的贴纸包列表").finish()


@m_packs_cls.dispatch("~reload").handle()
async def _(m: AlconnaMatcher):
    async with exception_notify("重新加载本地贴纸包失败"):
        pack_manager.reload()
    await m.finish("已重新加载本地贴纸包")


@m_packs_cls.dispatch("~install").handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_packs_cls.dispatch("~update").handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_packs_cls.dispatch("~delete").handle()
async def _(m: AlconnaMatcher):
    await m.finish("开发中")


@m_packs_cls.dispatch("~enable", state={"m_disable": False}).handle()
@m_packs_cls.dispatch("~disable", state={"m_disable": True}).handle()
async def _(
    m: AlconnaMatcher,
    state: T_State,
    q_packs: Query[list[str]] = Query("~packs"),
):
    packs = await find_packs_with_notify(*q_packs.result, include_unavailable=True)

    disable: bool = state["m_disable"]
    type_tip = "禁用" if disable else "启用"

    opt = StickerPackOperationInfo[StickerPack]()
    for pack in packs:
        if pack.config.disabled == disable:
            opt.skipped.append(ValueWithReason(pack, f"贴纸包已被{type_tip}"))
            continue
        try:
            pack.config.disabled = disable
            pack.save_config()
        except Exception as e:
            logger.exception(
                f"Failed to {'disable' if disable else 'enable'} pack {pack.slug}",
            )
            opt.failed.append(ValueWithReason(pack, e))
        else:
            opt.succeed.append(pack)

    await m.finish(f"已{type_tip}以下贴纸包：\n{format_opt_info(opt)}")


# fallback help
@m_packs_cls.assign("$main")
@m_cls.assign("$main")
async def _(m: AlconnaMatcher):
    await m.finish(alc.get_help())
