# -*- coding: UTF-8 -*-
# 摸鱼日报插件 - Python版本
# 转换自 moyu.ts
from solgram.listener import listener
from solgram.enums import Message
from solgram.utils import edit_delete, pip_install
import asyncio
from datetime import datetime
import pytz

pip_install("aiohttp")

import aiohttp

# 中国时区
CN_TIME_ZONE = pytz.timezone("Asia/Shanghai")

def format_cn_time(dt: datetime) -> str:
    """格式化中国时间"""
    cn_time = dt.astimezone(CN_TIME_ZONE)
    return cn_time.strftime("%Y-%m-%d %H:%M:%S")

@listener(command="moyu", description="📰 摸鱼日报")
async def moyu_handler(message: Message):
    """摸鱼日报插件主处理函数"""
    try:
        # 更新状态
        await message.edit("开摸...")
        
        # 获取当前时间并格式化标题
        current_time = datetime.now()
        caption = f"摸鱼日报 {format_cn_time(current_time)}"
        
        # 下载图片
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.52vmy.cn/api/wl/moyu",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    await message.edit("❌ 获取摸鱼日报失败，服务器响应异常")
                    return
                
                image_data = await response.read()
        
        # 发送图片
        await message.reply_photo(
            photo=image_data,
            caption=caption,
            quote=False
        )
        
        # 删除原始命令消息
        await message.delete()
        
    except aiohttp.ClientError as e:
        await edit_delete(message, f"❌ 网络错误：{str(e)}")
    except asyncio.TimeoutError:
        await edit_delete(message, "❌ 请求超时：网络连接超时")
    except Exception as e:
        await edit_delete(message, f"❌ 获取摸鱼日报失败：{str(e)}")
