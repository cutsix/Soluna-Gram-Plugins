from io import BytesIO
from solgram.enums import Client, Message
from solgram.listener import listener
from solgram.utils import alias_command
from solgram.config import Config
from solgram import log


class HisMsg:
    LANGUAGES = {
        "en": {
            "help": "Query the message history of the specified user in the group\n"
            f"Usage: \n`-{alias_command('his')} <user> [-n <num>] [-p <page>]`"
            "\n&nbsp;&nbsp; <i>user</i>: username or user_id; <i>num</i>: Limits the number of messages per page (default: 30)\n"
            "You can just reply to a message without <i>user</i> argument",
            "processing": f"{alias_command('his')}: ⏳ Querying...",
            "query_success": "✅ Queried history message. chat_id: {chat_id} user: {user}",
            "query_failed": "❌ Failed to query history message.",
            "media": {
                "AUDIO": "🎵 [AUDIO]:",
                "DOCUMENT": "📄 [DOCUMENT]:",
                "PHOTO": "📷 [PHOTO]:",
                "STICKER": "🖼️ [STICKER]:",
                "VIDEO": "🎥 [VIDEO]:",
                "ANIMATION": "🎬 [ANIMATION]:",
                "VOICE": "🎤 [VOICE]:",
                "VIDEO_NOTE": "📹 [VIDEO_NOTE]:",
                "CONTACT": "👤 [CONTACT]:",
                "LOCATION": "📍 [LOCATION]:",
                "VENUE": "📍 [VENUE]:",
                "POLL": "📊 [POLL]:",
                "WEB_PAGE": "🌐 [WEB_PAGE]:",
                "DICE": "🎲 [DICE]:",
                "GAME": "🎮 [GAME]:",
            },
            "service": {
                "service": "ℹ️ [Service_Message]: ",
                "PINNED_MESSAGE": "📌 Pinned: ",
                "NEW_CHAT_TITLE": "📝 New chat title: ",
            },
        },
        "zh-cn": {
            "help": "查询指定用户在群内的发言历史\n"
            f"使用方法: \n`-{alias_command('his')} <user> [-n <num>] [-p <page>]`"
            "\n&nbsp;&nbsp; <i>user</i>: 可以是用户名或者用户id; <i>num</i>: 每页显示的消息数量(默认30)\n"
            "你也可以直接回复一条消息，不带 <i>user</i> 参数",
            "processing": f"{alias_command('his')}: ⏳ 正在查询...",
            "query_success": "✅ 查询历史消息完成. 群组id: {chat_id} 用户: {user}",
            "query_failed": "❌ 查询历史消息失败.",
            "media": {
                "AUDIO": "🎵 [音频]:",
                "DOCUMENT": "📄 [文档]:",
                "PHOTO": "📷 [图片]:",
                "STICKER": "🖼️ [贴纸]:",
                "VIDEO": "🎥 [视频]:",
                "ANIMATION": "🎬 [动画表情]:",
                "VOICE": "🎤 [语音]:",
                "VIDEO_NOTE": "📹 [视频备注]:",
                "CONTACT": "👤 [联系人]:",
                "LOCATION": "📍 [位置]:",
                "VENUE": "📍 [场地]:",
                "POLL": "📊 [投票]:",
                "WEB_PAGE": "🌐 [网页]:",
                "DICE": "🎲 [骰子]:",
                "GAME": "🎮 [游戏]:",
            },
            "service": {
                "service": "ℹ️ [服务消息]: ",
                "PINNED_MESSAGE": "📌 置顶了: ",
                "NEW_CHAT_TITLE": "📝 新的群组名字: ",
            },
        },
    }
    DEFAULT_PER_PAGE = 30

    def __init__(self):
        try:
            self.lang_dict = self.LANGUAGES[Config.LANGUAGE]
        except:
            self.lang_dict = self.LANGUAGES["en"]

    def lang(self, text: str, default: str = "") -> str:
        res = self.lang_dict.get(text, default)
        if res == "":
            res = text
        return res


his_msg = HisMsg()


@listener(
    command="his",
    groups_only=True,
    need_admin=True,
    description=his_msg.lang("help"),
    parameters=his_msg.lang("arg", "<user> [-n <num>] [-p <page>]"),
)
async def his(bot: Client, message: Message):
    user = ""
    num = his_msg.DEFAULT_PER_PAGE
    page = 1
    chat_id = message.chat.id

    try:
        if "-n" in message.parameter:
            num_index = message.parameter.index("-n")
            if len(message.parameter) > num_index + 1:
                num = int(message.parameter[num_index + 1])

        if "-p" in message.parameter:
            page_index = message.parameter.index("-p")
            if len(message.parameter) > page_index + 1:
                page = int(message.parameter[page_index + 1])

        if len(message.parameter) > 0 and message.parameter[0] not in ["-n", "-p"]:
            user = message.parameter[0]
        elif message.reply_to_message_id is not None:
            user = int(message.reply_to_message.from_user.id)
        else:
            return await message.edit(his_msg.lang("help"))

    except Exception:
        return await message.edit(his_msg.lang("help"))
    
    await message.edit(his_msg.lang("processing"))

    count = 0
    results = ""
    total_messages = 0
    try:
        async for _ in bot.search_messages(chat_id, from_user=user):
            total_messages += 1

        total_pages = (total_messages // num) + (1 if total_messages % num else 0)

        if page > total_pages:
            return await message.edit(f"❌ Page {page} exceeds total pages ({total_pages}).")

        skip_count = (page - 1) * num

        messages = []
        async for msg in bot.search_messages(chat_id, limit=total_messages, from_user=user):
            messages.append(msg)

        page_messages = messages[skip_count:skip_count + num]

        if not page_messages:
            return await message.edit(f"❌ No messages found for page {page}.")

        if len(page_messages) > 30:
            html_content = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                    }}
                    .message {{
                        margin: 5px 0;
                        padding: 10px;
                        border-bottom: 1px solid #ddd;
                    }}
                    .message a {{
                        text-decoration: none;
                        color: #2a9d8f;
                    }}
                </style>
            </head>
            <body>
                <h2>用户 <code>{user}</code> 的历史消息</h2>
            """
            count = 0
            for msg in page_messages:
                count += 1
                message_link = msg.link
                message_text = msg.text

                if message_text is None and msg.media is not None:
                    media_type = str(msg.media).split(".")[1]
                    media_caption = msg.caption if msg.caption is not None else ""
                    message_text = his_msg.lang("media")[media_type] + media_caption
                if msg.service is not None:
                    service_type = str(msg.service).split(".")[1]
                    service_text = his_msg.lang("service")[service_type] if service_type in his_msg.lang("service") else ""
                    message_text = his_msg.lang("service")["service"] + service_text

                if len(message_text) > 50:
                    message_text = f"{message_text[:50]}..."

                html_content += f'<div class="message"><a href="{message_link}">{count}. {message_text}</a></div>\n'

            html_content += "</body></html>"

            html_bytes = BytesIO(html_content.encode('utf-8'))
            html_bytes.name = f"message_history_{user}.html"

            await bot.send_document(chat_id, html_bytes, caption=f"📄 以下是用户 {user} 的消息记录 (超过30条，生成HTML文件).")
            await message.delete()
            return

        for msg in page_messages:
            count += 1
            message_link = msg.link
            message_text = msg.text

            if message_text is None and msg.media is not None:
                media_type = str(msg.media).split(".")[1]
                media_caption = msg.caption if msg.caption is not None else ""
                message_text = his_msg.lang("media")[media_type] + media_caption
            if msg.service is not None:
                service_type = str(msg.service).split(".")[1]
                service_text = his_msg.lang("service")[service_type] if service_type in his_msg.lang("service") else ""
                message_text = his_msg.lang("service")["service"] + service_text

            if len(message_text) > 15:
                message_text = f"{count}.  {message_text[:15]}..."
            else:
                message_text = f"{count}. {message_text}"

            results += f'\n<a href="{message_link}">{message_text}</a> \n'

        await message.edit(
            f"<b>Message History</b> | <code>{user}</code> | 🔍 \n{results}\n\n"
            f"<b>Total:</b> {total_messages} | <b>Page:</b> {page}/{total_pages} | <b>Per:</b> {num}",
            disable_web_page_preview=True,
        )
        await log(his_msg.lang("query_success").format(chat_id=chat_id, user=user))

    except Exception as e:
        await message.edit(f"❌ [HIS_ERROR]: {e}")
        await log(f"[HIS_ERROR]: {e}")
