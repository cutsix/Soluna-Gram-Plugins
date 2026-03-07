
from solgram.listener import listener
from solgram import log
from solgram.enums import Client, Message
from solgram.utils import lang, pip_install
from contextlib import suppress
from asyncio import sleep
import os

from pathlib import Path
import asyncio
from datetime import datetime, timedelta
from pyrogram.errors import FloodWait, MessageEditTimeExpired
from pyrogram.enums import ChatType, MessageMediaType
from pyrogram.types import InputMediaPhoto

pip_install("aiohttp")

import aiohttp

# 配置常量
CONFIG = {
    "TROLL_IMAGE_URL": "https://raw.githubusercontent.com/cutsix/pgp/main/image/dme_troll_image.jpg",
    "TROLL_IMAGE_PATH": "plugins/dme/dme_troll_image.png",
    "BATCH_SIZE": 50,
    "EDIT_BATCH_SIZE": 20,
    "EDIT_CONCURRENCY": 5,
    "SEARCH_LIMIT": 100,
    "MAX_SEARCH_MULTIPLIER": 10,
    "MIN_MAX_SEARCH": 2000,
    "DEFAULT_BATCH_LIMIT": 30,
    "DELAYS": {
        "BATCH": 0.2,  # 200ms
        "EDIT_WAIT": 1.0,  # 1000ms
        "SEARCH": 0.1,  # 100ms
        "RESULT_DISPLAY": 3.0,  # 3000ms
    },
}

EDITABLE_MEDIA_TYPES = {
    MessageMediaType.PHOTO,
    MessageMediaType.VIDEO,
    MessageMediaType.DOCUMENT,
    MessageMediaType.ANIMATION,
    MessageMediaType.AUDIO,
    MessageMediaType.VOICE,
    MessageMediaType.VIDEO_NOTE,
}


async def get_troll_image():
    """
    获取防撤回图片，支持缓存
    Returns:
        str or None: 图片文件路径，如果下载失败则返回None
    """
    await log(f"[DME] 调试：get_troll_image() 开始执行")
    image_path = Path(CONFIG["TROLL_IMAGE_PATH"])
    await log(f"[DME] 调试：目标图片路径: {image_path}")
    
    # 如果本地文件已存在，直接返回路径
    if image_path.exists():
        await log(f"[DME] 调试：防撤回图片已存在，直接返回: {image_path}")
        return str(image_path)
    
    await log(f"[DME] 调试：防撤回图片不存在，开始下载")
    await log(f"[DME] 调试：下载URL: {CONFIG['TROLL_IMAGE_URL']}")
    
    # 确保目录存在
    try:
        image_path.parent.mkdir(parents=True, exist_ok=True)
        await log(f"[DME] 调试：创建目录成功: {image_path.parent}")
    except Exception as e:
        await log(f"[DME] 调试：创建目录失败: {e}")
        return None
    
    try:
        await log(f"[DME] 调试：开始HTTP请求")
        async with aiohttp.ClientSession() as session:
            async with session.get(CONFIG["TROLL_IMAGE_URL"]) as response:
                await log(f"[DME] 调试：HTTP响应状态: {response.status}")
                if response.status == 200:
                    content = await response.read()
                    await log(f"[DME] 调试：下载内容大小: {len(content)} 字节")
                    with open(image_path, "wb") as f:
                        f.write(content)
                    
                    # 验证文件写入
                    if image_path.exists():
                        file_size = image_path.stat().st_size
                        await log(f"[DME] 调试：防撤回图片下载成功: {image_path} (大小: {file_size} 字节)")
                        return str(image_path)
                    else:
                        await log(f"[DME] 调试：文件写入失败，文件不存在")
                        return None
                else:
                    await log(f"[DME] 调试：下载图片失败，HTTP状态码: {response.status}")
                    return None
    except Exception as e:
        await log(f"[DME] 调试：下载防撤回图片异常: {e}")
        import traceback
        await log(f"[DME] 调试：异常详情: {traceback.format_exc()}")
        return None


def _format_message_debug(message) -> str:
    out_value = getattr(message, "out", None)
    if out_value is None:
        out_value = getattr(message, "outgoing", None)
    from_user_id = message.from_user.id if message.from_user else None
    from_user_is_self = message.from_user.is_self if message.from_user else None
    sender_chat_id = message.sender_chat.id if message.sender_chat else None
    media_type = getattr(message, "media", None)
    return (
        f"id={message.id} out={out_value} "
        f"from_user_id={from_user_id} is_self={from_user_is_self} "
        f"sender_chat_id={sender_chat_id} media={media_type}"
    )


def is_my_message(message, my_id: int) -> bool:
    out_value = getattr(message, "out", None)
    if out_value is None:
        out_value = getattr(message, "outgoing", None)
    if out_value:
        return True
    if message.from_user and message.from_user.id == my_id:
        return True
    return False


async def search_my_messages_optimized(client: Client, chat_id, user_requested_count: int, my_id: int):
    """
    使用优化搜索模式直接搜索自己的消息
    Args:
        client: Pyrogram客户端
        chat_id: 聊天ID
        user_requested_count: 用户请求的消息数量
    Returns:
        list: 找到的消息列表
    """
    target_count = float('inf') if user_requested_count == 999999 else user_requested_count
    all_my_messages = []
    
    await log(
        f"[DME] 调试：使用优化搜索模式，chat_id={chat_id}, "
        f"my_id={my_id}, target={user_requested_count}"
    )
    
    try:
        # 使用pyrogram的search_messages直接搜索自己的消息
        search_limit = target_count if target_count != float('inf') else 0
        async for message in client.search_messages(
            chat_id=chat_id,
            from_user=my_id,
            limit=search_limit
        ):
            all_my_messages.append(message)
            if len(all_my_messages) <= 3:
                await log(f"[DME] 调试：优化搜索样本 {len(all_my_messages)}: {_format_message_debug(message)}")
            if len(all_my_messages) >= target_count:
                break
                
        await log(f"[DME] 调试：优化搜索完成，共找到 {len(all_my_messages)} 条自己的消息")
        return all_my_messages
        
    except Exception as e:
        await log(f"[DME] 调试：优化搜索失败: {type(e).__name__} - {e}")
        import traceback
        await log(f"[DME] 调试：优化搜索异常详情: {traceback.format_exc()}")
        return []


async def search_my_outgoing_messages(client: Client, chat_id, user_requested_count: int, my_id: int):
    """
    兼容"频道身份发言"的搜索：扫描历史并筛选自己发送的消息
    Args:
        client: Pyrogram客户端
        chat_id: 聊天ID  
        user_requested_count: 用户请求的消息数量
    Returns:
        list: 找到的消息列表
    """
    target_count = float('inf') if user_requested_count == 999999 else user_requested_count
    results = []
    
    await log(
        f"[DME] 调试：使用兼容模式搜索，chat_id={chat_id}, "
        f"my_id={my_id}, target={user_requested_count}"
    )
    
    try:
        # 扫描聊天历史，筛选自己发送的消息
        scanned = 0
        async for message in client.get_chat_history(chat_id):
            scanned += 1
            if scanned <= 5:
                await log(f"[DME] 调试：兼容搜索样本 {scanned}: {_format_message_debug(message)}")
            if is_my_message(message, my_id):
                results.append(message)
                if len(results) >= target_count:
                    break
                    
        await log(f"[DME] 调试：兼容搜索完成，扫描 {scanned} 条消息，命中 {len(results)} 条")
        return results
        
    except Exception as e:
        await log(f"[DME] 调试：兼容搜索失败: {type(e).__name__} - {e}")
        import traceback
        await log(f"[DME] 调试：兼容搜索异常详情: {traceback.format_exc()}")
        return []


def is_saved_messages_chat(chat, my_id: int):
    """
    判断是否为"收藏夹/保存的消息"会话
    Args:
        chat: 聊天对象
        my_id: 当前账号ID
    Returns:
        bool: 是否为收藏夹
    """
    # 收藏夹的特征：聊天类型为private且ID为自己的ID
    if hasattr(chat, 'type') and chat.type == ChatType.PRIVATE:
        return chat.id == my_id
    return False


def is_editable_media_message(message) -> bool:
    """
    检查消息是否为可编辑媒体类型
    Args:
        message: 消息对象
    Returns:
        bool: 是否为可编辑媒体
    """
    media_type = getattr(message, "media", None)
    if not media_type:
        return False
    return media_type in EDITABLE_MEDIA_TYPES


# 移除复杂的媒体检测函数 - 使用EAFP原则直接尝试编辑


async def try_edit_message_media_to_anti_recall(client: Client, message, troll_image_path: str):
    """
    直接尝试将消息媒体替换为防撤回图片 - 简化版本
    使用EAFP原则：直接尝试，失败了再处理
    Args:
        client: Pyrogram客户端
        message: 要编辑的消息对象
        troll_image_path: 防撤回图片路径
    Returns:
        bool: 是否编辑成功
    """
    await log(f"[DME] 调试：直接尝试编辑消息 {message.id} 的媒体内容")
    
    # 基础检查：图片文件是否存在
    if not troll_image_path or not os.path.exists(troll_image_path):
        await log(f"[DME] 调试：防撤回图片不存在: {troll_image_path}")
        return False

    # 媒体类型过滤
    if not is_editable_media_message(message):
        await log(f"[DME] 调试：消息 {message.id} 不是可编辑媒体类型，跳过")
        return False

    # 48小时编辑窗口检查
    if message.date:
        now = datetime.now(tz=message.date.tzinfo)
        if now - message.date > timedelta(hours=48):
            await log(f"[DME] 调试：⏰ 消息 {message.id} 超过48小时编辑限制")
            return False
    
    # 确保使用绝对路径
    abs_troll_path = os.path.abspath(troll_image_path)
    await log(f"[DME] 调试：使用绝对路径: {abs_troll_path}")
    
    for attempt in range(2):
        try:
            # 直接尝试编辑媒体 - 让pyrogram API自己判断是否可编辑
            media_obj = InputMediaPhoto(media=abs_troll_path, caption="")
            await client.edit_message_media(
                chat_id=message.chat.id,
                message_id=message.id,
                media=media_obj,
            )
            await log(f"[DME] 调试：✅ 成功编辑消息 {message.id} 的媒体内容")
            return True
            
        except FloodWait as e:
            await log(f"[DME] 调试：⏳ 编辑触发 FloodWait {e.value}s，等待后重试")
            await asyncio.sleep(e.value)
            continue
            
        except MessageEditTimeExpired:
            await log(f"[DME] 调试：⏰ 消息 {message.id} 编辑时间已过期（超过48小时）")
            return False
            
        except Exception as e:
            # 其他异常：可能不是媒体消息、权限不足、或其他原因
            error_type = type(e).__name__
            await log(f"[DME] 调试：❌ 编辑消息 {message.id} 失败: {error_type} - {e}")
            
            # 常见的失败原因不需要详细堆栈
            if any(keyword in str(e).lower() for keyword in ['media', 'photo', 'document', 'edit']):
                await log(f"[DME] 调试：可能原因: 不是媒体消息或不支持编辑该类型")
            else:
                # 意外错误才显示详细信息
                import traceback
                await log(f"[DME] 调试：异常详情: {traceback.format_exc()}")
            
            return False
    return False


async def edit_media_messages_in_batches(client: Client, messages: list, troll_image_path: str):
    """
    分批并发编辑媒体消息为防撤回图片
    Args:
        client: Pyrogram客户端
        messages: 媒体消息列表
        troll_image_path: 防撤回图片路径
    Returns:
        dict: 编辑结果统计
    """
    if not messages:
        return {"success": 0, "fail": 0, "exception": 0}
    
    sem = asyncio.Semaphore(CONFIG["EDIT_CONCURRENCY"])
    success_count = 0
    fail_count = 0
    exception_count = 0
    
    async def _run_edit(msg):
        async with sem:
            return await try_edit_message_media_to_anti_recall(client, msg, troll_image_path)
    
    for i in range(0, len(messages), CONFIG["EDIT_BATCH_SIZE"]):
        batch = messages[i:i + CONFIG["EDIT_BATCH_SIZE"]]
        tasks = [asyncio.create_task(_run_edit(msg)) for msg in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                exception_count += 1
            elif result is True:
                success_count += 1
            else:
                fail_count += 1
        
        await asyncio.sleep(CONFIG["DELAYS"]["BATCH"])
    
    return {"success": success_count, "fail": fail_count, "exception": exception_count}


async def delete_messages_with_retry(client: Client, chat_id, message_ids: list):
    """
    带重试机制的批量删除消息
    Args:
        client: Pyrogram客户端
        chat_id: 聊天ID
        message_ids: 要删除的消息ID列表
    Returns:
        int: 成功删除的消息数量
    """
    try:
        await client.delete_messages(chat_id=chat_id, message_ids=message_ids, revoke=True)
        return len(message_ids)
    except FloodWait as e:
        # 遇到API限制，等待后重试
        wait_time = e.value
        print(f"[DME] 触发API限制，等待 {wait_time} 秒...")
        
        for remaining in range(wait_time, 0, -10):
            if remaining % 10 == 0 or remaining < 10:
                print(f"[DME] 删除等待中... 剩余 {remaining} 秒")
            await asyncio.sleep(min(remaining, 10))
        
        # 重试删除
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=message_ids, revoke=True)
            return len(message_ids)
        except Exception as retry_error:
            print(f"[DME] 重试删除失败: {retry_error}")
            return 0
    except Exception as e:
        print(f"[DME] 删除批次失败: {e}")
        return 0


async def delete_in_saved_messages(client: Client, chat_id, user_requested_count: int):
    """
    收藏夹直接按数量删除（不做媒体编辑）
    Args:
        client: Pyrogram客户端
        chat_id: 聊天ID
        user_requested_count: 要删除的数量
    Returns:
        dict: 处理结果统计
    """
    target = user_requested_count
    message_ids = []
    
    print(f"[DME] 收藏夹模式：直接删除 {target} 条消息")
    
    # 收集要删除的消息ID
    async for message in client.get_chat_history(chat_id, limit=target):
        message_ids.append(message.id)
        if len(message_ids) >= target:
            break
    
    if not message_ids:
        return {"processed_count": 0, "actual_count": 0, "edited_count": 0}
    
    # 批量删除
    deleted_count = 0
    for i in range(0, len(message_ids), CONFIG["BATCH_SIZE"]):
        batch_ids = message_ids[i:i + CONFIG["BATCH_SIZE"]]
        batch_deleted = await delete_messages_with_retry(client, chat_id, batch_ids)
        deleted_count += batch_deleted
        
        if batch_deleted > 0:
            print(f"[DME] 删除批次进度: {deleted_count}/{len(message_ids)}")
        
        # 批次间延迟
        await asyncio.sleep(CONFIG["DELAYS"]["BATCH"])
    
    return {
        "processed_count": deleted_count,
        "actual_count": len(message_ids),
        "edited_count": 0
    }


async def search_edit_and_delete_my_messages(client: Client, chat_id, user_requested_count: int):
    """
    搜索并处理用户消息的主函数 - 优化版本
    Args:
        client: Pyrogram客户端
        chat_id: 聊天ID
        user_requested_count: 用户请求的数量
    Returns:
        dict: 处理结果统计
    """
    chat = await client.get_chat(chat_id)
    me = await client.get_me()
    my_id = me.id
    
    # 收藏夹特殊处理
    if is_saved_messages_chat(chat, my_id):
        print("[DME] 检测到收藏夹会话，使用快速删除模式")
        return await delete_in_saved_messages(client, chat_id, user_requested_count)
    
    await log(f"[DME] 调试：开始搜索消息，目标数量: {user_requested_count if user_requested_count != 999999 else '全部'}")
    
    # 首先尝试优化搜索
    all_my_messages = await search_my_messages_optimized(client, chat_id, user_requested_count, my_id)
    
    # 如果优化搜索结果不足，回退到兼容模式
    target_count = float('inf') if user_requested_count == 999999 else user_requested_count
    if len(all_my_messages) == 0 or (target_count != float('inf') and len(all_my_messages) < target_count):
        await log("[DME] 调试：优化搜索结果不足，回退到兼容模式")
        all_my_messages = await search_my_outgoing_messages(client, chat_id, user_requested_count, my_id)
    
    if not all_my_messages:
        await log("[DME] 调试：未找到任何自己的消息")
        return {"processed_count": 0, "actual_count": 0, "edited_count": 0}
    
    # 限制处理数量
    messages_to_process = all_my_messages
    if target_count != float('inf'):
        messages_to_process = all_my_messages[:target_count]
    
    await log(f"[DME] 调试：准备处理 {len(messages_to_process)} 条消息")
    
    # 简化方案：对所有消息都尝试防撤回编辑，让API自己判断
    await log(f"[DME] 调试：获取防撤回图片")
    troll_image_path = await get_troll_image()
    await log(f"[DME] 调试：get_troll_image() 返回: {troll_image_path}")
    
    edited_count = 0
    if troll_image_path:
        await log(f"[DME] 调试：开始对所有 {len(messages_to_process)} 条消息尝试防撤回编辑")
        
        media_messages = [msg for msg in messages_to_process if is_editable_media_message(msg)]
        await log(f"[DME] 调试：筛选到 {len(media_messages)} 条可编辑媒体消息")
        
        result = await edit_media_messages_in_batches(client, media_messages, troll_image_path)
        edited_count = result["success"]
        await log(
            f"[DME] 调试：防撤回编辑完成 - ✅成功: {result['success']}, "
            f"❌失败: {result['fail']}, ⚠️异常: {result['exception']}"
        )
        
        # 编辑完成后等待
        await log(f"[DME] 调试：防撤回编辑完成，等待 {CONFIG['DELAYS']['EDIT_WAIT']} 秒")
        await asyncio.sleep(CONFIG["DELAYS"]["EDIT_WAIT"])
    else:
        await log(f"[DME] 调试：未获取到防撤回图片，跳过所有防撤回编辑")
    
    # 批量删除消息
    await log(f"[DME] 调试：开始删除 {len(messages_to_process)} 条消息")
    message_ids = [msg.id for msg in messages_to_process]
    await log(f"[DME] 调试：消息ID列表: {message_ids}")
    deleted_count = 0
    
    for i in range(0, len(message_ids), CONFIG["BATCH_SIZE"]):
        batch_ids = message_ids[i:i + CONFIG["BATCH_SIZE"]]
        await log(f"[DME] 调试：删除批次 {i//CONFIG['BATCH_SIZE'] + 1}: {batch_ids}")
        batch_deleted = await delete_messages_with_retry(client, chat_id, batch_ids)
        deleted_count += batch_deleted
        
        await log(f"[DME] 调试：删除进度: {deleted_count}/{len(message_ids)}")
        
        # 批次间延迟
        await asyncio.sleep(CONFIG["DELAYS"]["BATCH"])
    
    await log(f"[DME] 调试：删除完成，共删除 {deleted_count} 条消息")
    
    return {
        "processed_count": deleted_count,
        "actual_count": len(messages_to_process),
        "edited_count": edited_count
    }

# 帮助文本
HELP_TEXT = """🗑️ <b>智能防撤回删除插件 (DME)</b>

<b>命令格式:</b>
<code>.dme [数量]</code>

<b>功能特性:</b>
• 智能搜索自己的消息
• 媒体消息防撤回处理
• 批量删除优化
• 收藏夹快速删除
• 静默操作模式

<b>使用示例:</b>
• <code>.dme 10</code> - 删除最近10条消息
• <code>.dme 100</code> - 删除最近100条消息  
• <code>.dme 999999</code> - 删除所有自己的消息
• <code>.dme help</code> - 显示帮助信息

<b>特殊功能:</b>
• 媒体消息会被替换为防撤回图片后删除
• 收藏夹中的消息直接快速删除
• 支持频道身份发言的消息删除
• 自动处理API限制和重试机制"""


@listener(
    outgoing=True,
    command="dme",
    need_admin=True,
    description="智能防撤回删除插件",
    parameters="[数量/help]",
)
async def dme_main(client: Client, message: Message):
    """智能防撤回删除插件主函数"""
    
    await log(f"[DME] 调试：dme_main() 函数开始执行")
    await log(f"[DME] 调试：消息来源 - chat_id: {message.chat.id}, from_user: {message.from_user.id if message.from_user else 'None'}")
    
    # 解析参数
    if not message.parameter:
        await log(f"[DME] 调试：没有参数，显示帮助信息")
        await message.edit(HELP_TEXT, parse_mode="html")
        return
    
    await log(f"[DME] 调试：收到参数: {message.parameter}")
    
    # 处理帮助命令
    if len(message.parameter) == 1 and message.parameter[0].lower() in ["help", "h"]:
        await log(f"[DME] 调试：显示帮助命令")
        await message.edit(HELP_TEXT, parse_mode="html")
        return
    
    # 解析数量参数
    try:
        count = int(message.parameter[0])
        await log(f"[DME] 调试：解析到数量参数: {count}")
        if count <= 0:
            await log(f"[DME] 调试：数量参数无效 (<=0)")
            await message.edit(
                "❌ <b>参数错误:</b> 数量必须是正整数\n\n"
                "💡 使用 <code>.dme help</code> 查看帮助",
                parse_mode="html"
            )
            return
    except (ValueError, IndexError):
        await log(f"[DME] 调试：数量参数解析失败")
        await message.edit(
            "❌ <b>参数错误:</b> 请提供有效的数字\n\n"
            "💡 使用 <code>.dme help</code> 查看帮助",
            parse_mode="html"
        )
        return
    
    chat_id = message.chat.id
    await log(f"[DME] 调试：目标聊天ID: {chat_id}")
    
    # 删除命令消息
    try:
        await message.delete()
        await log(f"[DME] 调试：成功删除命令消息")
    except Exception as e:
        await log(f"[DME] 调试：删除命令消息失败: {e}")
        pass
    
    # 执行主要操作
    await log(f"[DME] 调试：========== 开始执行DME任务 ==========")
    await log(f"[DME] 调试：聊天ID: {chat_id}")
    await log(f"[DME] 调试：请求数量: {count}")
    start_time = datetime.now()
    await log(f"[DME] 调试：开始时间: {start_time}")
    
    try:
        await log(f"[DME] 调试：调用 search_edit_and_delete_my_messages")
        result = await search_edit_and_delete_my_messages(client, chat_id, count)
        await log(f"[DME] 调试：search_edit_and_delete_my_messages 返回: {result}")
        
        duration = (datetime.now() - start_time).total_seconds()
        await log(f"[DME] 调试：========== 任务完成 ==========")
        await log(f"[DME] 调试：总耗时: {duration:.1f} 秒")
        await log(f"[DME] 调试：处理消息: {result['processed_count']} 条")
        await log(f"[DME] 调试：编辑媒体: {result['edited_count']} 条")
        await log(f"[DME] 调试：=============================")
        
        # 完全静默模式 - 不发送任何前台消息
        
    except Exception as e:
        await log(f"[DME] 调试：操作失败: {e}")
        import traceback
        await log(f"[DME] 调试：异常详情: {traceback.format_exc()}")
        # 静默失败 - 不显示错误给用户
