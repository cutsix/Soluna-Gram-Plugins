# -*- coding: UTF-8 -*-
# 每日新闻插件 - Python版本
# 转换自 new.ts
from solgram.listener import listener
from solgram.enums import Message
from solgram.utils import edit_delete, pip_install
from pyrogram.enums import ParseMode
import json
import html
import asyncio

pip_install("aiohttp")

import aiohttp

# HTML转义工具
def html_escape(text: str) -> str:
    """HTML转义"""
    return html.escape(text, quote=True)

# 详细帮助文档
HELP_TEXT = """🗞️ <b>每日新闻插件</b>

<b>📝 功能描述:</b>
• 📰 <b>每日新闻</b>：获取当日热点新闻
• 🎬 <b>历史上的今天</b>：查看历史事件
• 🧩 <b>天天成语</b>：学习成语知识
• 🎻 <b>慧语香风</b>：欣赏名人名言
• 🎑 <b>诗歌天地</b>：品味古典诗词

<b>🔧 使用方法:</b>
• <code>,news</code> - 获取完整的每日资讯
• <code>,news help</code> - 显示此帮助信息

<b>💡 示例:</b>
• <code>,news</code> - 获取今日完整资讯包

<b>📊 数据来源:</b>
• API: news.topurl.cn
• 内容: 新闻、历史、成语、名言、诗词"""

async def fetch_news_data():
    """获取新闻数据"""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://news.topurl.cn/api",
            timeout=aiohttp.ClientTimeout(total=15),
            headers={'User-Agent': 'TeleBox/1.0'}
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('data')
    return None

def format_news_message(data):
    """格式化新闻消息"""
    message_parts = []
    
    # 每日新闻部分
    if data.get('newsList') and len(data['newsList']) > 0:
        message_parts.append("📮 <b>每日新闻</b> 📮")
        message_parts.append("")
        for index, item in enumerate(data['newsList']):
            title = html_escape(item.get('title', ''))
            url = item.get('url', '')
            if title and url:
                message_parts.append(f"{index + 1}. <a href=\"{url}\">{title}</a>")
        message_parts.append("")
    
    # 历史上的今天部分
    if data.get('historyList') and len(data['historyList']) > 0:
        message_parts.append("🎬 <b>历史上的今天</b> 🎬")
        message_parts.append("")
        for item in data['historyList']:
            event = html_escape(item.get('event', ''))
            if event:
                message_parts.append(event)
        message_parts.append("")
    
    # 天天成语部分
    if data.get('phrase'):
        message_parts.append("🧩 <b>天天成语</b> 🧩")
        message_parts.append("")
        phrase = html_escape(data['phrase'].get('phrase', ''))
        explain = html_escape(data['phrase'].get('explain', ''))
        if phrase and explain:
            message_parts.append(f"<b>{phrase}</b>")
            message_parts.append(f"{explain}")
        message_parts.append("")
    
    # 慧语香风部分
    if data.get('sentence'):
        message_parts.append("🎻 <b>慧语香风</b> 🎻")
        message_parts.append("")
        sentence = html_escape(data['sentence'].get('sentence', ''))
        author = html_escape(data['sentence'].get('author', ''))
        if sentence and author:
            message_parts.append(f"<i>{sentence}</i>")
            message_parts.append(f"—— <b>{author}</b>")
        message_parts.append("")
    
    # 诗歌天地部分
    if data.get('poem'):
        message_parts.append("🎑 <b>诗歌天地</b> 🎑")
        message_parts.append("")
        content = ''.join(data['poem'].get('content', []))
        title = html_escape(data['poem'].get('title', ''))
        author = html_escape(data['poem'].get('author', ''))
        if content and title and author:
            poem_content = html_escape(content)
            message_parts.append(f"<i>{poem_content}</i>")
            message_parts.append(f"—— 《<b>{title}</b>》{author}")
        message_parts.append("")
    
    return "\n".join(message_parts).strip()

async def send_long_message(message: Message, text: str):
    """处理长消息分段发送"""
    MAX_LENGTH = 4000
    
    if len(text) <= MAX_LENGTH:
        await message.edit(text, parse_mode=ParseMode.HTML)
        return
    
    # 分段发送
    parts = text.split('\n\n')
    chunks = []
    current_chunk = ""
    
    for part in parts:
        if len(current_chunk + part + '\n\n') > MAX_LENGTH:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = part + '\n\n'
            else:
                # 单个部分就超长，强制截断
                chunks.append(part[:MAX_LENGTH - 3] + "...")
        else:
            current_chunk += part + '\n\n'
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # 发送第一段（编辑原消息）
    if chunks:
        await message.edit(chunks[0], parse_mode=ParseMode.HTML)
        
        # 发送后续段落
        for chunk in chunks[1:]:
            await message.reply(chunk, parse_mode=ParseMode.HTML)

@listener(command="news", description="🗞️ 每日新闻、历史上的今天、天天成语、慧语香风、诗歌天地")
async def news_handler(message: Message):
    """新闻插件主处理函数"""
    try:
        # 参数解析
        args = message.parameter if message.parameter else []
        sub = args[0].lower() if args else ""
        
        # 处理help命令
        if sub in ["help", "h"]:
            await message.edit(HELP_TEXT, parse_mode=ParseMode.HTML)
            return
        
        # 处理未知子命令
        if sub and sub not in ["help", "h"]:
            await message.edit(
                f"❌ <b>未知命令:</b> <code>{html_escape(sub)}</code>\n\n💡 使用 <code>,news help</code> 查看帮助",
                parse_mode=ParseMode.HTML
            )
            return
        
        # 默认操作：获取新闻
        await message.edit("📰 获取中...", parse_mode=ParseMode.HTML)
        
        # 连接服务器
        await message.edit("📡 连接服务器...", parse_mode=ParseMode.HTML)
        
        # 获取新闻数据
        data = await fetch_news_data()
        if not data:
            await message.edit("❌ <b>获取失败:</b> API返回数据格式错误", parse_mode=ParseMode.HTML)
            return
        
        # 处理数据
        await message.edit("📝 处理数据...", parse_mode=ParseMode.HTML)
        
        # 格式化消息
        final_message = format_news_message(data)
        
        if not final_message:
            await message.edit("❌ 未获取到有效数据", parse_mode=ParseMode.HTML)
            return
        
        # 发送消息
        await send_long_message(message, final_message)
        
    except aiohttp.ClientError as e:
        await message.edit(f"❌ <b>网络错误:</b> {html_escape(str(e))}", parse_mode=ParseMode.HTML)
    except asyncio.TimeoutError:
        await message.edit("❌ <b>请求超时:</b> 网络连接超时", parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.edit(f"❌ <b>插件执行失败:</b> {html_escape(str(e))}", parse_mode=ParseMode.HTML)
