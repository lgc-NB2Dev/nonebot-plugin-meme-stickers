from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any, NoReturn, Optional, TypeVar

import skia
from arclet.alconna import Alconna, CommandMeta
from cookit.pyd import model_copy
from nonebot import logger
from nonebot.adapters import Message as BaseMessage
from nonebot.exception import NoneBotException
from nonebot_plugin_alconna import UniMessage, on_alconna
from nonebot_plugin_waiter import prompt

from ..config import config
from ..consts import AUTHOR, DESCRIPTION
from ..draw.grid import (
    draw_sticker_grid_from_packs,
    draw_sticker_grid_from_params,
)
from ..draw.tools import save_image
from ..sticker_pack import pack_manager
from ..sticker_pack.models import StickerInfo, StickerParams
from ..sticker_pack.pack import StickerPack

T = TypeVar("T")

alc = Alconna(
    "meme-stickers",
    meta=CommandMeta(description=DESCRIPTION, author=AUTHOR),
)
m_cls = on_alconna(
    alc,
    aliases={"stickers"},
    skip_for_unmatch=False,
    auto_send_output=True,
    use_cmd_start=True,
    # use_cmd_sep=True,
)

EXIT_COMMANDS = ("0", "e", "exit", "q", "quit", "取消", "退出")
COMMON_COMMANDS_TIP = "另外可以回复 0 来退出"

RETURN_COMMANDS = ("r", "return", "b", "back", "返回", "上一步")
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
    await UniMessage("已退出操作").finish()


async def timeout_finish() -> NoReturn:
    await UniMessage("等待超时，已退出操作").finish()


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


def handle_idx_command(txt: str, items: Sequence[T]) -> Optional[T]:
    if txt.isdigit() and (1 <= (idx := int(txt)) <= len(items)):
        return items[idx - 1]
    return None


async def sticker_pack_select(include_unavailable: bool = False) -> StickerPack:
    packs = pack_manager.packs if include_unavailable else pack_manager.available_packs
    if not packs:
        await UniMessage("当前无可用贴纸包").finish()

    async with exception_notify("图片绘制失败"):  # fmt: skip
        pack_list_img = save_image(
            draw_sticker_grid_from_packs(packs),
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
        txt, _ = await handle_prompt_common_commands(
            await prompt("", timeout=config.prompt_timeout),
        )
        if (pack := handle_idx_command(txt, packs)) or (
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
            f"以上是贴纸包 `{pack.manifest.name}` 中的贴纸"
            f"\n请发送 名称 / 序号 来选择"
            f"\n{COMMON_COMMANDS_TIP}",
        )
        .send()
    )
    while True:
        txt, _ = await handle_prompt_common_commands(
            await prompt("", timeout=config.prompt_timeout),
        )
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
                f"以上是该贴纸包内可用的贴纸分类"
                f"\n请发送 名称 / 序号 来选择"
                f"\n{COMMON_COMMANDS_TIP}",
            )
            .send()
        )
        illegal_finish = create_illegal_finisher()
        while True:
            txt, _ = await handle_prompt_common_commands(
                await prompt("", timeout=config.prompt_timeout),
            )
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
                f"以上是分类 `{category}` 中的贴纸"
                f"\n请发送 名称 / 序号 来选择"
                f"\n{COMMON_COMMANDS_TIP}、{RETURN_COMMAND_TIP}",
            )
            .send()
        )

        illegal_finish = create_illegal_finisher()
        while True:
            txt, _ = await handle_prompt_common_commands(
                await prompt("", timeout=config.prompt_timeout),
            )
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


async def find_dict_value_with_notify(d: dict[Any, T], key: Any, msg: str) -> T:
    if key not in d:
        await UniMessage(msg).finish()
    return d[key]
