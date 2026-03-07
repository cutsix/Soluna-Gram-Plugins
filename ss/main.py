import pickle
from pyrogram import Client, enums
import re
import random
import asyncio
from os.path import exists
from solgram.listener import listener
from pyrogram.types import InputMediaPhoto
from solgram.services import client as requests
from solgram.enums import Message, Client

# 添加频道分组
channel_groups = {
    "default": [
        "sunmoonvedio",
        "ndggboomle",
    ]
}

@listener(command="ss", description="我才不喜欢这个")
async def lsp(client: Client, message: Message):
    try:
        message_thread_id = message.reply_to_top_message_id
        fromUserId = message.from_user.id
        me = await client.get_me()
        userId = me.id
        isSelf = fromUserId == userId

        # 使用默认频道组
        channels = channel_groups["default"]

        # 随机选择频道
        channel = random.choice(channels)

        chat_id = message.chat.id
        reply = message.reply_to_message_id if message.reply_to_message_id else None

        bot_message = await message.edit(f'[我才不喜欢...]', disable_web_page_preview=True)

        count = await client.search_messages_count(chat_id=channel, filter=enums.MessagesFilter.VIDEO)
        if count < 1:
            m = await bot_message.edit(f'[找不到视频]', disable_web_page_preview=True)
            await asyncio.sleep(3)
            await message.safe_delete()
            await m.safe_delete()
            return

        # 持续尝试直到找到合适的视频
        attempt = 0
        max_attempts = 8  # 最大尝试次数
        while attempt < max_attempts:
            attempt += 1
            random_offset = random.randint(1, count)
            await bot_message.edit(f'[我才不喜欢 {random_offset}/{count}... ]', disable_web_page_preview=True)

            found_video = False
            async for m in client.search_messages(chat_id=channel, offset=random_offset, limit=1, filter=enums.MessagesFilter.VIDEO):
                # 检查是否是视频
                if not m.video:
                    continue

                try:
                    video_duration = m.video.duration
                    if video_duration > 180:  # 检查视频时长是否超过3分钟
                        continue

                    # 检查视频文件大小
                    if m.video.file_size and m.video.file_size > 50 * 1024 * 1024:  # 50MB
                        continue

                    # 使用 file_id
                    video = m.video.file_id

                    if message.reply_to_message:
                        await message.reply_to_message.reply_video(
                            video,
                            caption=f'[我才不喜欢 {random_offset}/{count}]'
                        )
                    else:
                        await message.reply_video(
                            video,
                            caption=f'[我才不喜欢 {random_offset}/{count}]',
                            quote=False,
                            reply_to_message_id=message.reply_to_top_message_id
                        )

                    found_video = True
                    break
                except Exception as e:
                    continue

            if found_video:
                await bot_message.safe_delete()
                await message.safe_delete()
                return

            # 短暂等待后继续尝试
            await asyncio.sleep(1)

        # 如果尝试次数用完仍未找到合适的视频
        if not found_video:
            m = await bot_message.edit(f'[尝试了 {max_attempts} 次，未找到符合条件的视频]', disable_web_page_preview=True)
            await asyncio.sleep(3)
            await message.safe_delete()
            await m.safe_delete()

    except Exception as e:
        m = await message.edit(f"失败 ~ {e}")
        await asyncio.sleep(3)
        await message.safe_delete()
        await m.safe_delete()
