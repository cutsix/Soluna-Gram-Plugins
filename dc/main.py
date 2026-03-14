# -*- coding: UTF-8 -*-

from pyrogram import Client
from pyrogram.enums import ParseMode

from solgram.listener import listener
from solgram.enums import Message

DC_BUCKETS = ("1", "2", "3", "4", "5")


def format_user_dc(dc_id) -> str:
    return f"DC{dc_id}" if dc_id else "无法查询! 您是否设置了头像呢？我是否可以看到你的头像呢？"


def format_ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 2)


@listener(command="dc", description="查看本群 DC 分布，或查看你回复的人在哪个 DC")
async def dc(client: Client, message: Message):
    message = await message.edit("Please wait...")

    if message.reply_to_message:
        user = message.reply_to_message.from_user or message.reply_to_message.sender_chat
        if not user:
            await message.edit("出错啦！")
            return
        await message.edit(f"您所在的位置: {format_user_dc(getattr(user, 'dc_id', None))}")
        return

    if message.chat.id > 0:
        try:
            user = await client.get_users(message.chat.id)
        except Exception:
            await message.edit("出错啦！")
            return
        await message.edit(f"他所在的位置: {format_user_dc(getattr(user, 'dc_id', None))}")
        return

    force = (message.arguments or "").strip().lower() == "force"
    try:
        count = await client.get_chat_members_count(message.chat.id)
    except Exception as exc:
        await message.edit(f"获取群成员数量失败: {exc}")
        return

    if count >= 10000 and not force:
        await message.edit(
            "太...太多人了... 我会...会...会坏掉的...\n\n"
            "如果您执意要运行的话，您可以使用指令 `,dc force`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    users = 0
    bots = 0
    deleted = 0
    dc_ids = {bucket: 0 for bucket in DC_BUCKETS}
    dc_ids["failed"] = 0

    try:
        async for member in client.get_chat_members(message.chat.id, limit=9999):
            user = member.user
            if not user:
                continue
            if user.is_bot:
                bots += 1
                continue
            if user.is_deleted:
                deleted += 1
                continue
            users += 1
            dc_id = str(getattr(user, "dc_id", "") or "")
            if dc_id in dc_ids:
                dc_ids[dc_id] += 1
            else:
                dc_ids["failed"] += 1
    except Exception as exc:
        await message.edit(f"统计失败: {exc}")
        return

    notice = (
        "\n\n***请注意: 由于 TG 限制，我们只能遍历前 10k 人，此次获得的数据并不完整***"
        if count >= 10000
        else ""
    )

    await message.edit(
        f"""DC:
> DC1用户: **{dc_ids["1"]}** 占比: **{format_ratio(dc_ids["1"], users)}%**
> DC2用户: **{dc_ids["2"]}** 占比: **{format_ratio(dc_ids["2"], users)}%**
> DC3用户: **{dc_ids["3"]}** 占比: **{format_ratio(dc_ids["3"], users)}%**
> DC4用户: **{dc_ids["4"]}** 占比: **{format_ratio(dc_ids["4"], users)}%**
> DC5用户: **{dc_ids["5"]}** 占比: **{format_ratio(dc_ids["5"], users)}%**
> 无法获取在哪个 DC 的用户: **{dc_ids["failed"]}**
> 已自动过滤掉 **{bots}** 个 Bot, **{deleted}** 个 死号
> 统计用户总数: **{users}**{notice}""",
        parse_mode=ParseMode.MARKDOWN,
    )
