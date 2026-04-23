import contextlib
import os
import platform
import tarfile
from pathlib import Path
from asyncio import create_subprocess_exec
from asyncio.subprocess import DEVNULL, PIPE
from json import loads
from PIL import Image
from os.path import exists
from shutil import rmtree
from httpx import ReadTimeout
from solgram.listener import listener
from solgram.enums import Client, Message, AsyncClient
from solgram.single_utils import sqlite
from solgram.utils import lang

PLUGIN_DIR = Path(__file__).resolve().parent
SPEEDTEST_DIR = PLUGIN_DIR / "speedtest-cli"
speedtest_path = SPEEDTEST_DIR / "speedtest"
DEFAULT_SERVER_KEY = "speed_maomi.default-server-id"


def decode_output(data):
    try:
        return str(data.decode().strip())
    except UnicodeDecodeError:
        return str(data.decode("gbk").strip())


def trim_error_detail(detail, limit=200):
    detail = (detail or "").strip()
    if len(detail) <= limit:
        return detail
    return detail[:limit] + "..."


def prepare_runtime_env():
    env = os.environ.copy()
    runtime_home = str(SPEEDTEST_DIR)
    config_dir = str(SPEEDTEST_DIR / ".config")
    cache_dir = str(SPEEDTEST_DIR / ".cache")

    SPEEDTEST_DIR.mkdir(parents=True, exist_ok=True)
    Path(config_dir).mkdir(parents=True, exist_ok=True)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    env["HOME"] = runtime_home
    env["XDG_CONFIG_HOME"] = config_dir
    env["XDG_CACHE_HOME"] = cache_dir
    if not env.get("LANG"):
        env["LANG"] = "C.UTF-8"
    if not env.get("LC_ALL"):
        env["LC_ALL"] = env["LANG"]
    if not env.get("TERM"):
        env["TERM"] = "xterm"
    if not env.get("SHELL"):
        env["SHELL"] = "/bin/sh"
    if not env.get("USER"):
        env["USER"] = "root"
    if not env.get("LOGNAME"):
        env["LOGNAME"] = env["USER"]
    return env


def should_refresh_binary(detail):
    detail = detail or ""
    return any(
        marker in detail
        for marker in (
            "basic_string::_M_construct null not valid",
            "Exec format error",
            "cannot execute binary file",
            "not found",
            "No such file",
        )
    )


def safe_remove(filepath):
    """ Safely removes a file if it exists. """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Error removing file {filepath}: {e}")


def get_default_server_id():
    value = sqlite.get(DEFAULT_SERVER_KEY, "")
    if value is None:
        return ""
    value = str(value).strip()
    return value if value.isdigit() else ""


def save_default_server_id(server_id):
    sqlite[DEFAULT_SERVER_KEY] = str(server_id)


def clear_default_server_id():
    if sqlite.get(DEFAULT_SERVER_KEY, None) is not None:
        del sqlite[DEFAULT_SERVER_KEY]


def find_server_by_id(servers, server_id):
    target_id = str(server_id).strip()
    for server in servers or []:
        if str(server.get("id", "")).strip() == target_id:
            return server
    return None

async def download_cli(request, force=False):
    speedtest_version = "1.2.0"
    machine = str(platform.machine())
    if machine == "AMD64":
        machine = "x86_64"
    filename = (f"ookla-speedtest-{speedtest_version}-linux-{machine}.tgz")
    speedtest_url = (f"https://install.speedtest.net/app/cli/{filename}")
    if force:
        rmtree(SPEEDTEST_DIR, ignore_errors=True)
    env = prepare_runtime_env()
    path = str(SPEEDTEST_DIR) + os.sep

    try:
        data = await request.get(speedtest_url, follow_redirects=True, timeout=30)
        data.raise_for_status()
    except ReadTimeout:
        return "下载测速组件超时，请稍后重试。"
    except Exception as e:
        return f"下载测速组件失败：{e}"

    archive_path = path + filename
    with open(archive_path, mode="wb") as f:
        f.write(data.content)
    try:
        tar = tarfile.open(archive_path, "r:gz")
        file_names = tar.getnames()
        for file_name in file_names:
            tar.extract(file_name, path)
        tar.close()
        safe_remove(archive_path)
        safe_remove(f"{path}speedtest.5")
        safe_remove(f"{path}speedtest.md")
    except Exception as e:
        safe_remove(archive_path)
        return f"解压测速组件失败：{e}"
    proc = await create_subprocess_exec(
        "chmod",
        "+x",
        str(speedtest_path),
        stdout=PIPE,
        stderr=PIPE,
        stdin=DEVNULL,
        env=env,
        cwd=str(SPEEDTEST_DIR),
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0 or not exists(speedtest_path):
        detail = trim_error_detail(decode_output(stderr) or decode_output(stdout))
        return f"测速组件初始化失败：{detail or 'speedtest 不存在'}"
    return None

async def unit_convert(byte):
    """ Converts byte into readable formats. """
    mb_to_byte = 1000000 # 1兆比特=1000000字节
    mbps_to_mbs = ((byte * 8) / mb_to_byte) / 8
    return f"{round(mbps_to_mbs, 2)} MB/s"

async def start_speedtest(arguments):
    """ Executes command and returns output, with the option of enabling stderr. """
    proc = await create_subprocess_exec(
        str(speedtest_path),
        *arguments,
        stdout=PIPE,
        stderr=PIPE,
        stdin=DEVNULL,
        env=prepare_runtime_env(),
        cwd=str(SPEEDTEST_DIR),
    )
    stdout, stderr = await proc.communicate()
    stdout = decode_output(stdout)
    stderr = decode_output(stderr)
    return stdout, stderr, proc.returncode


async def ensure_cli(request, force=False):
    if not force and exists(speedtest_path):
        return None
    return await download_cli(request, force=force)


async def run_speedtest(request: AsyncClient, message: Message, server_id=""):
    setup_error = await ensure_cli(request)
    if setup_error:
        return setup_error, None

    message_args = (message.arguments or "").strip()
    arguments = ["--accept-license", "--accept-gdpr", "-f", "json"]
    selected_server_id = str(server_id).strip()
    if not selected_server_id and message_args.isdigit():
        selected_server_id = message_args
    if not selected_server_id:
        selected_server_id = get_default_server_id()
    if selected_server_id:
        arguments[2:2] = ["-s", selected_server_id]

    outs, errs, code = await start_speedtest(arguments)
    detail = trim_error_detail(errs or outs)
    if code != 0 and should_refresh_binary(detail):
        setup_error = await ensure_cli(request, force=True)
        if setup_error:
            return setup_error, None
        outs, errs, code = await start_speedtest(arguments)
        detail = trim_error_detail(errs or outs)
    if code == 0:
        try:
            result = loads(outs)
        except Exception as e:
            return f"测速结果解析失败：{e}", None
    elif "NoServersException" in detail:
        return "没有找到目标服务器", None
    elif (
        "Cannot retrieve speedtest configuration" in detail
        or "ConfigurationError" in detail
        or "Cannot open socket" in detail
        or "Connection" in detail
    ):
        return f"{lang('speedtest_ConnectFailure')}\n{detail}", None
    elif (
        "No such file" in detail
        or "Permission denied" in detail
        or "not found" in detail
    ):
        return f"测速组件执行失败：{detail}", None
    else:
        return (
            f"测速失败：{detail}" if detail else lang('speedtest_ConnectFailure'),
            None,
        )

    des = (
        f"**Speedtest** \n"
        f"击中点: `{result['server']['name']} \n"
        f"区域: `{result['server']['location']}` \n"
        f"上传: `{await unit_convert(result['upload']['bandwidth'])}` \n"
        f"下载: `{await unit_convert(result['download']['bandwidth'])}` \n"
        f" 你们看到我的小猫咪了吗？！！！ \n"
    )

    if result["result"]["url"]:
        data = await request.get(
            result["result"]["url"] + ".png", follow_redirects=True, timeout=30
        )
        with open("speedtest.png", mode="wb") as f:
            f.write(data.content)
        with contextlib.suppress(Exception):
            img = Image.open("speedtest.png")
            c = img.crop((17, 11, 727, 389))
            c.save("speedtest.png")
    return des, "speedtest.png" if exists("speedtest.png") else None

async def get_speedtest_servers(request):
    """ Get speedtest_server. """
    setup_error = await ensure_cli(request)
    if setup_error:
        return setup_error, None
    outs, errs, code = await start_speedtest(["-f", "json", "-L"])
    if code != 0:
        detail = trim_error_detail(errs or outs)
        if should_refresh_binary(detail):
            setup_error = await ensure_cli(request, force=True)
            if setup_error:
                return setup_error, None
            outs, errs, code = await start_speedtest(["-f", "json", "-L"])
            detail = trim_error_detail(errs or outs)
    if code != 0:
        return (
            f"{lang('speedtest_ConnectFailure')}\n{detail}"
            if detail
            else lang("speedtest_ConnectFailure"),
            None,
        )
    try:
        result = loads(outs)
    except Exception as e:
        return f"测速节点解析失败：{e}", None
    servers = result.get("servers", []) if isinstance(result, dict) else []
    return None, servers if isinstance(servers, list) else []


async def get_all_ids(request):
    error, servers = await get_speedtest_servers(request)
    if error:
        return error, None
    if not servers:
        return "附近没有测速节点", None
    lines = ["附近测速节点："]
    default_server_id = get_default_server_id()
    if default_server_id:
        default_server = find_server_by_id(servers, default_server_id)
        if default_server:
            lines.append(
                f"当前默认测速节点：`{default_server_id}` - "
                f"`{default_server.get('name', '未知节点')}` - "
                f"`{default_server.get('location', '未知区域')}`"
            )
        else:
            lines.append(f"当前默认测速节点：`{default_server_id}`")
    lines.append("使用 `sv set <id>` 设置默认测速点，使用 `sv set clear` 清除。")
    lines.append("")
    lines.extend(
        f"`{i['id']}` - `{i['name']}` - `{i['location']}`"
        for i in servers
    )
    return "\n".join(lines), None


async def set_default_speedtest_server(request, server_id):
    error, servers = await get_speedtest_servers(request)
    if error:
        return error
    server = find_server_by_id(servers, server_id)
    if not server:
        return "没有找到这个测速节点，请先使用 `sv list` 查看可用节点。"
    save_default_server_id(server_id)
    return (
        f"已将默认测速节点设置为 `{server_id}` - "
        f"`{server.get('name', '未知节点')}` - "
        f"`{server.get('location', '未知区域')}`"
    )

@listener(command="sv",
          need_admin=True,
          description=lang('speedtest_des'),
          parameters="[list|<server id>|set <server id>|set clear]")
async def speedtest(client: Client, message: Message, request: AsyncClient):
    """ Tests internet speed using speedtest. """
    msg = message
    message_args = (message.arguments or "").strip()
    args = message_args.split()
    lowered_args = message_args.lower()

    if lowered_args == "list":
        des, photo = await get_all_ids(request)
    elif args and args[0].lower() == "set":
        if len(args) == 1:
            default_server_id = get_default_server_id()
            if default_server_id:
                des = (
                    f"当前默认测速节点：`{default_server_id}`\n"
                    "使用 `sv set clear` 清除，或使用 `sv set <id>` 重新设置。"
                )
            else:
                des = "当前没有默认测速节点，请先使用 `sv list` 查看节点。"
            photo = None
        elif len(args) == 2 and args[1].lower() == "clear":
            clear_default_server_id()
            des = "已清除默认测速节点，下次 `sv` 将继续由 Speedtest 自动选点。"
            photo = None
        elif len(args) == 2 and args[1].isdigit():
            des = await set_default_speedtest_server(request, args[1])
            photo = None
        else:
            return await msg.edit(lang('arg_error'))
    elif len(message_args) == 0 or message_args.isdigit():
        selected_server_id = message_args if message_args.isdigit() else get_default_server_id()
        status_text = "猫咪努力的挣脱毛线球，开始汇聚元气..."
        if selected_server_id:
            status_text += f"\n目标节点：`{selected_server_id}`"
        msg: Message = await message.edit(status_text)
        des, photo = await run_speedtest(request, message, selected_server_id)
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
