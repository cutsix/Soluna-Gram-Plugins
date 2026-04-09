from io import BytesIO

from PIL import Image

from solgram.listener import listener
from solgram.enums import Message, Client


@listener(
    command="stp",
    description="将回复的静态贴纸转换为图片",
    parameters="（带任意参数时以原图文档发送）",
)
async def sticker_to_pic(bot: Client, message: Message):
    reply = message.reply_to_message
    if not reply or not reply.sticker:
        return await message.edit("请回复一个静态贴纸")
    if reply.sticker.is_animated or reply.sticker.is_video:
        return await message.edit("请回复一个静态贴纸")

    try:
        sticker_file = await bot.download_media(reply, in_memory=True)
        message = await message.edit("正在转换...\n███████70%")
        with Image.open(sticker_file) as image:
            output = BytesIO()
            output.name = "sticker.png"
            image.save(output, format="PNG")
        output.seek(0)
    except Exception as exc:
        return await message.edit(f"转换失败：{exc}")

    if message.arguments:
        await reply.reply_document(output, quote=True)
    else:
        await reply.reply_photo(output, quote=True)

    await message.safe_delete()
