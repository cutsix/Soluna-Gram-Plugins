# -*- coding: UTF-8 -*-
# pgp-plugin作者: sunmoon
from datetime import datetime

from pyrogram import Client

from solgram import logs
from solgram.listener import listener
from solgram.utils import Message


NOT_FOUND = "没找到哇～"


@listener(command="when", description="查询靓仔的信息")
async def get_id(bot: Client, context: Message):
    if context.reply_to_message:
        target = context.reply_to_message.from_user or context.reply_to_message.sender_chat
        if not target:
            return await context.edit("出错啦！")
    else:
        if not context.parameter or len(context.parameter) != 1:
            return await context.edit("请输入靓仔的用户名（username）.")
        identifier = context.parameter[0]
        try:
            target = await bot.get_users(identifier)
        except Exception as e:
            return await context.edit(f"未找到靓仔 {identifier}. 错误: {str(e)}")

    try:
        user_id = target.id
        username = getattr(target, "username", None)
        settings = await get_official_chat_settings(bot, user_id)

        registration_month = getattr(settings, "registration_date", None) if settings else None
        account_age, years = format_age_from_registration_month(registration_month)
        level = determine_level(years) if registration_month else NOT_FOUND

        result_text = (
            f"昵称：{build_display_name(target)}\n"
            f"用户名：{format_username(username)}\n"
            f"数据中心：{format_data_center(target)}\n"
            f"用户ID: [{user_id}](tg://user?id={user_id})\n"
            f"Premium用户: {format_premium(target)}\n"
            f"{await get_join_time_info(bot, context, user_id)}"
            f"{await get_common_chats_info(bot, user_id)}"
            f"注册年月：{format_registration_month(registration_month)}\n"
            f"账号年龄：{account_age}\n"
            f"级别：{level}"
        )

        await context.edit(result_text)
    except Exception as e:
        await context.edit(f"无法查询靓仔信息: {str(e)}")


async def get_official_chat_settings(bot: Client, user_id: int):
    try:
        return await bot.get_chat_settings(user_id)
    except Exception as e:
        logs.error(f"无法获取用户 {user_id} 的官方账号信息：{e}")
        return None


async def get_join_time_info(bot: Client, context: Message, user_id: int) -> str:
    if context.chat.type == "private":
        return ""

    try:
        chat_member = await bot.get_chat_member(context.chat.id, user_id)
        joined_date = getattr(chat_member, "joined_date", None)
        if joined_date:
            return f"入群时间：{joined_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
    except Exception as e:
        logs.error(f"无法获取用户 {user_id} 的入群时间：{e}")
        return "入群时间：获取失败\n"

    return "入群时间：没找到哇～\n"


async def get_common_chats_info(bot: Client, user_id: int) -> str:
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


def format_username(username: str | None) -> str:
    return f"@{username}" if username else NOT_FOUND


def format_data_center(target) -> str:
    dc_id = getattr(target, "dc_id", None)
    return f"DC{dc_id}" if dc_id else NOT_FOUND


def format_premium(target) -> str:
    return "True" if getattr(target, "is_premium", False) else "False"


def format_registration_month(registration_month: str | None) -> str:
    if not registration_month:
        return NOT_FOUND

    try:
        month_text, year_text = registration_month.split(".")
        month = int(month_text)
        year = int(year_text)
        return f"{year}年{month}月"
    except (TypeError, ValueError):
        return registration_month


def format_age_from_registration_month(registration_month: str | None) -> tuple[str, int]:
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
    elif years >= 3:
        return "老兵"
    elif years > 1:
        return "不如老兵"
    else:
        return "新兵蛋子"
