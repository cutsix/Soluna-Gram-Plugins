import asyncio
import contextlib
import json
from html import escape
from typing import Dict, List, Optional, Tuple

from pyrogram.enums import MessageEntityType, ParseMode
from pyrogram.types import MessageEntity

from solgram.enums import Client, Message
from solgram.listener import listener
from solgram.single_utils import sqlite
from solgram.utils import alias_command

SHORTCUTS_KEY = "shortcuts"


def serialize_entity_type(entity_type) -> str:
    if isinstance(entity_type, str):
        return entity_type
    if getattr(entity_type, "name", None):
        return entity_type.name
    with contextlib.suppress(Exception):
        return MessageEntityType(entity_type).name
    return str(entity_type)


def deserialize_entity_type(entity_type: str):
    if not isinstance(entity_type, str):
        return entity_type
    normalized = entity_type.rsplit(".", 1)[-1].upper()
    if normalized in MessageEntityType.__members__:
        return MessageEntityType[normalized]
    return entity_type


def get_all_shortcuts() -> Dict[str, Dict]:
    raw = sqlite.get(SHORTCUTS_KEY, "{}")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def serialize_entities(entities: Optional[List[MessageEntity]]) -> List[Dict]:
    serialized = []
    for entity in entities or []:
        item = {
            "type": serialize_entity_type(entity.type),
            "offset": entity.offset,
            "length": entity.length,
        }
        for field in ("url", "language", "custom_emoji_id", "expandable"):
            value = getattr(entity, field, None)
            if value is not None:
                item[field] = value
        user = getattr(entity, "user", None)
        if user and getattr(user, "id", None):
            item["user_id"] = user.id
        serialized.append(item)
    return serialized


async def deserialize_entities(
    bot: Client, entities_data: Optional[List[Dict]]
) -> Optional[List[MessageEntity]]:
    entities = []
    for item in entities_data or []:
        try:
            entity_kwargs = {
                "offset": int(item["offset"]),
                "length": int(item["length"]),
            }
            entity_kwargs["type"] = deserialize_entity_type(item["type"])
            for field in ("url", "language", "custom_emoji_id", "expandable"):
                if item.get(field) is not None:
                    entity_kwargs[field] = item[field]
            user_id = item.get("user_id")
            if user_id is not None:
                with contextlib.suppress(Exception):
                    entity_kwargs["user"] = await bot.get_users(user_id)
            entities.append(MessageEntity(**entity_kwargs))
        except Exception:
            continue
    return entities or None


def get_shortcut(name: str) -> Optional[Tuple[str, List[Dict], bool]]:
    shortcuts = get_all_shortcuts()
    data = shortcuts.get(name)
    if data is None:
        return None
    if isinstance(data, str):
        return data, [], False
    if not isinstance(data, dict):
        return None
    text = data.get("text", "")
    entities = data.get("entities", [])
    web_page = bool(data.get("web_page", False))
    if not isinstance(text, str):
        return None
    return text, entities if isinstance(entities, list) else [], web_page


def save_shortcut(
    name: str,
    text: str,
    entities: Optional[List[MessageEntity]] = None,
    web_page: bool = False,
) -> None:
    shortcuts = get_all_shortcuts()
    shortcuts[name] = {
        "text": text,
        "entities": serialize_entities(entities),
        "web_page": web_page,
    }
    sqlite[SHORTCUTS_KEY] = json.dumps(shortcuts, ensure_ascii=False)


def delete_shortcut(name: str) -> bool:
    shortcuts = get_all_shortcuts()
    if name not in shortcuts:
        return False
    del shortcuts[name]
    sqlite[SHORTCUTS_KEY] = json.dumps(shortcuts, ensure_ascii=False)
    return True


async def edit_then_delete(
    message: Message,
    text: str,
    seconds: int = 3,
    parse_mode: Optional[ParseMode] = None,
):
    prompt = await message.edit(text, parse_mode=parse_mode)
    await asyncio.sleep(seconds)
    with contextlib.suppress(Exception):
        await prompt.delete()


def build_help_text() -> str:
    sc_cmd = alias_command("sc")
    schelp_cmd = alias_command("schelp")
    return (
        "<b>快捷方式帮助</b>\n\n"
        f"保存快捷方式：回复一条带文字的消息后，发送 <code>,{sc_cmd} save 名称</code>\n"
        f"使用快捷方式：发送 <code>,{sc_cmd} 名称</code>\n"
        f"查看快捷方式：发送 <code>,{sc_cmd} list</code>\n"
        f"删除快捷方式：发送 <code>,{sc_cmd} remove 名称</code>\n\n"
        "说明：\n"
        "- 会保留原消息文本实体和自定义表情。\n"
        "- 纯媒体消息不能保存为快捷方式。\n"
        "- 提示消息会在几秒后自动删除。\n"
        f"- 使用 <code>,{schelp_cmd}</code> 可再次查看本帮助。"
    )


@listener(
    command="sc",
    description="快捷方式系统，支持保存文本格式和网页预览",
    parameters="[<名称>|save <名称>|remove <名称>|list]",
)
async def quick_shortcut(bot: Client, message: Message):
    args = message.parameter or []
    if not args:
        await edit_then_delete(
            message,
            (
                "请指定要使用的快捷方式名称\n"
                f"使用 <code>,{alias_command('schelp')}</code> 查看帮助"
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    action = args[0]

    if action == "list":
        shortcuts = get_all_shortcuts()
        if not shortcuts:
            await edit_then_delete(message, "还没有保存任何快捷方式")
            return
        lines = ["<b>已保存的快捷方式</b>", ""]
        for name in sorted(shortcuts):
            data = shortcuts.get(name, {})
            suffix = " [预览]" if isinstance(data, dict) and data.get("web_page") else ""
            lines.append(f"<code>{escape(name)}</code>{suffix}")
        await edit_then_delete(
            message, "\n".join(lines), seconds=10, parse_mode=ParseMode.HTML
        )
        return

    if action == "save":
        if len(args) < 2:
            await edit_then_delete(
                message,
                f"请指定快捷方式名称\n例如：<code>,{alias_command('sc')} save hello</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        reply = message.reply_to_message
        if not reply:
            await edit_then_delete(message, "请回复一条消息以保存新的快捷方式")
            return

        text = reply.text or reply.caption
        entities = reply.entities if reply.text else reply.caption_entities
        web_page = bool(getattr(reply, "web_page", None))
        if not text:
            await edit_then_delete(message, "无法保存空消息或纯媒体消息")
            return

        name = args[1]
        save_shortcut(name, text, entities, web_page)
        await edit_then_delete(
            message,
            f"快捷方式 <code>{escape(name)}</code> 保存成功",
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "remove":
        if len(args) < 2:
            await edit_then_delete(
                message,
                f"请指定要删除的快捷方式名称\n例如：<code>,{alias_command('sc')} remove hello</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        name = args[1]
        if delete_shortcut(name):
            await edit_then_delete(
                message,
                f"快捷方式 <code>{escape(name)}</code> 已删除",
                parse_mode=ParseMode.HTML,
            )
        else:
            await edit_then_delete(
                message,
                f"快捷方式 <code>{escape(name)}</code> 不存在",
                parse_mode=ParseMode.HTML,
            )
        return

    shortcut = get_shortcut(action)
    if not shortcut:
        await edit_then_delete(
            message,
            f"快捷方式 <code>{escape(action)}</code> 不存在",
            parse_mode=ParseMode.HTML,
        )
        return

    text, entities_data, web_page = shortcut
    entities = await deserialize_entities(bot, entities_data)
    try:
        await bot.send_message(
            message.chat.id,
            text,
            entities=entities,
            parse_mode=ParseMode.DISABLED,
            disable_web_page_preview=not web_page,
            message_thread_id=message.message_thread_id,
        )
    except Exception:
        try:
            await bot.send_message(
                message.chat.id,
                text,
                parse_mode=ParseMode.DISABLED,
                disable_web_page_preview=not web_page,
                message_thread_id=message.message_thread_id,
            )
        except Exception as exc:
            await edit_then_delete(
                message,
                f"发送快捷方式失败：<code>{escape(str(exc))}</code>",
                parse_mode=ParseMode.HTML,
            )
            return
    await message.safe_delete()


@listener(command="schelp", description="显示快捷方式使用帮助")
async def shortcut_help(message: Message):
    await edit_then_delete(
        message,
        build_help_text(),
        seconds=15,
        parse_mode=ParseMode.HTML,
    )
