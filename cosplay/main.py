import io
import random
import tempfile
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin, urlparse

from pyrogram.types import InputMediaPhoto

from solgram.listener import listener
from solgram.enums import Message, Client
from solgram.services import client as http_client
from solgram.single_utils import safe_remove
from solgram.utils import pip_install

pip_install("beautifulsoup4")
pip_install("pillow")

from bs4 import BeautifulSoup
from PIL import Image

BASE_URL = "https://cosplaytele.com/"
MAX_PAGES = 455
MAX_IMAGES = 10
DEFAULT_IMAGES = 1
REQUEST_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
SUPPORTED_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def _reply_to_id(message: Message):
    return message.reply_to_message_id or message.reply_to_top_message_id


def _parse_count(message: Message) -> int:
    if not message.parameter:
        return DEFAULT_IMAGES
    try:
        count = int(message.parameter[0])
    except (TypeError, ValueError):
        return DEFAULT_IMAGES
    return max(1, min(count, MAX_IMAGES))


async def _fetch_text(url: str) -> str:
    response = await http_client.get(
        url,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


async def _fetch_bytes(url: str) -> bytes:
    response = await http_client.get(
        url,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.content


def _to_jpeg_bytes(raw: bytes) -> bytes:
    image = Image.open(io.BytesIO(raw))
    if image.mode not in ("RGB", "L"):
        if "A" in image.getbands():
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
    elif image.mode == "L":
        image = image.convert("RGB")

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92)
    return output.getvalue()


def _extract_post_links(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    base_domain = urlparse(BASE_URL).netloc
    for tag in soup.select("a[href]"):
        href = tag.get("href")
        if not href:
            continue
        normalized = urljoin(BASE_URL, href)
        parsed = urlparse(normalized)
        if parsed.netloc != base_domain:
            continue
        if normalized.rstrip("/") == BASE_URL.rstrip("/"):
            continue
        if any(part in normalized for part in (
            "/page/",
            "/category/",
            "/24-hours/",
            "/3-day/",
            "/7-day/",
            "/explore-categories/",
            "/best-cosplayer/",
        )):
            continue
        links.add(normalized)
    return list(links)


def _extract_gallery_images(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    images = []
    for tag in soup.select("figure.gallery-item img"):
        src = tag.get("src") or tag.get("data-src")
        if not src:
            continue
        normalized = urljoin(BASE_URL, src)
        path = urlparse(normalized).path.lower()
        if path.endswith(SUPPORTED_SUFFIXES):
            images.append(normalized)
    return images


async def _get_random_photo_set() -> Tuple[str, str]:
    random_page = random.randint(1, MAX_PAGES)
    page_url = BASE_URL if random_page == 1 else f"{BASE_URL}page/{random_page}/"
    html = await _fetch_text(page_url)
    links = _extract_post_links(html)
    if not links:
        raise RuntimeError(f"第 {random_page} 页没有找到可用套图")
    selected = random.choice(links)
    title = selected.rstrip("/").split("/")[-1].replace("-", " ") or "未知套图"
    return selected, title


async def _pick_random_images(count: int) -> Tuple[str, str, List[str]]:
    last_error = None
    for _ in range(8):
        try:
            photo_set_url, title = await _get_random_photo_set()
            html = await _fetch_text(photo_set_url)
            images = _extract_gallery_images(html)
            if not images:
                continue
            if len(images) < count:
                continue
            selected = random.sample(images, count) if len(images) > count else images
            return photo_set_url, title, selected
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"获取套图失败: {last_error or '未知错误'}")


async def _download_images(image_urls: List[str]) -> List[str]:
    files = []
    for image_url in image_urls:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_path = temp.name
        temp.close()
        try:
            image_bytes = await _fetch_bytes(image_url)
            Path(temp_path).write_bytes(_to_jpeg_bytes(image_bytes))
            files.append(temp_path)
        except Exception:
            safe_remove(temp_path)
            raise
    return files


async def _send_images(
    client: Client,
    message: Message,
    file_paths: List[str],
    photo_set_url: str,
) -> None:
    reply_to = _reply_to_id(message)

    async def _send_one_by_one() -> None:
        for index, file_path in enumerate(file_paths):
            await client.send_photo(
                message.chat.id,
                file_path,
                # caption=f"套图链接: {photo_set_url}" if index == 0 else "",
                caption=f"你喜欢这个吗？" if index == 0 else "",
                has_spoiler=True,
                reply_to_message_id=reply_to if index == 0 else None,
            )

    if len(file_paths) == 1:
        await _send_one_by_one()
        return

    media = []
    for index, file_path in enumerate(file_paths):
        media.append(
            InputMediaPhoto(
                file_path,
                caption=f"你喜欢这个吗？" if index == 0 else "",
                has_spoiler=True,
            )
        )
    try:
        await client.send_media_group(
            message.chat.id,
            media,
            reply_to_message_id=reply_to,
        )
    except Exception:
        await _send_one_by_one()


async def _run_cosplay(client: Client, message: Message) -> None:
    count = _parse_count(message)
    files = []
    try:
        await message.edit(f"正在探索...")
        photo_set_url, title, image_urls = await _pick_random_images(count)
        await message.edit(f'已命中，正在传输')
        files = await _download_images(image_urls)
        # await message.edit("下载完成，正在发送...")
        await _send_images(client, message, files, photo_set_url)
        await message.safe_delete()
    except Exception as exc:
        await message.edit(f"❌ 获取 cosplay 图片失败: {exc}")
    finally:
        for file_path in files:
            safe_remove(file_path)


@listener(
    command="cosplay",
    description="随机获取 cosplay 套图图片",
    parameters="[数量，默认 1，最大 10]",
)
async def cosplay_command(client: Client, message: Message):
    await _run_cosplay(client, message)


@listener(
    command="cos",
    description="随机获取 cosplay 套图图片",
    parameters="[数量，默认 1，最大 10]",
)
async def cos_command(client: Client, message: Message):
    await _run_cosplay(client, message)
