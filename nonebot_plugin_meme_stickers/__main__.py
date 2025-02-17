from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any, Callable, NoReturn, Optional, TypeVar, Union
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
from cookit.pyd import model_copy
from nonebot import logger
from nonebot.adapters import Message as BaseMessage
from nonebot.exception import NoneBotException
from nonebot.typing import T_State
from nonebot_plugin_alconna import AlconnaMatcher, Query, UniMessage, on_alconna
from nonebot_plugin_waiter import prompt

from .config import config
from .draw import (
    FONT_STYLE_FUNC_MAP,
    IMAGE_FORMAT_MAP,
    TEXT_ALIGN_MAP,
    draw_sticker_grid_from_params,
    draw_sticker_pack_grid,
    draw_sticker_pack_grid_from_packs,
    make_sticker_picture_from_params,
    make_surface_for_picture,
    save_image,
    temp_sticker_card_params,
)
from .models import StickerInfo, StickerParams, resolve_color_to_tuple
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

RELATIVE_INT_PARAM = r"re:\^?(\+-)?\d+"
RELATIVE_FLOAT_PARAM = r"re:\^?(\+-)?\d+(\.\d+)?"

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
            Args["x", RELATIVE_FLOAT_PARAM],
            help_text="文本基线 X 坐标（以 ^ 开头指偏移值）",
        ),
        Option(
            "-y|--y",
            Args["y", RELATIVE_FLOAT_PARAM],
            help_text="文本基线 Y 坐标（以 ^ 开头指偏移值）",
        ),
        Option(
            "--align",
            Args["align", str],
            help_text="文本对齐方式",
        ),
        Option(
            "--rotate",
            Args["rotate", RELATIVE_FLOAT_PARAM],
            help_text="文本旋转角度（以 ^ 开头指偏移值）",
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
            Args["stroke_width_factor", RELATIVE_FLOAT_PARAM],
            help_text="文本描边宽度系数",
        ),
        Option(
            "--font-size",
            Args["font_size", RELATIVE_FLOAT_PARAM],
            help_text="文本字号（以 ^ 开头指偏移值）",
        ),
        Option(
            "--font-style",
            Args["font_style", str],
            help_text="文本字体风格",
        ),
        Option(
            "--auto-resize",
            action=store_true,
            help_text="启用自动调整文本位置与尺寸（默认启用，当 x 或 y 参数指定时会自动禁用，需要携带此参数以使用）",
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
            "--background",
            Args["background", str],
            help_text="当文件类型为 jpeg 时图片的背景色",
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

T = TypeVar("T")


EXIT_COMMANDS = ("0", "e", "exit", "q", "quit", "取消", "退出")
COMMON_COMMANDS_TIP = "另外可以回复 0 来退出"

RETURN_COMMANDS = ("r", "return", "back", "返回", "上一步")
RETURN_COMMAND_TIP = "回复 r 来返回上一步"


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


def handle_idx_command(txt: str, items: Sequence[T], offset: int = -1) -> Optional[T]:
    if txt.isdigit() and (1 <= (idx := int(txt)) <= len(items)):
        return items[idx + offset]
    return None


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
            f"请在 {config.prompt_timeout} 秒内发送贴纸包 序号 / 代号 / 名称 进行选择"
            f"\n{COMMON_COMMANDS_TIP}",
        )
        .send()
    )

    illegal_finish = create_illegal_finisher()
    while True:
        txt, _ = await handle_prompt_common_commands(await prompt(""))
        if (pack := handle_idx_command(txt, pack_manager.packs)) or (
            pack := pack_manager.find_pack(txt)
        ):
            return pack
        await illegal_finish()
        await UniMessage("未找到对应贴纸包，请重新发送").send()


async def ensure_pack_available(pack: StickerPack):
    if pack.unavailable:
        await UniMessage(f"贴纸包 `{pack.slug}` 暂无法使用，自动退出操作").finish()


async def only_sticker_select(pack: StickerPack) -> StickerInfo:
    stickers = pack.manifest.resolved_stickers
    sticker_params = [
        model_copy(info.params, update={"text": f"{i}. {info.name}"})
        for i, info in enumerate(stickers, 1)
    ]

    async with exception_notify("图片绘制失败"):
        sticker_select_img = save_image(
            draw_sticker_grid_from_params(
                pack.manifest.sticker_grid.default_params,
                sticker_params,
                base_path=pack.base_path,
            ),
            skia.kJPEG,
        )

    await (
        UniMessage.image(raw=sticker_select_img)
        .text(
            f"以下是贴纸包 `{pack.manifest.name}` 中的贴纸"
            f"\n请发送 名称 / 序号 来选择"
            f"\n{COMMON_COMMANDS_TIP}",
        )
        .send()
    )
    while True:
        txt, _ = await handle_prompt_common_commands(await prompt(""))
        await ensure_pack_available(pack)
        if (sticker := handle_idx_command(txt, stickers)) or (
            sticker := next(
                (s for s in stickers if s.name.lower() == txt.lower()),
                None,
            )
        ):
            return sticker
        await UniMessage("未找到对应贴纸，请重新发送").send()


async def category_and_sticker_select(pack: StickerPack) -> StickerInfo:
    stickers_by_category = pack.manifest.resolved_stickers_by_category
    categories: list[str] = sorted(stickers_by_category.keys())

    category_sample_stickers: list[StickerParams] = [
        model_copy(stickers_by_category[c][0].params, update={"text": f"{i}. {c}"})
        for i, c in enumerate(categories, 1)
    ]

    async with exception_notify("图片绘制失败"):
        category_select_img = save_image(
            draw_sticker_grid_from_params(
                pack.manifest.sticker_grid.resolved_category_params,
                category_sample_stickers,
                base_path=pack.base_path,
            ),
            skia.kJPEG,
        )

    async def select_category() -> str:
        await (
            UniMessage.image(raw=category_select_img)
            .text(
                f"以下是该贴纸包内可用的贴纸分类"
                f"\n请发送 名称 / 序号 来选择"
                f"\n{COMMON_COMMANDS_TIP}",
            )
            .send()
        )
        illegal_finish = create_illegal_finisher()
        while True:
            txt, _ = await handle_prompt_common_commands(await prompt(""))
            await ensure_pack_available(pack)
            if (c := handle_idx_command(txt, categories)) or (
                c := next((c for c in categories if c.lower() == txt.lower()), None)
            ):
                return c
            await illegal_finish()
            await UniMessage("未找到对应分类，请重新发送").send()

    async def select_sticker(category: str) -> Optional[StickerInfo]:
        """category select requested when return None"""

        category_params = pack.manifest.sticker_grid.resolved_stickers_params
        grid_params = category_params.get(
            category,
            pack.manifest.sticker_grid.default_params,
        )
        stickers = stickers_by_category[category]

        all_stickers = pack.manifest.resolved_stickers
        sticker_ids = [all_stickers.index(s) + 1 for s in stickers]

        sticker_params = [
            model_copy(info.params, update={"text": f"{i}. {info.name}"})
            for i, info in zip(sticker_ids, stickers)
        ]
        async with exception_notify("图片绘制失败"):
            sticker_select_img = save_image(
                draw_sticker_grid_from_params(
                    grid_params,
                    sticker_params,
                    pack.base_path,
                ),
                skia.kJPEG,
            )

        await (
            UniMessage.image(raw=sticker_select_img)
            .text(
                f"以下是分类 `{category}` 中的贴纸"
                f"\n请发送 名称 / 序号 来选择"
                f"\n{COMMON_COMMANDS_TIP}、{RETURN_COMMAND_TIP}",
            )
            .send()
        )

        illegal_finish = create_illegal_finisher()
        while True:
            txt, _ = await handle_prompt_common_commands(await prompt(""))
            await ensure_pack_available(pack)
            if txt.lower() in RETURN_COMMANDS:
                return None
            if txt.isdigit() and (i := int(txt)) in sticker_ids:
                return all_stickers[i - 1]
            if s := next((s for s in stickers if s.name.lower() == txt.lower()), None):
                return s
            await illegal_finish()
            await UniMessage("未找到对应贴纸，请重新发送").send()

    while True:
        category = await select_category()
        if sticker := await select_sticker(category):
            return sticker


async def sticker_select(pack: StickerPack) -> StickerInfo:
    if pack.manifest.sticker_grid.disable_category_select:
        return await only_sticker_select(pack)
    return await category_and_sticker_select(pack)


async def prompt_sticker_text() -> str:
    await UniMessage("请发送你想要写在贴纸上的文本").send()
    illegal_finish = create_illegal_finisher()
    while True:
        txt, _ = await handle_prompt_common_commands(await prompt(""))
        if txt:
            return txt
        await illegal_finish()
        await UniMessage("文本不能为空，请重新发送").send()


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


async def find_dict_value_with_notify(d: dict[Any, T], key: Any, msg: str) -> T:
    if key not in d:
        await UniMessage(msg).finish()
    return d[key]


def resolve_relative_num(val: str, base: float) -> float:
    if not val.startswith("^"):
        return float(val)
    return base + float(val.lstrip("^"))


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

    if q_sticker.result:
        if q_sticker.result.isdigit():
            sticker = pack.manifest.resolved_stickers[int(q_sticker.result) - 1]
        else:
            sticker = pack.manifest.find_sticker_by_name(q_sticker.result)
    else:
        sticker = await sticker_select(pack)
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
@m_cls.assign("$main")
async def _(m: AlconnaMatcher):
    await m.finish(alc.get_help())
