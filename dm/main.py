from asyncio import sleep
from contextlib import suppress

from solgram import log
from solgram.enums import Client, Message
from solgram.listener import listener
from solgram.utils import lang


@listener(
    outgoing=True,
    command="dm",
    need_admin=True,
    description="批量删除当前对话中自己发送的消息",
    parameters="[数量]",
)
async def self_prune(bot: Client, message: Message):
    msgs = []
    count_buffer = 0
    offset = 0
    if message.reply_to_message:
        offset = message.reply_to_message.id
    if len(message.parameter) == 0:
        count = 1
    elif len(message.parameter) == 1:
        try:
            count = int(message.parameter[0])
        except ValueError:
            await message.edit(lang("arg_error"))
            return
    else:
        await message.edit(lang("arg_error"))
        return
    await message.delete()

    async for msg in bot.get_chat_history(message.chat.id, limit=100):
        if count_buffer == count:
            break
        if msg.from_user and msg.from_user.is_self:
            await attempt_edit_message(msg)
            msgs.append(msg.id)
            count_buffer += 1
            if len(msgs) == 100:
                await bot.delete_messages(message.chat.id, msgs)
                msgs = []

    async for msg in bot.search_messages(message.chat.id, from_user="me", offset=offset):
        if count_buffer == count:
            break
        await attempt_edit_message(msg)
        msgs.append(msg.id)
        count_buffer += 1
        if len(msgs) == 100:
            await bot.delete_messages(message.chat.id, msgs)
            msgs = []

    if msgs:
        await bot.delete_messages(message.chat.id, msgs)

    await log(
        f"{lang('prune_hint1')}{lang('sp_hint')} {count_buffer} / {count} {lang('prune_hint2')}"
    )

    with suppress(ValueError):
        notification = await send_prune_notify(bot, message, count_buffer, count)
        await sleep(1)
        await notification.delete()


async def attempt_edit_message(msg: Message):
    try:
        await msg.edit("<code>***此条信息已删除</code>")
    except Exception as e:
        await log(f"Error editing message {msg.id}: {e}")


async def send_prune_notify(
    bot: Client, message: Message, count_buffer: int, count: int
):
    return await bot.send_message(
        message.chat.id,
        f"{lang('spn_deleted')} {count_buffer} / {count} {lang('prune_hint2')}",
        message_thread_id=message.message_thread_id,
    )

