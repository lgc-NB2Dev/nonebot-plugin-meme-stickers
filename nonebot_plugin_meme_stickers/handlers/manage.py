import asyncio
from typing import Optional

import skia
from arclet.alconna import Args, MultiVar, Option, store_true
from cookit.nonebot.alconna import RecallContext
from nonebot import logger
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from nonebot_plugin_alconna import AlconnaMatcher, Query, UniMessage
from nonebot_plugin_waiter import prompt

from ..config import config
from ..consts import PREVIEW_CACHE_DIR_NAME
from ..draw.grid import draw_sticker_grid_from_packs
from ..draw.pack_list import draw_sticker_pack_grid
from ..draw.tools import save_image
from ..sticker_pack import pack_manager
from ..sticker_pack.hub import (
    fetch_checksum,
    fetch_hub_and_packs,
    temp_sticker_card_params,
)
from ..sticker_pack.pack import StickerPack
from ..utils.file_source import create_req_sem
from ..utils.operation import OpInfo, OpIt, format_op
from .shared import (
    COMMON_COMMANDS_TIP,
    alc,
    exception_notify,
    find_packs_with_notify,
    handle_prompt_common_commands,
    m_cls,
)

alc.subcommand(
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
    help_text="查看本地或 Hub 上的贴纸包列表（仅超级用户）",
    alias=["ls", "ll", "l"],
)


@m_cls.dispatch("~list", permission=SUPERUSER).handle()
async def _(
    q_online: Query[bool] = Query("~online.value", default=False),
    q_no_unavailable: Query[bool] = Query("~no-unavailable.value", default=False),
):
    if q_online.result:
        async with exception_notify("从 Hub 获取贴纸包信息失败"):
            hub, manifests = await fetch_hub_and_packs()
        if not manifests:
            await UniMessage("Hub 上无可用贴纸包").finish()
        async with exception_notify("从 Hub 获取贴纸包信息失败"):
            sem = create_req_sem()
            checksums = dict(
                zip(
                    (x.slug for x in hub),
                    await asyncio.gather(
                        *(fetch_checksum(x.source, sem=sem) for x in hub),
                    ),
                ),
            )
        async with exception_notify("下载用于预览的贴纸失败"):
            params = await temp_sticker_card_params(
                config.data_dir / PREVIEW_CACHE_DIR_NAME,
                hub,
                manifests,
                checksums,
            )
        async with exception_notify("图片绘制失败"):
            pic = save_image(draw_sticker_pack_grid(params), skia.kJPEG)
        await UniMessage.image(raw=pic).text("以上为 Hub 中可用的贴纸包列表").finish()

    packs = (
        pack_manager.available_packs if q_no_unavailable.result else pack_manager.packs
    )
    if not packs:
        await UniMessage("当前无可用贴纸包").finish()
    async with exception_notify("图片绘制失败"):  # fmt: skip
        pic = save_image(
            draw_sticker_grid_from_packs(packs),
            skia.kJPEG,
        )
    await UniMessage.image(raw=pic).text("以上为本地可用的贴纸包列表").finish()


alc.subcommand(
    "reload",
    help_text="重新加载本地贴纸包（仅超级用户）",
)


@m_cls.dispatch("~reload", permission=SUPERUSER).handle()
async def _(m: AlconnaMatcher):
    async with exception_notify("出现未知错误"):
        op = pack_manager.reload()
    await m.finish(f"已重新加载本地贴纸包\n{format_op(op)}")


alc.subcommand(
    "install",
    Args["packs#要下载的贴纸包代号", MultiVar(str, "+")],
    help_text="从 Hub 下载贴纸包（仅超级用户）",
    alias=["ins", "download", "add"],
)


@m_cls.dispatch("~install", permission=SUPERUSER).handle()
async def _(
    m: AlconnaMatcher,
    q_packs: Query[list[str]] = Query("~packs"),
):
    async with RecallContext() as ctx, exception_notify("出现未知错误"):
        await ctx.send("正在下载贴纸包，请稍候")
        op = await pack_manager.install(q_packs.result)
    await m.finish(
        f"贴纸包安装结果："
        f"\n{format_op(op)}"
        f"\n建议检查后台输出，如提示贴纸包有额外字体请按提示手动安装",
    )


alc.subcommand(
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
    help_text="从 Hub 更新贴纸包（仅超级用户）",
    alias=["up", "upgrade"],
)


@m_cls.dispatch("~update", permission=SUPERUSER).handle()
async def _(
    m: AlconnaMatcher,
    q_packs: Query[Optional[list[str]]] = Query("~packs", None),
    q_all: Query[bool] = Query("~all.value", default=False),
    q_force: Query[bool] = Query("~force.value", default=False),
):
    if not q_packs.result and not q_all.result:
        await m.finish("请指定要更新的贴纸包或使用选项 -a / --all 更新所有贴纸包")
    async with RecallContext() as ctx, exception_notify("出现未知错误"):
        await ctx.send("正在下载贴纸包，请稍候")
        op = await pack_manager.update(q_packs.result or None, q_force.result)
    await m.finish(
        f"贴纸包更新结果："
        f"\n{format_op(op)}"
        f"\n建议检查后台输出，如提示贴纸包有额外字体请按提示手动安装",
    )


alc.subcommand(
    "delete",
    Args["packs#要删除的贴纸包 ID / 代号 / 名称", MultiVar(str, "+")],
    Option(
        "-y|--yes",
        action=store_true,
        help_text="跳过确认提示",
    ),
    help_text="删除本地贴纸包（仅超级用户）",
    alias=["del", "remove", "rm"],
)


@m_cls.dispatch("~delete", permission=SUPERUSER).handle()
async def _(
    m: AlconnaMatcher,
    q_packs: Query[list[str]] = Query("~packs"),
    q_yes: Query[bool] = Query("~yes.value", default=False),
):
    packs = await find_packs_with_notify(*q_packs.result)
    if q_yes.result:
        op = OpInfo[StickerPack]()
        for pack in packs:
            try:
                pack_manager.delete(pack)
            except Exception as e:
                logger.exception(f"Failed to delete pack {pack.slug}")
                op.failed.append(OpIt(pack, exc=e))
            else:
                op.succeed.append(OpIt(pack))
        await m.finish(f"贴纸包删除结果：\n{format_op(op)}")

    for pack in packs:
        async with RecallContext() as ctx:
            await ctx.send(
                f"是否真的要删除贴纸包 `{pack.slug}`？"
                f"输入 Y 确定，输入其他内容取消。"
                f"{COMMON_COMMANDS_TIP}",
            )
            ans, _ = await handle_prompt_common_commands(
                await prompt("", timeout=config.prompt_timeout),
            )
            if ans.lower() != "y":
                await m.send(f"已取消贴纸包 `{pack.slug}` 删除操作")
                continue

        try:
            pack_manager.delete(pack)
        except Exception:
            logger.exception(f"Failed to delete pack {pack.slug}")
            await UniMessage(f"删除贴纸包 `{pack.slug}` 失败").send()
        else:
            await UniMessage(f"已删除贴纸包 `{pack.slug}`").send()


alc.subcommand(
    "disable",
    Args["packs#要删除的贴纸包 ID / 代号 / 名称", MultiVar(str, "+")],
    help_text="禁用本地贴纸包（仅超级用户）",
).subcommand(
    "enable",
    Args["packs#要删除的贴纸包 ID / 代号 / 名称", MultiVar(str, "+")],
    help_text="启用本地贴纸包（仅超级用户）",
)


@m_cls.dispatch("~enable", permission=SUPERUSER, state={"m_disable": False}).handle()
@m_cls.dispatch("~disable", permission=SUPERUSER, state={"m_disable": True}).handle()
async def _(
    m: AlconnaMatcher,
    state: T_State,
    q_packs: Query[list[str]] = Query("~packs"),
):
    packs = await find_packs_with_notify(*q_packs.result, include_unavailable=True)

    disable: bool = state["m_disable"]
    type_tip = "禁用" if disable else "启用"

    opt = OpInfo[StickerPack]()
    for pack in packs:
        if pack.config.disabled == disable:
            opt.skipped.append(OpIt(pack, f"贴纸包已被{type_tip}"))
            continue
        try:
            pack.config.disabled = disable
            pack.save_config()
        except Exception as e:
            logger.exception(
                f"Failed to {'disable' if disable else 'enable'} pack {pack.slug}",
            )
            opt.failed.append(OpIt(pack, exc=e))
        else:
            opt.succeed.append(OpIt(pack))

    await m.finish(f"已{type_tip}以下贴纸包：\n{format_op(opt)}")
