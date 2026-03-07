import contextlib
import json

from asyncio import sleep
from typing import Optional

from pyrogram.errors import PeerIdInvalid
from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.raw.functions.stickers import CreateStickerSet
from pyrogram.raw.types import (
    InputStickerSetShortName,
    InputDocument,
    InputStickerSetItem,
)
from pyrogram.raw.types.messages import StickerSet
from pyrogram.file_id import FileId

from solgram.listener import listener
from solgram.services import bot, sqlite
from solgram.enums import Message
from solgram.single_utils import safe_remove
from solgram.utils import alias_command


class CannotToStickerSetError(Exception):
    """
    Occurs when program cannot change a message to a sticker set
    """

    def __init__(self):
        super().__init__("无法将此消息转换为贴纸")


class NoStickerSetNameError(Exception):
    """
    Occurs when no username is provided
    """

    def __init__(self, string: str = "请先设置用户名"):
        super().__init__(string)


class StickerSetFullError(Exception):
    """
    Occurs when the sticker set is full
    """

    def __init__(self):
        super().__init__("贴纸包已满")


async def get_pack(name: str):
    try:
        return await bot.invoke(
            GetStickerSet(stickerset=InputStickerSetShortName(short_name=name), hash=0)
        )
    except Exception as e:  # noqa
        raise NoStickerSetNameError("贴纸名名称错误或者不存在") from e


class Sticker:
    message: Message
    sticker_set: str
    custom_sticker_set: bool
    emoji: str
    should_forward: Message
    is_animated: bool
    is_video: bool
    nums: int
    document: Optional[InputDocument]
    document_path: Optional[str]
    software: str = "Soluna-Gram"

    def __init__(
        self,
        message: Message,
        sticker_set: str = "",
        emoji: str = "😀",
        should_forward: Message = None,
    ):
        self.message = message
        self.sticker_set = sticker_set
        self.custom_sticker_set = False
        self.load_custom_sticker_set()
        self.emoji = emoji
        self.should_forward = should_forward
        self.should_create = False
        self.is_animated = False
        self.is_video = False
        self.nums = 1
        self.document = None
        self.document_path = None

    @staticmethod
    def get_custom_sticker_set():
        return sqlite.get("sticker_set", None)

    @staticmethod
    def set_custom_sticker_get(name: str):
        sqlite["sticker_set"] = name

    @staticmethod
    def del_custom_sticker_set():
        del sqlite["sticker_set"]

    def load_custom_sticker_set(self):
        if name := self.get_custom_sticker_set():
            self.sticker_set = name
            self.custom_sticker_set = True

    async def generate_sticker_set(self, time: int = 1):
        self.nums = time
        if not self.sticker_set or time > 1:
            me = await bot.get_me()
            if not me.username:
                raise NoStickerSetNameError()
            self.sticker_set = f"{me.username}_{time}"
            if self.is_video:
                self.sticker_set += "_video"
            elif self.is_animated:
                self.sticker_set += "_animated"
        try:
            await self.check_pack_full()
        except NoStickerSetNameError:
            self.should_create = True
        except StickerSetFullError:
            await self.generate_sticker_set(time + 1)

    async def check_pack_full(self):
        pack: StickerSet = await get_pack(self.sticker_set)
        if pack.set.count == 120:
            raise StickerSetFullError()

    async def process_sticker(self):
        if not (self.should_forward and self.should_forward.sticker):
            raise CannotToStickerSetError()
        sticker_ = self.should_forward.sticker
        self.is_video = sticker_.is_video
        self.is_animated = sticker_.is_animated
        self.emoji = sticker_.emoji or self.emoji
        if self.is_video or self.is_animated:
            self.document_path = await self.download_file()
        file = FileId.decode(sticker_.file_id)
        self.document = InputDocument(
            id=file.media_id,
            access_hash=file.access_hash,
            file_reference=file.file_reference,
        )

    async def download_file(self) -> str:
        return await self.should_forward.download()

    async def upload_file(self):
        if not self.document_path:
            return
        with contextlib.suppress(Exception):
            msg = await bot.send_document(
                429000, document=self.document_path, force_document=True
            )
            file = FileId.decode(msg.document.file_id)
            self.document = InputDocument(
                id=file.media_id,
                access_hash=file.access_hash,
                file_reference=file.file_reference,
            )
        safe_remove(self.document_path)

    async def create_sticker_set(self):
        me = await bot.get_me()
        title = f"@{me.username} 的私藏（{self.nums}）" if me.username else self.sticker_set
        if self.is_video:
            title += "（Video）"
        elif self.is_animated:
            title += "（Animated）"
        try:
            await bot.invoke(
                CreateStickerSet(
                    user_id=await bot.resolve_peer((await bot.get_me()).id),
                    title=title,
                    short_name=self.sticker_set,
                    stickers=[
                        InputStickerSetItem(document=self.document, emoji=self.emoji)
                    ],
                    animated=self.is_animated,
                    videos=self.is_video,
                )
            )
        except Exception as e:
            raise NoStickerSetNameError("贴纸包名称非法，请换一个") from e

    async def add_to_sticker_set(self):
        async with bot.conversation(429000) as conv:
            await conv.ask("/start")
            await sleep(0.3)
            await conv.mark_as_read()
            await conv.ask("/cancel")
            await sleep(0.3)
            await conv.mark_as_read()
            await conv.ask("/addsticker")
            await sleep(0.3)
            await conv.mark_as_read()
            resp: Message = await conv.ask(self.sticker_set)
            await sleep(0.3)
            if resp.text == "Invalid set selected.":
                raise NoStickerSetNameError("这个贴纸包好像不属于你~")
            await conv.mark_as_read()
            if self.is_video or self.is_animated:
                await self.upload_file()
            else:
                await self.should_forward.forward("Stickers")
            resp: Message = await conv.get_response()
            await sleep(0.3)
            if not resp.text.startswith("Thanks!"):
                raise NoStickerSetNameError("这个贴纸包类型好像不匹配~")
            await conv.mark_as_read()
            await conv.ask(self.emoji)
            await sleep(0.3)
            await conv.mark_as_read()
            await conv.ask("/done")
            await sleep(0.3)
            await conv.mark_as_read()
            await conv.ask("/done")
            await sleep(0.3)
            await conv.mark_as_read()

    async def to_sticker_set(self):
        await self.generate_sticker_set()
        if not self.sticker_set:
            raise NoStickerSetNameError()
        if self.should_create:
            await self.upload_file()
            await self.create_sticker_set()
        else:
            await self.add_to_sticker_set()

    def mention(self):
        return f"[{self.sticker_set}](https://t.me/addstickers/{self.sticker_set})"

    @staticmethod
    def get_all_sticker_sets() -> dict:
        """获取所有保存的贴纸包信息"""
        return json.loads(sqlite.get("sticker_sets", "{}"))

    @staticmethod
    def save_sticker_set(name: str, title: str, alias: str = None):
        """保存贴纸包信息，保留原有的快捷命名
        Args:
            name: 贴纸包名称
            title: 贴纸包标题
            alias: 快捷命名
        """
        sticker_sets = json.loads(sqlite.get("sticker_sets", "{}"))
        if name in sticker_sets:
            # 如果贴纸包已存在且提供了新的别名，则更新别名
            if alias:
                sticker_sets[name]["alias"] = alias
            # 更新标题
            sticker_sets[name]["title"] = title
        else:
            # 如果是新贴纸包，创建新记录
            sticker_sets[name] = {
                "title": title,
                "alias": alias
            }
        sqlite["sticker_sets"] = json.dumps(sticker_sets)

    @staticmethod
    def get_sticker_by_alias(alias: str) -> str:
        """通过快捷命名获取贴纸包名称"""
        sticker_sets = json.loads(sqlite.get("sticker_sets", "{}"))
        for name, info in sticker_sets.items():
            if info.get("alias") == alias:
                return name
        return None

    @staticmethod
    def delete_sticker_set(name: str) -> bool:
        """删除贴纸包记录
        Args:
            name: 贴纸包名称
        Returns:
            bool: 是否删除成功
        """
        sticker_sets = json.loads(sqlite.get("sticker_sets", "{}"))
        if name in sticker_sets:
            del sticker_sets[name]
            sqlite["sticker_sets"] = json.dumps(sticker_sets)
            return True
        return False

    def help_config(self) -> str:
        pack = self.mention() if self.sticker_set else "无法保存，请设置用户名"
        sticker_sets = self.get_all_sticker_sets()
        sets_list = "\n".join([
            f"▫️ {name}" + (f" -> {info.get('alias')}" if info.get('alias') else "")
            for name, info in sticker_sets.items()
        ])
        
        return (
            f"欢迎使用 sticker 插件\n\n"
            f"当前贴纸包：{pack}\n\n"
            f"已保存的贴纸包：\n{sets_list if sets_list else '暂无保存的贴纸包'}\n\n"
            f"使用方法：\n"
            f"1️⃣ 设置默认贴纸包：\n  <code>,{alias_command('s')} 贴纸包名</code>\n"
            f"2️⃣ 取消默认贴纸包：\n  <code>,{alias_command('s')} cancel</code>\n"
            f"3️⃣ 查看已保存贴纸包：\n  <code>,{alias_command('s')} list</code>\n"
            f"4️⃣ 直接保存到指定贴纸包：\n  <code>,{alias_command('s')} 贴纸包名 save</code>\n"
            f"5️⃣ 设置贴纸包快捷命名：\n  <code>,{alias_command('s')} set 贴纸包名 快捷名</code>\n"
            f"6️⃣ 使用快捷命名保存：\n  <code>,{alias_command('s')} 快捷名</code>\n"
            f"7️⃣ 删除贴纸包记录：\n  <code>,{alias_command('s')} del 贴纸包名</code>"
        )

    def get_config(self) -> str:
        pack = self.mention() if self.sticker_set else "无法保存，请设置用户名"
        return (
            f"当前贴纸包：{pack}\n"
            f"使用 <code>,{alias_command('s')} help</code> 查看完整帮助"
        )


@listener(
    command="s",
    parameters="[help/贴纸包名/cancel/list/set/del] [贴纸包名] [快捷名]",
    description="保存贴纸到自己的贴纸包",
    need_admin=True,
)
async def sticker(message: Message):
    one_sticker = Sticker(message, should_forward=message.reply_to_message)
    
    # 显示帮助信息
    if message.arguments == "help":
        help_msg = await message.edit(one_sticker.help_config())
        await sleep(8)
        return await help_msg.delete()

    # 无参数时直接保存到默认贴纸包
    if not message.arguments:
        if not message.reply_to_message:
            help_msg = await message.edit(one_sticker.get_config())
            await sleep(5)
            return await help_msg.delete()
        
        try:
            await one_sticker.process_sticker()
            await one_sticker.to_sticker_set()
        except PeerIdInvalid:
            return await message.edit("请先私聊一次 @Stickers 机器人")
        except Exception as e:
            await message.edit(f"收藏到贴纸包失败：{e}")
            await sleep(3)
            return await message.delete()
        
        await message.edit(f"收藏到贴纸包 {one_sticker.mention()} 成功")
        await sleep(3)
        return await message.delete()

    # 列出所有保存的贴纸包
    if message.arguments == "list":
        sticker_sets = one_sticker.get_all_sticker_sets()
        if not sticker_sets:
            return await message.edit("还没有保存任何贴纸包")
        
        sets_list = "📝 已保存的贴纸包：\n\n" + "\n".join([
            f"▫️ [{name}](https://t.me/addstickers/{name})" + 
            (f" -> {info.get('alias')}" if info.get('alias') else "")
            for name, info in sticker_sets.items()
        ])
        await message.edit(sets_list)
        await sleep(10)
        return await message.delete()

    # 设置贴纸包快捷命名
    if message.parameter[0] == "set":
        if len(message.parameter) != 3:
            await message.edit("请使用格式：,s set 贴纸包名 快捷名")
            await sleep(3)
            return await message.delete()
        
        sticker_name = message.parameter[1]
        alias = message.parameter[2]
        
        try:
            await get_pack(sticker_name)  # 验证贴纸包是否存在
            one_sticker.save_sticker_set(sticker_name, f"@{(await bot.get_me()).username} 的私藏", alias)
            await message.edit(f"已为贴纸包 {sticker_name} 设置快捷命名 {alias}")
            await sleep(3)
            return await message.delete()
        except Exception as e:
            await message.edit(f"设置快捷命名失败：{e}")
            await sleep(3)
            return await message.delete()

    # 处理快捷命名的情况
    if len(message.parameter) == 1:
        # 检查是否是快捷命名
        if sticker_name := one_sticker.get_sticker_by_alias(message.parameter[0]):
            if not message.reply_to_message:
                await message.edit("请回复一个贴纸")
                await sleep(3)
                return await message.delete()
            
            one_sticker.sticker_set = sticker_name
            try:
                await one_sticker.process_sticker()
                await one_sticker.to_sticker_set()
            except PeerIdInvalid:
                return await message.edit("请先私聊一次 @Stickers 机器人")
            except Exception as e:
                await message.edit(f"收藏到贴纸包失败：{e}")
                await sleep(3)
                return await message.delete()
            
            await message.edit(f"收藏到贴纸包 {one_sticker.mention()} 成功")
            await sleep(3)
            return await message.delete()

    # 取消默认贴纸包
    if message.arguments == "cancel":
        if one_sticker.get_custom_sticker_set() is None:
            return await message.edit("还没有设置自定义保存贴纸包")
        one_sticker.del_custom_sticker_set()
        await message.edit("移除自定义保存贴纸包成功")
        await sleep(3)
        return await message.delete()

    # 处理直接保存到指定贴纸包的情况
    if len(message.parameter) == 2 and message.parameter[1] == "save":
        if not message.reply_to_message:
            await message.edit("请回复一个贴纸")
            await sleep(3)
            return await message.delete()
        
        one_sticker.sticker_set = message.parameter[0]
        try:
            await one_sticker.process_sticker()
            await one_sticker.to_sticker_set()
            # 保存贴纸包信息，不影响现有的快捷命名
            one_sticker.save_sticker_set(message.parameter[0], f"@{(await bot.get_me()).username} 的私藏", None)
        except PeerIdInvalid:
            return await message.edit("请先私聊一次 @Stickers 机器人")
        except Exception as e:
            await message.edit(f"收藏到贴纸包失败：{e}")
            await sleep(3)
            return await message.delete()
        
        await message.edit(f"收藏到贴纸包 {one_sticker.mention()} 成功")
        await sleep(3)
        return await message.delete()

    # 设置默认贴纸包
    if len(message.parameter) == 1:
        one_sticker.sticker_set = message.arguments
        try:
            await one_sticker.check_pack_full()
        except NoStickerSetNameError:
            pass
        except Exception as e:
            await message.edit(f"设置自定义贴纸包失败：{e}")
            await sleep(3)
            return await message.delete()
        
        one_sticker.set_custom_sticker_get(message.arguments)
        # 保存贴纸包信息，传入 None 作为 alias 参数，这样不会覆盖现有的快捷命名
        one_sticker.save_sticker_set(message.arguments, f"@{(await bot.get_me()).username} 的私藏", None)
        await message.edit("设置自定义保存贴纸包成功")
        await sleep(3)
        return await message.delete()

    # 删除贴纸包记录
    if message.parameter[0] == "del":
        if len(message.parameter) != 2:
            await message.edit("请使用格式：,s del 贴纸包名")
            await sleep(3)
            return await message.delete()
        
        sticker_name = message.parameter[1]
        if one_sticker.delete_sticker_set(sticker_name):
            # 如果删除的是当前默认贴纸包，也要清除默认设置
            if one_sticker.get_custom_sticker_set() == sticker_name:
                one_sticker.del_custom_sticker_set()
            await message.edit(f"已删除贴纸包 {sticker_name} 的记录")
        else:
            await message.edit(f"贴纸包 {sticker_name} 不存在于记录中")
        await sleep(3)
        return await message.delete()

    # 处理普通的贴纸保存
    if not message.reply_to_message:
        await message.edit("参数错误")
        await sleep(3)
        return await message.delete()
    
    try:
        await one_sticker.process_sticker()
        await one_sticker.to_sticker_set()
    except PeerIdInvalid:
        return await message.edit("请先私聊一次 @Stickers 机器人")
    except Exception as e:
        await message.edit(f"收藏到贴纸包失败：{e}")
        await sleep(3)
        return await message.delete()
    
    await message.edit(f"收藏到贴纸包 {one_sticker.mention()} 成功")
    await sleep(3)
    await message.delete()
