import contextlib
import re
from urllib.parse import urlparse

from pyrogram.enums import ParseMode

from solgram.listener import listener
from solgram.enums import Message
from solgram.services import client as http_client

TARGET_PATTERN = re.compile(
    r"(https?://\S+|(?:\d{1,3}\.){3}\d{1,3}|[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
IP_API_FIELDS = (
    "status,message,country,regionName,city,lat,lon,isp,org,as,mobile,proxy,hosting,query"
)


def normalize_target(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    target = parsed.hostname or parsed.path
    if ":" in target and "." not in target and not parsed.hostname:
        target = raw
    return target.strip("[]")


def extract_target_from_text(text: str) -> str:
    if not text:
        return ""
    match = TARGET_PATTERN.search(text)
    if not match:
        return ""
    return normalize_target(match.group(1))


def extract_target_from_reply(reply: Message) -> str:
    text = reply.text or reply.caption or ""
    entities = reply.entities or reply.caption_entities or []
    for entity in entities:
        value = text[entity.offset : entity.offset + entity.length]
        target = normalize_target(value)
        if target:
            return target
    return extract_target_from_text(text)


async def get_ip_info(target: str) -> str:
    response = await http_client.get(
        f"http://ip-api.com/json/{target}?fields={IP_API_FIELDS}"
    )
    data = response.json()
    if data.get("status") != "success":
        return ""

    lines = [f"查询目标： `{target}`"]
    if data.get("query") and data["query"] != target:
        lines.append(f"解析地址： `{data['query']}`")

    lines.extend(
        [
            f"地区： `{data.get('country', '')} - {data.get('regionName', '')} - {data.get('city', '')}`",
            f"经纬度： `{data.get('lat', '')},{data.get('lon', '')}`",
            f"ISP： `{data.get('isp', '')}`",
        ]
    )

    if data.get("org"):
        lines.append(f"组织： `{data['org']}`")

    with contextlib.suppress(Exception):
        asn = data.get("as", "")
        if asn:
            lines.append(f"[{asn}](https://bgp.he.net/{asn.split()[0]})")

    if data.get("mobile"):
        lines.append("此 IP 可能为**蜂窝移动数据 IP**")
    if data.get("proxy"):
        lines.append("此 IP 可能为**代理 IP**")
    if data.get("hosting"):
        lines.append("此 IP 可能为**数据中心 IP**")

    return "\n".join(lines)


@listener(command="ip", description="查询 IP / 域名归属地信息", parameters="[ip/域名]")
async def ipinfo(message: Message):
    reply = message.reply_to_message
    message = await message.edit("正在查询中...")

    try:
        target = ""
        if message.arguments:
            target = normalize_target(message.arguments)
        elif reply:
            target = extract_target_from_reply(reply)

        if not target:
            await message.edit("没有找到要查询的 ip/域名 ...")
            return

        result = await get_ip_info(target)
        if not result:
            await message.edit("没有找到要查询的 ip/域名 ...")
            return

        await message.edit(result, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await message.edit("没有找到要查询的 ip/域名 ...")
