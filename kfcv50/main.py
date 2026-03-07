from secrets import choice
from solgram.listener import listener
from solgram.enums import Message
from solgram.utils import edit_delete, pip_install
import json

pip_install("aiohttp")

import aiohttp

# API 接口列表
API_ENDPOINTS = [
    "https://api.ahfi.cn/api/kfcv50?type=json",
    "https://kfc-crazy-thursday.vercel.app/api/index",
    "https://api.suyanw.cn/api/kfcyl.php",
    "https://api.suyanw.cn/api/kfcyl.php?type=json"
]

@listener(command="kfc", description="KFC V50")
async def kfcv50(_, message: Message):
    try:
        async with aiohttp.ClientSession() as session:
            # 随机选择一个API
            api_url = choice(API_ENDPOINTS)
            async with session.get(api_url) as response:
                if response.status == 200:
                    text = await response.text()
                    
                    if api_url.endswith('json'):  # JSON格式的API
                        try:
                            data = json.loads(text)
                            if 'text' in data:  # api.suyanw.cn 的JSON格式
                                return await message.edit(data['text'])
                            elif 'data' in data:  # api.ahfi.cn 的格式
                                return await message.edit(data['data']['copywriting'])
                        except json.JSONDecodeError:
                            # 如果JSON解析失败，直接使用文本内容
                            return await message.edit(text)
                    else:  # 纯文本格式的API
                        return await message.edit(text)
                        
        await edit_delete(message, "出错了呜呜呜 ~ 无法访问到 API 服务器 。")
    except Exception as e:
        await edit_delete(message, f"出错了呜呜呜 ~ {str(e)}")
