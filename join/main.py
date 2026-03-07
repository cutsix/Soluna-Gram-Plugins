# -*- coding: UTF-8 -*-
from pyrogram import Client
from solgram.listener import listener
from solgram.utils import Message, alias_command
from pyrogram.enums import ChatMemberStatus, ParseMode
from solgram import logs
from datetime import datetime

cmd = alias_command('join')

@listener(command=f"{cmd}", groups_only=True, description="查询用户入群时间\n\n使用方法：回复一条消息并使用此命令")
async def fn(bot: Client, message: Message):
    if not message.reply_to_message:
        await message.edit("请回复一条消息来查询用户的入群时间。")
        return

    user = message.reply_to_message.from_user
    if not user:
        await message.edit("无法获取用户信息。")
        return

    try:
        chat_member = await bot.get_chat_member(message.chat.id, user.id)
        joined_date = chat_member.joined_date
        
        if joined_date:
            formatted_date = joined_date.strftime("%Y-%m-%d %H:%M:%S")
            await message.edit(f"用户 {user.mention()} 的入群时间是：{formatted_date}")
        else:
            await message.edit(f"无法获取用户 {user.mention()} 的入群时间。")
    except Exception as e:
        logs.error(f"无法获取用户 {user.id} 的入群时间：{e}")
        await message.edit(f"获取用户 {user.mention()} 的入群时间时发生错误：{e}")