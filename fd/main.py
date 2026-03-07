import asyncio
from pyrogram.errors import Forbidden, FloodWait
from solgram.listener import listener
from solgram.enums import Client, Message
from solgram.utils import alias_command, lang
from solgram.single_utils import sqlite

@listener(
    command="r",
    description="复读鸡，叽叽复叽叽，叽叽叽。\n`,fd on_limit` - 开启复读次数限制\n`,fd off_limit` - 关闭复读次数限制",
    parameters="<次数(可选)|on_limit|off_limit>",
)
async def fd(bot: Client, message: Message):
    """复读指定消息指定次数"""
    try:
        # 处理开关命令
        if len(message.parameter) == 1:
            if message.parameter[0] == "off_limit":
                sqlite["fd_unlimited"] = True
                await message.edit("已关闭复读次数限制")
                await asyncio.sleep(3)
                return await message.delete()
            elif message.parameter[0] == "on_limit":
                sqlite["fd_unlimited"] = False
                await message.edit("已开启复读次数限制（最大3次）")
                await asyncio.sleep(3)
                return await message.delete()

        if not message.reply_to_message:
            prompt_msg = await message.edit("请回复一条消息以复读")
            await asyncio.sleep(3)
            return await prompt_msg.delete()

        count = 1
        if len(message.parameter) > 0:
            try:
                count = int(message.parameter[0])
                # 检查是否启用了无限制模式
                if not sqlite.get("fd_unlimited", False):  # 默认返回 False，即默认开启限制
                    if count <= 0 or count > 3:  # 默认限制最大3次
                        prompt_msg = await message.edit("❌ 复读次数默认为1到3次\n`,fd off_limit`  解除限制")
                        await asyncio.sleep(8)
                        return await prompt_msg.delete()
                elif count <= 0:  # 无限制模式下只检查是否大于0
                    prompt_msg = await message.edit("复读次数应大于0")
                    await asyncio.sleep(3)
                    return await prompt_msg.delete()
            except ValueError:
                prompt_msg = await message.edit("请输入一个有效的复读次数")
                await asyncio.sleep(3)
                return await prompt_msg.delete()

        reply = message.reply_to_message
        await message.delete()

        for _ in range(count):
            try:
                await reply.copy(
                    message.chat.id,
                    message_thread_id=message.message_thread_id
                )
            except Exception as e:
                error_msg = await bot.send_message(
                    message.chat.id,
                    f"❌复读消息时发生错误: {str(e)}"
                )
                await asyncio.sleep(3)
                await error_msg.delete()
                break

    except Exception as e:
        error_msg = await message.edit(f"[FD_ERROR]: {e}")
        await asyncio.sleep(3)
        await error_msg.delete()


@listener(
    command="res",
    description="复读转发从回复消息开始的 n 条消息（包含回复消息）\n用法：回复一条消息后使用 ,res 或 ,res <数字>",
    parameters="<数字(可选，默认1，最大100)>",
)
async def res(bot: Client, message: Message):
    """复读转发从回复消息开始的 n 条消息（包含回复消息）"""
    try:
        # 检查是否回复了消息
        if not message.reply_to_message:
            prompt_msg = await message.edit("请回复一条消息以复读")
            await asyncio.sleep(3)
            return await prompt_msg.delete()

        reply = message.reply_to_message
        chat_id = message.chat.id

        # 解析参数获取 n
        n = 1  # 默认值
        if message.arguments:
            try:
                n = int(message.arguments.strip())
                if n <= 0:
                    prompt_msg = await message.edit("❌ 复读数量必须大于 0")
                    await asyncio.sleep(3)
                    return await prompt_msg.delete()
                if n > 100:
                    prompt_msg = await message.edit("❌ 复读数量最大为 100")
                    await asyncio.sleep(3)
                    return await prompt_msg.delete()
            except ValueError:
                prompt_msg = await message.edit("❌ 请输入有效的数字")
                await asyncio.sleep(3)
                return await prompt_msg.delete()

        # 计算目标消息 id 列表（从回复消息开始，包含回复消息及其下方共 n 条）
        target_ids = [reply.id + i for i in range(n)]

        # 批量获取消息
        try:
            messages_to_forward = await bot.get_messages(chat_id, target_ids)
        except Exception as e:
            prompt_msg = await message.edit(f"❌ 获取消息失败: {str(e)}")
            await asyncio.sleep(3)
            return await prompt_msg.delete()

        # 确保返回的是列表
        if not isinstance(messages_to_forward, list):
            messages_to_forward = [messages_to_forward]

        # 过滤有效消息（非空、非已删除）
        valid_messages = [
            msg for msg in messages_to_forward
            if msg and not msg.empty
        ]

        if not valid_messages:
            prompt_msg = await message.edit("❌ 没有找到可复读的消息（可能已被删除）")
            await asyncio.sleep(3)
            return await prompt_msg.delete()

        # 删除命令消息
        await message.safe_delete()

        # 检查是否有内容保护
        has_protection = message.chat.has_protected_content

        # 按顺序转发/复制每条消息
        for msg in valid_messages:
            try:
                if not has_protection:
                    # 未保护：使用转发
                    await msg.forward(
                        chat_id,
                        message_thread_id=message.message_thread_id
                    )
                else:
                    # 受保护：使用复制
                    await msg.copy(
                        chat_id,
                        message_thread_id=message.message_thread_id
                    )
            except (Forbidden, FloodWait) as e:
                # 转发/复制失败，静默跳过
                break
            except Exception as e:
                # 其他异常，静默跳过
                continue

    except Exception as e:
        error_msg = await message.edit(f"[RES_ERROR]: {e}")
        await asyncio.sleep(3)
        await error_msg.delete()
