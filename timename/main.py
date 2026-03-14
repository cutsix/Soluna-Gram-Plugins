import traceback
from datetime import datetime, timedelta, timezone

from solgram import logs
from solgram.scheduler import scheduler
from solgram.services import bot

styled_numbers = {
    "0": "𝟬",
    "1": "𝟭",
    "2": "𝟮",
    "3": "𝟯",
    "4": "𝟰",
    "5": "𝟱",
    "6": "𝟲",
    "7": "𝟳",
    "8": "𝟴",
    "9": "𝟵",
    ":": ":",
}


def convert_to_styled(text: str) -> str:
    return "".join(styled_numbers.get(char, char) for char in text)


def get_status_emoji(hour: int) -> str:
    if 0 <= hour < 6:
        return "💤"
    if 6 <= hour < 7:
        return "☀️"
    if 7 <= hour < 8:
        return "💄"
    if 8 <= hour < 9:
        return "🍳"
    if 9 <= hour < 10:
        return "🪞"
    if 10 <= hour < 11:
        return "🐟"
    if 11 <= hour < 12:
        return "💅"
    if 12 <= hour < 13:
        return "🍚"
    if 13 <= hour < 14:
        return "🥱"
    if 14 <= hour < 15:
        return "🧹"
    if 15 <= hour < 16:
        return "🛍️"
    if 16 <= hour < 17:
        return "🍰"
    if 17 <= hour < 18:
        return "🥗"
    if 18 <= hour < 19:
        return "🥘"
    if 19 <= hour < 20:
        return "🍓"
    if 20 <= hour < 21:
        return "🧸"
    if 21 <= hour < 22:
        return "🛁"
    if 22 <= hour < 23:
        return "🧴"
    return "🌙"


@scheduler.scheduled_job("cron", second=0, id="autochangename")
async def change_name_auto():
    try:
        dt = (
            datetime.utcnow()
            .replace(tzinfo=timezone.utc)
            .astimezone(timezone(timedelta(hours=8)))
        )
        hour = dt.hour
        minute = dt.strftime("%M")
        styled_time = convert_to_styled(f"{hour}:{minute}")
        last_name = f"{styled_time} {get_status_emoji(hour)}"

        await bot.update_profile(last_name=last_name)

        me = await bot.get_me()
        if me.last_name != last_name:
            raise RuntimeError("修改 last_name 失败")
    except Exception as exc:
        trace = "\n".join(traceback.format_exception(exc))
        logs.error(f"更新失败!\n{trace}")
