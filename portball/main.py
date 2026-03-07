from datetime import datetime, timedelta
import re
from typing import Union  # 添加导入

from pyrogram.enums import ChatType
from pyrogram.errors import UserAdminInvalid, BadRequest, ChatAdminRequired
from pyrogram.types import ChatPermissions

from solgram.listener import listener
from solgram.enums import Client, Message


def parse_duration(time_str: str) -> Union[timedelta, None]:  # 修改此行
    match = re.match(r"^(\d+)([mhdwMHDW])$", time_str.strip())
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    unit = unit.lower()
    if unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    elif unit == "w":
        return timedelta(weeks=value)
    return None


@listener(
    command="portball",
    outgoing=True,
    need_admin=False,
    description="回复你要临时禁言的人的消息，支持时间单位例如 30m / 2h / 1d / 1w",
    parameters="[理由]|<时间>",
)
async def portball(bot: Client, message: Message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        edit_message = await message.edit_text("你好蠢诶，又不是群组，怎么禁言啦！")
        await edit_message.delay_delete()
        await message.delay_delete()
        return

    reply_to_message = message.reply_to_message
    if not reply_to_message or not reply_to_message.from_user:
        edit_message = await message.edit_text("你好蠢诶，都没有回复人，我哪知道你要搞谁的事情……")
        await edit_message.delay_delete()
        await message.delay_delete()
        return

    from_user = reply_to_message.from_user
    if from_user.is_self:
        edit_message = await message.edit_text("无法禁言自己。")
        await edit_message.delay_delete()
        return

    reason = ""
    duration = None

    if len(message.parameter) == 1:
        duration = parse_duration(message.parameter[0])
    elif len(message.parameter) == 2:
        reason = message.parameter[0]
        duration = parse_duration(message.parameter[1])

    if not duration:
        edit_message = await message.edit_text("出错了呜呜呜 ~ 无效的时间格式（例如 30m、1h、2d、1w）")
        await edit_message.delay_delete()
        return

    if duration.total_seconds() < 60:
        edit_message = await message.edit_text("诶呀不要小于1分钟啦")
        await edit_message.delay_delete()
        return

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            from_user.id,
            ChatPermissions(),
            datetime.now() + duration,
        )
    except (UserAdminInvalid, ChatAdminRequired):
        await bot.send_message(message.chat.id, "错误：该操作需要管理员权限")
        await message.delay_delete()
        return
    except BadRequest:
        await message.edit_text("出错了呜呜呜 ~ 执行封禁时出错")
        await message.delay_delete()
        return

    full_name = f"{from_user.first_name or ''} {from_user.last_name or ''}".strip() or str(from_user.id)
    text = f"[{full_name}](tg://user?id={from_user.id}) "
    if reason:
        text += f"由于 {reason} "

    # 显示友好的时间单位
    total_minutes = int(duration.total_seconds() / 60)
    if total_minutes % (60 * 24 * 7) == 0:
        text += f"被塞了 {total_minutes // (60 * 24 * 7)} 周口球.\n"
    elif total_minutes % (60 * 24) == 0:
        text += f"被塞了 {total_minutes // (60 * 24)} 天口球.\n"
    elif total_minutes % 60 == 0:
        text += f"被塞了 {total_minutes // 60} 小时口球.\n"
    else:
        text += f"被塞了 {total_minutes} 分钟口球.\n"

    text += "到期自动拔出, 无后遗症."

    await bot.send_message(message.chat.id, text)
    await message.safe_delete()
