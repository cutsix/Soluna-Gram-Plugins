import pickle
from pyrogram import Client, enums
import random
import asyncio
from os.path import exists
from solgram.listener import listener
from solgram.enums import Message, Client

# 频道分组
channel_groups = {
    "default": [
        "botmzt",
        "titswiki_sfw",
        "meizitu3",
        "meinv00857",
        "EnjoyJK",
        "ZZDXJJ"
    ],
    "NSFW": [
        # NSFW 频道组
        "FFFLLJJJ",
        "meinv999",
    ]
}

@listener(command="sst", description="我才不喜欢，添加 `18` 将发送 **NSFW内容**（自动启用防剧透）",
         parameters="[18]")
async def sst(client: Client, message: Message):
    try:
        # 解析参数
        arguments = message.arguments.upper().strip()
        params = arguments.split()

        is_nsfw = "18" in params
        is_spoiler = bool(arguments)

        # 根据参数选择频道组
        channel_group = "NSFW" if is_nsfw else "default"
        channels = channel_groups[channel_group]

        # 随机选择频道
        channel = random.choice(channels)

        # 发送状态消息
        bot_message = await message.edit("[获取图片中...]", disable_web_page_preview=True)

        # 获取频道内图片总数
        count = await client.search_messages_count(chat_id=channel, filter=enums.MessagesFilter.PHOTO)
        if count < 1:
            m = await bot_message.edit("[未找到图片]")
            await asyncio.sleep(3)
            await message.safe_delete()
            await m.safe_delete()
            return

        # 寻找图片
        found_photo = False
        attempts = 0

        while not found_photo:
            # 随机选择一个偏移量
            random_offset = random.randint(1, count)
            await bot_message.edit(f"[获取图片中... {random_offset}/{count}]")

            # 搜索消息
            async for m in client.search_messages(chat_id=channel, offset=random_offset, limit=1, filter=enums.MessagesFilter.PHOTO):
                found_photo = True
                if is_spoiler:
                    photo = await client.download_media(m.photo.file_id, in_memory=True)
                else:
                    photo = m.photo.file_id

                if message.reply_to_message:
                    await message.reply_to_message.reply_photo(
                        photo,
                        caption=f"[我才不喜欢 {random_offset}/{count}]",
                        has_spoiler=is_spoiler
                    )
                else:
                    await message.reply_photo(
                        photo,
                        caption=f"[我才不喜欢 {random_offset}/{count}]",
                        has_spoiler=is_spoiler,
                        quote=False,
                        reply_to_message_id=message.reply_to_top_message_id
                    )

            # 如果没有找到图片，更新状态消息并继续尝试
            if not found_photo:
                attempts += 1
                await bot_message.edit(f"[尝试中... 第{attempts}次尝试]")
                await asyncio.sleep(1)  # 短暂延迟后再次尝试

        # 发送成功后删除状态消息和原命令
        await bot_message.safe_delete()
        await message.safe_delete()

    except Exception as e:
        m = await message.edit(f"发送失败 ~ {e}")
        await asyncio.sleep(3)
        await message.safe_delete()
        await m.safe_delete()

