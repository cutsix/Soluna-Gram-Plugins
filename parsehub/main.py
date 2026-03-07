"""
Soluna-Gram 插件: ParseHub 链接解析器

依赖 @ParseHubot 机器人解析社交媒体链接

支持平台:
- 抖音视频|图文
- 哔哩哔哩视频|动态
- YouTube / YouTube Music
- TikTok视频|图文
- 小红书视频|图文
- Twitter视频|图文
- 百度贴吧视频|图文
- Facebook视频
- 微博视频|图文
- Instagram视频|图文
"""

import asyncio
import contextlib
import html as html_module
import json
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Set, Any

from pyrogram import enums
from solgram.listener import listener
from solgram.enums import Client, Message

# ==================== 常量定义 ====================
BOT_USERNAME = "ParseHubot"
POLL_INTERVAL_MS = 2000  # 轮询间隔（毫秒）
MAX_WAIT_MS = 3 * 60 * 1000  # 最大等待时间（3分钟）
RESULT_IDLE_MS = 5000  # 结果空闲时间（5秒）
FETCH_LIMIT = 50  # 每次获取消息数量

PROGRESS_PREFIXES = [
    "解 析 中",
    "已有相同任务正在解析",
    "下 载 中",
    "上 传 中",
]

# ==================== 状态管理 ====================
STATE_FILE = Path(__file__).parent / "parsehub_state.json"

# 全局状态变量
has_started_bot = False
first_run_pre_start_last_id = 0
should_ignore_next_bot_message = False
ignored_up_to_id = 0


def read_state() -> Dict:
    """读取状态文件"""
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return {
                "initialized": bool(data.get("initialized", False)),
                "ignoredUpToId": int(data.get("ignoredUpToId", 0)) if data.get("ignoredUpToId") else 0
            }
    except Exception:
        pass
    return {"initialized": False, "ignoredUpToId": 0}


def write_state(state: Dict):
    """写入状态文件"""
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# 初始化状态
init_state = read_state()
ignored_up_to_id = init_state.get("ignoredUpToId", 0)


# ==================== 辅助函数 ====================
def html_escape(text: str) -> str:
    """HTML 实体转义"""
    return html_module.escape(text)


def is_progress_text(text: Optional[str]) -> bool:
    """判断是否为进度消息"""
    if not text:
        return False
    trimmed = text.strip()
    return any(trimmed.startswith(prefix) for prefix in PROGRESS_PREFIXES)


def extract_links(text: str) -> List[str]:
    """从文本中提取链接"""
    if not text:
        return []
    
    # 匹配 http(s):// 或 www. 开头的链接
    pattern = r'(?:https?://|www\.)\S+'
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    # 清理链接（移除末尾的标点符号）
    sanitized = []
    for raw in matches:
        # 移除中英文标点
        cleaned = re.sub(r'[)\]\}\u3002\uff1a\uff01\uff1f\u3001\uff0c>]+$', '', raw)
        # 确保有协议头
        if not cleaned.startswith('http'):
            cleaned = f'https://{cleaned}'
        sanitized.append(cleaned.strip())
    
    # 去重并过滤空值
    return list(filter(None, dict.fromkeys(sanitized)))


async def get_latest_bot_message_id(bot: Client, bot_username: str) -> int:
    """获取机器人最新消息 ID"""
    try:
        messages = []
        async for msg in bot.get_chat_history(bot_username, limit=1):
            messages.append(msg)
        if messages:
            return messages[0].id
    except Exception:
        pass
    return 0


async def ensure_bot_ready(bot: Client, bot_username: str):
    """确保机器人已准备就绪"""
    global has_started_bot, first_run_pre_start_last_id, should_ignore_next_bot_message
    global ignored_up_to_id, init_state
    
    # 解除屏蔽
    with contextlib.suppress(Exception):
        await bot.unblock_user(bot_username)
    
    # 检查是否已启动
    if has_started_bot:
        return
    
    # 检查历史消息
    try:
        count = 0
        async for _ in bot.get_chat_history(bot_username, limit=1):
            count += 1
        if count > 0:
            has_started_bot = True
            return
    except Exception:
        pass
    
    # 发送 /start 启动机器人
    try:
        if not init_state.get("initialized", False):
            first_run_pre_start_last_id = await get_latest_bot_message_id(bot, bot_username)
            should_ignore_next_bot_message = True
        
        await bot.send_message(bot_username, "/start")
        has_started_bot = True
    except Exception:
        pass
    
    # 首次运行：捕获欢迎消息 ID
    if not init_state.get("initialized", False):
        deadline = time.time() + 20  # 最多等待 20 秒
        while time.time() < deadline:
            await asyncio.sleep(0.5)
            try:
                latest_id = await get_latest_bot_message_id(bot, bot_username)
                if latest_id > first_run_pre_start_last_id and latest_id > ignored_up_to_id:
                    ignored_up_to_id = latest_id
                    init_state["initialized"] = True
                    init_state["ignoredUpToId"] = latest_id
                    write_state(init_state)
                    should_ignore_next_bot_message = False
                    break
            except Exception:
                pass


def describe_reason(reason: Optional[str]) -> str:
    """描述失败原因"""
    reasons = {
        "timeout": "等待超时",
        "fetch_failed": "获取机器人消息失败",
        "send_failed": "向机器人发送链接失败",
        "no_client": "客户端未就绪",
    }
    return reasons.get(reason, "原因未知")


async def relay_parse_result(
    bot: Client,
    message: Message,
    bot_username: str,
    link: str,
    baseline_id: int
) -> Dict:
    """
    中继解析结果
    
    返回: {"lastId": int, "forwarded": bool, "reason": str, "error": str}
    """
    global should_ignore_next_bot_message, ignored_up_to_id, init_state
    
    # 发送链接到机器人
    try:
        await bot.send_message(bot_username, link)
    except Exception as e:
        return {
            "lastId": baseline_id,
            "forwarded": False,
            "reason": "send_failed",
            "error": str(e)
        }
    
    processed_ids: Set[int] = set()
    final_messages: Dict[int, Any] = {}
    
    deadline = time.time() + (MAX_WAIT_MS / 1000)
    last_id = baseline_id
    last_final_activity = 0
    first_run_ignore = should_ignore_next_bot_message
    
    # 轮询消息
    while time.time() < deadline:
        await asyncio.sleep(POLL_INTERVAL_MS / 1000)
        
        # 获取消息
        messages = []
        try:
            async for msg in bot.get_chat_history(bot_username, limit=FETCH_LIMIT):
                messages.append(msg)
        except Exception as e:
            return {
                "lastId": last_id,
                "forwarded": False,
                "reason": "fetch_failed",
                "error": str(e)
            }
        
        # 按 ID 排序（从旧到新）
        messages.sort(key=lambda m: m.id)
        
        for bot_msg in messages:
            # 过滤条件
            if not bot_msg or bot_msg.service:  # 服务消息
                continue
            if bot_msg.outgoing:  # 自己发送的消息
                continue
            if bot_msg.id <= last_id:  # 已处理的消息
                continue
            if bot_msg.id in processed_ids:
                continue
            
            processed_ids.add(bot_msg.id)
            last_id = max(last_id, bot_msg.id)
            
            # 检查是否为进度消息
            text = bot_msg.text or bot_msg.caption or ""
            if is_progress_text(text):
                continue
            
            # 首次运行：忽略欢迎消息
            if first_run_ignore:
                first_run_ignore = False
                should_ignore_next_bot_message = False
                ignored_up_to_id = bot_msg.id
                init_state["initialized"] = True
                init_state["ignoredUpToId"] = bot_msg.id
                write_state(init_state)
                last_id = max(last_id, bot_msg.id)
                continue
            
            # 记录最终消息
            final_messages[bot_msg.id] = bot_msg
            last_final_activity = time.time()
        
        # 检查是否已收集到最终结果（空闲时间超过阈值）
        if final_messages and time.time() - last_final_activity >= (RESULT_IDLE_MS / 1000):
            break
    
    # 没有收到最终结果
    if not final_messages:
        return {"lastId": last_id, "forwarded": False, "reason": "timeout"}
    
    # 按 ID 排序消息
    sorted_messages = sorted(final_messages.values(), key=lambda m: m.id)
    
    forwarded = False
    fallback_texts = []
    
    # 使用 copy_message 逐条复制（等价于 TS 版本的 dropAuthor: true）
    for i, msg in enumerate(sorted_messages):
        try:
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=bot_username,
                message_id=msg.id
            )
            forwarded = True
            
            # 每 10 条消息延迟一下，避免触发限流
            if i > 0 and i % 10 == 0:
                await asyncio.sleep(0.1)
        except Exception:
            # 复制失败，收集文本作为降级方案
            text = (msg.text or msg.caption or "").strip()
            if text:
                fallback_texts.append(text)
            else:
                fallback_texts.append(
                    f"⚠️ 未能复制 @{bot_username} 的多媒体结果，请前往私聊机器人查看。"
                )
    
    # 降级：发送文本消息
    if not forwarded and fallback_texts:
        try:
            await bot.send_message(
                message.chat.id,
                f" @{bot_username} 返回内容：\n\n{chr(10).join(fallback_texts)}",
                reply_to_message_id=message.id
            )
            forwarded = True  # 标记为已转发，避免返回 timeout 错误
        except Exception:
            pass
    
    return {
        "lastId": last_id,
        "forwarded": forwarded,
        "reason": None if forwarded else "timeout"
    }


# ==================== 命令处理器 ====================
@listener(
    command="parsehub",
    description="""依赖 @ParseHubot

1) 直接命令：<code>,parsehub 链接</code>
2) 回复消息后使用：在含链接的消息上回复 <code>,parsehub</code>

目前支持的平台:
抖音视频|图文
哔哩哔哩视频|动态
YouTube
YouTube Music
TikTok视频|图文
小红书视频|图文
Twitter视频|图文
百度贴吧视频|图文
Facebook视频
微博视频|图文
Instagram视频|图文

示例：
<code>,parsehub https://twitter.com/user/status/123</code>
<code>,parsehub https://www.instagram.com/p/xxxx/</code>"""
)
async def parsehub_handler(bot: Client, message: Message):
    """ParseHub 链接解析命令处理器"""
    global ignored_up_to_id, should_ignore_next_bot_message, first_run_pre_start_last_id
    global init_state
    
    # 获取命令文本
    raw_text = message.text or ""
    # 移除命令前缀
    cleaned = re.sub(r'^[,，]parsehub\s*', '', raw_text, flags=re.IGNORECASE)
    links = extract_links(cleaned)
    
    # 如果命令中没有链接，尝试从回复消息中提取
    if not links and message.reply_to_message:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        reply_links = extract_links(reply_text)
        if reply_links:
            links = reply_links
    
    # 合并命令和回复消息中的链接（去重）
    if message.reply_to_message:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        reply_links = extract_links(reply_text)
        if reply_links:
            link_set = set(links)
            link_set.update(reply_links)
            links = list(link_set)
    
    # 没有找到链接，显示帮助
    if not links:
        help_text = f"""依赖 @{BOT_USERNAME}

1) 直接命令：<code>,parsehub 链接</code>
2) 回复消息后使用：在含链接的消息上回复 <code>,parsehub</code>

目前支持的平台:
抖音视频|图文
哔哩哔哩视频|动态
YouTube
YouTube Music
TikTok视频|图文
小红书视频|图文
Twitter视频|图文
百度贴吧视频|图文
Facebook视频
微博视频|图文
Instagram视频|图文

示例：
<code>,parsehub https://twitter.com/user/status/123</code>
<code>,parsehub https://www.instagram.com/p/xxxx/</code>"""
        await message.edit(help_text, parse_mode=enums.ParseMode.HTML)
        return
    
    # 只处理第一个链接
    if len(links) > 1:
        links = [links[0]]
    
    # 显示处理中提示
    await message.edit(
        f" 正在解析中....",
        parse_mode=enums.ParseMode.HTML
    )
    
    # 确保机器人已准备就绪
    await ensure_bot_ready(bot, BOT_USERNAME)
    
    # 获取基准消息 ID
    baseline_id = await get_latest_bot_message_id(bot, BOT_USERNAME)
    if ignored_up_to_id > baseline_id:
        baseline_id = ignored_up_to_id
    
    # 检查首次运行标志
    if (should_ignore_next_bot_message and 
        first_run_pre_start_last_id > 0 and 
        baseline_id > first_run_pre_start_last_id):
        should_ignore_next_bot_message = False
        init_state["initialized"] = True
        init_state["ignoredUpToId"] = baseline_id
        write_state(init_state)
    
    # 处理每个链接
    for link in links:
        outcome = await relay_parse_result(bot, message, BOT_USERNAME, link, baseline_id)
        baseline_id = outcome["lastId"]
        
        # 处理失败情况
        if not outcome["forwarded"]:
            reason_text = describe_reason(outcome.get("reason"))
            error_msg = outcome.get("error", "")
            detail = f"\n\n错误信息：{error_msg}" if error_msg and error_msg != "None" else ""
            
            await bot.send_message(
                message.chat.id,
                f"⚠️ 未能获取 <b>{html_escape(link)}</b> 的最终结果（{reason_text}）。"
                f"请稍后重试或直接私聊 @{BOT_USERNAME}。{detail}",
                parse_mode=enums.ParseMode.HTML,
                reply_to_message_id=message.id
            )
        
        await asyncio.sleep(0.6)  # 延迟 600ms
    
    # 删除原始命令消息
    with contextlib.suppress(Exception):
        await message.delete()

