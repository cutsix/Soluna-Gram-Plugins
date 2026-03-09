# -*- coding: UTF-8 -*-
# pgp-plugin作者: sunmoon
from asyncio import create_task
from bisect import bisect_left
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from pyrogram import Client

from solgram import logs
from solgram.listener import listener
from solgram.utils import Message


NOT_FOUND = "没找到哇～"
REPORT_BOT_USERNAME = "@solunagram_bot"
UID_TIMESTAMPS = [
    [1000000, 1380326400],
    [2768409, 1383264000],
    [7679610, 1388448000],
    [11538514, 1391212000],
    [15835244, 1392940000],
    [23646077, 1393459000],
    [38015510, 1393632000],
    [44634663, 1399334000],
    [46145305, 1400198000],
    [54845238, 1411257000],
    [63263518, 1414454000],
    [101260938, 1425600000],
    [101323197, 1426204000],
    [103151531, 1433376000],
    [103258382, 1432771000],
    [109393468, 1439078000],
    [111220210, 1429574000],
    [112594714, 1439683000],
    [116812045, 1437696000],
    [122600695, 1437782000],
    [124872445, 1439856000],
    [125828524, 1444003000],
    [130029930, 1441324000],
    [133909606, 1444176000],
    [143445125, 1448928000],
    [148670295, 1452211000],
    [152079341, 1453420000],
    [157242073, 1446768000],
    [171295414, 1457481000],
    [181783990, 1460246000],
    [222021233, 1465344000],
    [225034354, 1466208000],
    [278941742, 1473465000],
    [285253072, 1476835000],
    [294851037, 1479600000],
    [297621225, 1481846000],
    [328594461, 1482969000],
    [337808429, 1487707000],
    [341546272, 1487782000],
    [352940995, 1487894000],
    [369669043, 1490918000],
    [400169472, 1501459000],
    [616816630, 1529625600],
    [681896077, 1532821500],
    [727572658, 1543708800],
    [796147074, 1541371800],
    [925078064, 1563290000],
    [928636984, 1581513420],
    [1054883348, 1585674420],
    [1057704545, 1580393640],
    [1145856008, 1586342040],
    [1227964864, 1596127860],
    [1382531194, 1600188120],
    [1658586909, 1613148540],
    [1660971491, 1613329440],
    [1692464211, 1615402500],
    [1719536397, 1619293500],
    [1721844091, 1620224820],
    [1772991138, 1617540360],
    [1807942741, 1625520300],
    [1893429550, 1622040000],
    [1972424006, 1631669400],
    [1974255900, 1634000000],
    [2030606431, 1631992680],
    [2041327411, 1631989620],
    [2078711279, 1634321820],
    [2104178931, 1638353220],
    [2120496865, 1636714020],
    [2123596685, 1636503180],
    [2138472342, 1637590800],
    [3318845111, 1618028800],
    [4317845111, 1620028800],
    [5162494923, 1652449800],
    [5186883095, 1648764360],
    [5304951856, 1656718440],
    [5317829834, 1653152820],
    [5318092331, 1652024220],
    [5336336790, 1646368100],
    [5362593868, 1652024520],
    [5387234031, 1662137700],
    [5396587273, 1648014800],
    [5409444610, 1659025020],
    [5416026704, 1660925460],
    [5465223076, 1661710860],
    [5480654757, 1660926300],
    [5499934702, 1662130740],
    [5513192189, 1659626400],
    [6813121418, 1698489600],
    [6865576492, 1699052400],
    [6925870357, 1701192327],
]
UID_SAMPLE_IDS = [item[0] for item in UID_TIMESTAMPS]


@listener(command="when", description="查询靓仔的信息")
async def get_id(bot: Client, context: Message):
    target, is_user_target = await resolve_query_target(bot, context)
    if target is None:
        return

    try:
        user_id = target.id
        username = getattr(target, "username", None)
        registration_month = await resolve_registration_month(
            bot, user_id, is_user_target
        )
        account_age, years = format_age_from_registration_month(registration_month)
        level = determine_level(years) if registration_month else NOT_FOUND

        result_text = (
            f"昵称：{build_display_name(target)}\n"
            f"用户名：{format_username(username)}\n"
            f"数据中心：{format_data_center(target)}\n"
            f"用户ID: {format_target_id(user_id, is_user_target)}\n"
            f"Premium用户: {format_premium(target)}\n"
            f"{await get_join_time_info(bot, context, user_id, is_user_target)}"
            f"{await get_common_chats_info(bot, user_id, is_user_target)}"
            f"注册年月：{format_registration_month(registration_month)}\n"
            f"账号年龄：{account_age}\n"
            f"级别：{level}"
        )

        await context.edit(result_text)
    except Exception as e:
        await context.edit(f"无法查询靓仔信息: {str(e)}")


async def resolve_query_target(
    bot: Client, context: Message
) -> Tuple[Optional[Any], bool]:
    if context.reply_to_message:
        if context.reply_to_message.from_user:
            return context.reply_to_message.from_user, True
        if context.reply_to_message.sender_chat:
            return context.reply_to_message.sender_chat, False
        await context.edit("出错啦！")
        return None, False

    if not context.parameter or len(context.parameter) != 1:
        await context.edit("请输入靓仔的用户名或ID.")
        return None, False

    identifier = context.parameter[0]
    try:
        return await bot.get_users(identifier), True
    except Exception as e:
        await context.edit(f"未找到靓仔 {identifier}. 错误: {str(e)}")
        return None, False


async def resolve_registration_month(
    bot: Client, user_id: int, is_user_target: bool
) -> Optional[str]:
    if not is_user_target:
        return None

    official_registration_month = await get_official_registration_month(bot, user_id)
    if official_registration_month:
        create_task(
            report_registration_sample(bot, user_id, official_registration_month)
        )
        return official_registration_month

    estimated_datetime = estimate_registration_datetime(user_id)
    if not estimated_datetime:
        return None
    return registration_month_from_datetime(estimated_datetime)


async def get_official_registration_month(
    bot: Client, user_id: int
) -> Optional[str]:
    settings = await get_official_chat_settings(bot, user_id)
    return getattr(settings, "registration_date", None) if settings else None


async def get_official_chat_settings(bot: Client, user_id: int):
    try:
        return await bot.get_chat_settings(user_id)
    except Exception as e:
        logs.error(f"无法获取用户 {user_id} 的官方账号信息：{e}")
        return None


def estimate_registration_datetime(user_id: int) -> Optional[datetime]:
    if not UID_TIMESTAMPS:
        return None

    if user_id <= UID_TIMESTAMPS[0][0]:
        return datetime.fromtimestamp(UID_TIMESTAMPS[0][1], tz=timezone.utc)
    if user_id >= UID_TIMESTAMPS[-1][0]:
        return datetime.fromtimestamp(UID_TIMESTAMPS[-1][1], tz=timezone.utc)

    index = bisect_left(UID_SAMPLE_IDS, user_id)
    if index < len(UID_TIMESTAMPS) and UID_TIMESTAMPS[index][0] == user_id:
        return datetime.fromtimestamp(UID_TIMESTAMPS[index][1], tz=timezone.utc)

    prev_id, prev_timestamp = UID_TIMESTAMPS[index - 1]
    next_id, next_timestamp = UID_TIMESTAMPS[index]
    if next_id == prev_id:
        return datetime.fromtimestamp(prev_timestamp, tz=timezone.utc)

    ratio = (user_id - prev_id) / (next_id - prev_id)
    estimated_timestamp = int(
        prev_timestamp + ratio * (next_timestamp - prev_timestamp)
    )
    return datetime.fromtimestamp(estimated_timestamp, tz=timezone.utc)


def registration_month_from_datetime(value: datetime) -> str:
    return f"{value.month}.{value.year}"


def registration_month_to_report_value(registration_month: str) -> Optional[str]:
    try:
        month_text, year_text = registration_month.split(".")
        month = int(month_text)
        year = int(year_text)
        if month < 1 or month > 12:
            return None
        return f"{year:04d}-{month:02d}"
    except (TypeError, ValueError):
        return None


async def report_registration_sample(
    bot: Client, user_id: int, registration_month: str
) -> None:
    report_value = registration_month_to_report_value(registration_month)
    if not report_value:
        return

    try:
        await bot.send_message(
            REPORT_BOT_USERNAME, f"check_data:{user_id}:{report_value}"
        )
    except Exception as e:
        logs.error(f"无法上报用户 {user_id} 的注册时间样本：{e}")


async def get_join_time_info(
    bot: Client, context: Message, user_id: int, is_user_target: bool
) -> str:
    if context.chat.type == "private":
        return ""
    if not is_user_target:
        return f"入群时间：{NOT_FOUND}\n"

    try:
        chat_member = await bot.get_chat_member(context.chat.id, user_id)
        joined_date = getattr(chat_member, "joined_date", None)
        if joined_date:
            return f"入群时间：{joined_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
    except Exception as e:
        logs.error(f"无法获取用户 {user_id} 的入群时间：{e}")
        return "入群时间：获取失败\n"

    return f"入群时间：{NOT_FOUND}\n"


async def get_common_chats_info(
    bot: Client, user_id: int, is_user_target: bool
) -> str:
    if not is_user_target:
        return f"共同群组：{NOT_FOUND}\n"

    try:
        common_chats = await bot.get_common_chats(user_id)
        return f"共同群组：{len(common_chats)} 个\n"
    except Exception as e:
        logs.error(f"无法获取与用户 {user_id} 的共同群组：{e}")
        return "共同群组：获取失败\n"


def build_display_name(target) -> str:
    title = getattr(target, "title", None)
    if title:
        return title

    first_name = getattr(target, "first_name", "") or ""
    last_name = getattr(target, "last_name", "") or ""
    full_name = f"{first_name} {last_name}".strip()
    return full_name or NOT_FOUND


def format_username(username: Optional[str]) -> str:
    return f"@{username}" if username else NOT_FOUND


def format_data_center(target) -> str:
    dc_id = getattr(target, "dc_id", None)
    return f"DC{dc_id}" if dc_id else NOT_FOUND


def format_target_id(target_id: int, is_user_target: bool) -> str:
    if is_user_target:
        return f"[{target_id}](tg://user?id={target_id})"
    return f"`{target_id}`"


def format_premium(target) -> str:
    return "True" if getattr(target, "is_premium", False) else "False"


def format_registration_month(registration_month: Optional[str]) -> str:
    if not registration_month:
        return NOT_FOUND

    try:
        month_text, year_text = registration_month.split(".")
        month = int(month_text)
        year = int(year_text)
        return f"{year}年{month}月"
    except (TypeError, ValueError):
        return registration_month


def format_age_from_registration_month(
    registration_month: Optional[str],
) -> Tuple[str, int]:
    if not registration_month:
        return NOT_FOUND, 0

    try:
        month_text, year_text = registration_month.split(".")
        month = int(month_text)
        year = int(year_text)
        now = datetime.now()
        total_months = (now.year - year) * 12 + (now.month - month)

        if total_months < 0:
            return NOT_FOUND, 0

        years, months = divmod(total_months, 12)
        if years > 0 and months > 0:
            return f"{years}年{months}月", years
        if years > 0:
            return f"{years}年", years
        if months > 0:
            return f"{months}月", 0
        return "不到1个月", 0
    except (TypeError, ValueError):
        return NOT_FOUND, 0


def determine_level(years: int) -> str:
    """根据账号年龄确定用户级别"""
    if years >= 10:
        return "十年老逼登"
    if years >= 3:
        return "老兵"
    if years > 1:
        return "不如老兵"
    return "新兵蛋子"
