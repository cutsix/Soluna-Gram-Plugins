import contextlib
import platform
import tarfile
import os
from pathlib import Path
from asyncio import create_subprocess_shell
from asyncio.subprocess import PIPE
from json import loads
from PIL import Image
from os import makedirs
from os.path import exists
from httpx import ReadTimeout
from solgram.listener import listener
from solgram.enums import Client, Message, AsyncClient
from solgram.utils import lang

PLUGIN_DIR = Path(__file__).resolve().parent
SPEEDTEST_DIR = PLUGIN_DIR / "speedtest-cli"
speedtest_path = SPEEDTEST_DIR / "speedtest"

def safe_remove(filepath):
    """ Safely removes a file if it exists. """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Error removing file {filepath}: {e}")

async def download_cli(request):
    speedtest_version = "1.2.0"
    machine = str(platform.machine())
    if machine == "AMD64":
        machine = "x86_64"
    filename = (f"ookla-speedtest-{speedtest_version}-linux-{machine}.tgz")
    speedtest_url = (f"https://install.speedtest.net/app/cli/{filename}")
    path = str(SPEEDTEST_DIR) + os.sep
    if not exists(path):
        makedirs(path)
    data = await request.get(speedtest_url)
    with open(path+filename, mode="wb") as f:
        f.write(data.content)
    try:
        tar = tarfile.open(path+filename, "r:gz")
        file_names = tar.getnames()
        for file_name in file_names:
            tar.extract(file_name, path)
        tar.close()
        safe_remove(path+filename)
        safe_remove(f"{path}speedtest.5")
        safe_remove(f"{path}speedtest.md")
    except Exception:
        return "下载或解压缩失败，下次请努力吧", None
    proc = await create_subprocess_shell(
        f"chmod +x '{speedtest_path}'",
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
        stdin=PIPE,
    )
    stdout, stderr = await proc.communicate()
    return path if exists(speedtest_path) else None

async def unit_convert(byte):
    """ Converts byte into readable formats. """
    mb_to_byte = 1000000 # 1兆比特=1000000字节
    mbps_to_mbs = ((byte * 8) / mb_to_byte) / 8
    return f"{round(mbps_to_mbs, 2)} MB/s"

async def start_speedtest(command):
    """ Executes command and returns output, with the option of enabling stderr. """
    proc = await create_subprocess_shell(command, shell=True, stdout=PIPE, stderr=PIPE, stdin=PIPE)
    stdout, stderr = await proc.communicate()
    try:
        stdout = str(stdout.decode().strip())
        stderr = str(stderr.decode().strip())
    except UnicodeDecodeError:
        stdout = str(stdout.decode('gbk').strip())
        stderr = str(stderr.decode('gbk').strip())
    return stdout, stderr, proc.returncode

async def run_speedtest(request: AsyncClient, message: Message):
    if not exists(speedtest_path):
        await download_cli(request)

    command = (
        f"'{speedtest_path}' --accept-license --accept-gdpr -s {message.arguments} -f json"
        if str.isdigit(message.arguments)
        else f"'{speedtest_path}' --accept-license --accept-gdpr -f json"
    )

    outs, errs, code = await start_speedtest(command)
    if code == 0:
        result = loads(outs)
    elif "NoServersException" in errs:
        return "没有找到目标服务器", None
    else:
        return lang('speedtest_ConnectFailure'), None

    des = (
        f"**Speedtest** \n"
        f"击中点: `{result['server']['name']} \n"
        f"区域: `{result['server']['location']}` \n"
        f"上传: `{await unit_convert(result['upload']['bandwidth'])}` \n"
        f"下载: `{await unit_convert(result['download']['bandwidth'])}` \n"
        f" 你们看到我的小猫咪了吗？！！！ \n"
    )

    if result["result"]["url"]:
        data = await request.get(result["result"]["url"]+'.png')
        with open("speedtest.png", mode="wb") as f:
            f.write(data.content)
        with contextlib.suppress(Exception):
            img = Image.open("speedtest.png")
            c = img.crop((17, 11, 727, 389))
            c.save("speedtest.png")
    return des, "speedtest.png" if exists("speedtest.png") else None

async def get_all_ids(request):
    """ Get speedtest_server. """
    if not exists(speedtest_path):
        await download_cli(request)
    outs, errs, code = await start_speedtest(f"'{speedtest_path}' -f json -L")
    result = loads(outs) if code == 0 else None
    return (
        (
            "附近测速节点：\n"
            + "\n".join(
                f"`{i['id']}` - `{i['name']}` - `{i['location']}`"
                for i in result['servers']
            ),
            None,
        )
        if result
        else ("附近没有测速节点", None)
    )

@listener(command="sv",
          need_admin=True,
          description=lang('speedtest_des'),
          parameters="(list/server id)")
async def speedtest(client: Client, message: Message, request: AsyncClient):
    """ Tests internet speed using speedtest. """
    msg = message
    if message.arguments == "list":
        des, photo = await get_all_ids(request)
    elif len(message.arguments) == 0 or str.isdigit(message.arguments):
        msg: Message = await message.edit("猫咪努力的挣脱毛线球，开始汇聚元气...")
        des, photo = await run_speedtest(request, message)
    else:
        return await msg.edit(lang('arg_error'))
    if not photo:
        return await msg.edit(des)
    try:
        if message.reply_to_message:
            await message.reply_to_message.reply_photo(photo, caption=des)
        else:
            await message.reply_photo(photo, caption=des, quote=False, reply_to_message_id=message.reply_to_top_message_id)
        await message.safe_delete()
    except Exception:
        return await msg.edit(des)
    safe_remove(photo)
