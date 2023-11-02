#!/usr/bin/env python

import argparse
import asyncio
import grp
import logging
import os
import pwd
import subprocess
from pathlib import Path
from typing import Coroutine, List

import path_util  # noqa: F401

from bin.hummingbot import UIStartListener, detect_available_port
from hummingbot import init_logging
from hummingbot.client.config.config_crypt import BaseSecretsManager, ETHKeyFileSecretManger
from hummingbot.client.config.config_helpers import (
    ClientConfigAdapter,
    all_configs_complete,
    create_yml_files_legacy,
    load_client_config_map_from_file,
    load_strategy_config_map_from_file,
    read_system_configs_from_yml,
)
from hummingbot.client.config.security import Security
from hummingbot.client.hummingbot_application import HummingbotApplication
from hummingbot.client.settings import STRATEGIES_CONF_DIR_PATH, AllConnectorSettings
from hummingbot.client.ui import login_prompt
from hummingbot.client.ui.style import load_style
from hummingbot.core.event.events import HummingbotUIEvent
from hummingbot.core.management.console import start_management_console
from hummingbot.core.utils.async_utils import safe_gather


class CmdlineParser(argparse.ArgumentParser):
    def __init__(self):
        super().__init__()
        self.add_argument(
            "--config-file-name",
            "-f",
            type=str,
            required=False,
            help="Specify a file in `conf/` to load as the strategy config file.",
        )
        self.add_argument(
            "--config-password",
            "-p",
            type=str,
            required=False,
            help="Specify the password to unlock your encrypted files.",
        )
        self.add_argument(
            "--auto-set-permissions",
            type=str,
            required=False,
            help="Try to automatically set config / logs / data dir permissions, " "useful for Docker containers.",
        )


# 自动为项目下的一些文件和文件夹修改文件所属的用户为 user_group_spec 所执行的用户
def autofix_permissions(user_group_spec: str):
    uid, gid = [sub_str for sub_str in user_group_spec.split(":")]

    # pwd.getpwnam 方法的作用是根据用户名查找并返回与该用户名关联的用户信息（Unix 用户账户信息）
    # pw_uid：用户UID（唯一标识用户的数字）
    uid = int(uid) if uid.isnumeric() else pwd.getpwnam(uid).pw_uid
    # grp.getgrnam 方法的作用是根据组名查找并返回与该组名关联的组信息（Unix 用户组信息）
    # gr_gid：组的GID（唯一标识组的数字）
    gid = int(gid) if gid.isnumeric() else grp.getgrnam(gid).gr_gid

    # pwd.getpwuid 方法的作用是根据用户标识符（UID）查找并返回与该UID关联的用户信息（Unix 用户账户信息），
    # 注意：pwd.getpwuid 和 pwd.getpwnam 方法都是用来获取用户账户信息的，只不过 pwd.getpwuid 的入参是 uid ，而 pwd.getpwnam 的入参是 username
    # pw_dir：用户的主目录路径
    # $HOME ：用户主目录
    os.environ["HOME"] = pwd.getpwuid(uid).pw_dir
    # os.path.realpath() 获取绝对路径，所以这里是获取根目录的绝对路径
    project_home: str = os.path.realpath(os.path.join(__file__, "../../"))

    """
    1. Path.home() 是一个方法，用于获取当前用户的主目录路径。这通常是用户的个人文件和配置存储的位置。
    2. .joinpath(".hummingbot-gateway") 是使用 Path 对象的方法，用于将当前用户的主目录路径与一个相对路径（这里是 ".hummingbot-gateway"）连接起来，以创建一个新的 Path 对象。
    3. .as_posix() 方法用于将 Path 对象转换为字符串形式，以确保 gateway_path 是一个字符串而不是 Path 对象。
    """
    gateway_path: str = Path.home().joinpath(".hummingbot-gateway").as_posix()
    subprocess.run(
        f"cd '{project_home}' && " f"sudo chown -R {user_group_spec} conf/ data/ logs/ scripts/ {gateway_path}",
        capture_output=True,
        shell=True,
    )
    # os.setgid(gid) 和 os.setuid(uid) 是用于改变进当前程的用户组ID（GID）和用户ID（UID）的系统调用
    os.setgid(gid)
    os.setuid(uid)


async def quick_start(args: argparse.Namespace, secrets_manager: BaseSecretsManager):
    config_file_name = args.config_file_name
    # 加载 conf/conf_client.yml 配置文件
    client_config_map = load_client_config_map_from_file()

    if args.auto_set_permissions is not None:
        autofix_permissions(args.auto_set_permissions)

    if not Security.login(secrets_manager):
        logging.getLogger().error("Invalid password.")
        return

    # 等待所有本地的交易所 secret key 配置都解析完成
    await Security.wait_til_decryption_done()
    await create_yml_files_legacy()
    # 初始化日志配置文件
    init_logging("hummingbot_logs.yml", client_config_map)
    # 读取费用信息的配置文件 conf_fee_overrides.yml
    await read_system_configs_from_yml()

    # 初始化本地测试交易所，这种交易所会在本地模拟买入、卖出、获取余额等操作，便于测试
    AllConnectorSettings.initialize_paper_trade_settings(client_config_map.paper_trade.paper_trade_exchanges)

    hb = HummingbotApplication.main_application(client_config_map=client_config_map)
    # Todo: validate strategy and config_file_name before assinging

    # 老版本的策略配置文件解析得到的策略
    strategy_config = None
    # 是否是新版本的 script
    is_script = False
    if config_file_name is not None:
        # 要特别关注这个赋值操作，可以看一下 HummingbotApplication 的 strategy_file_name 赋值处理函数
        hb.strategy_file_name = config_file_name
        # 如果以 .py 结尾，则是 script
        if config_file_name.split(".")[-1] == "py":
            hb.strategy_name = hb.strategy_file_name
            is_script = True
        else:  # 否则是老版本的策略
            # 解析策略配置
            strategy_config = await load_strategy_config_map_from_file(STRATEGIES_CONF_DIR_PATH / config_file_name)
            hb.strategy_name = (
                strategy_config.strategy
                if isinstance(strategy_config, ClientConfigAdapter)
                else strategy_config.get("strategy").value
            )
            hb.strategy_config_map = strategy_config

    if strategy_config is not None:
        if not all_configs_complete(strategy_config, hb.client_config_map):
            hb.status()

    # The listener needs to have a named variable for keeping reference, since the event listener system
    # uses weak references to remove unneeded listeners.
    start_listener: UIStartListener = UIStartListener(hb, is_script=is_script, is_quickstart=True)
    # 监听 start 事件
    hb.app.add_listener(HummingbotUIEvent.Start, start_listener)

    tasks: List[Coroutine] = [hb.run()]
    if client_config_map.debug_console:
        management_port: int = detect_available_port(8211)
        tasks.append(start_management_console(locals(), host="localhost", port=management_port))

    await safe_gather(*tasks)


def main():
    args = CmdlineParser().parse_args()

    # Parse environment variables from Dockerfile.
    # If an environment variable is not empty and it's not defined in the arguments, then we'll use the environment
    # variable.
    if args.config_file_name is None and len(os.environ.get("CONFIG_FILE_NAME", "")) > 0:
        args.config_file_name = os.environ["CONFIG_FILE_NAME"]
    if args.config_password is None and len(os.environ.get("CONFIG_PASSWORD", "")) > 0:
        args.config_password = os.environ["CONFIG_PASSWORD"]

    # If no password is given from the command line, prompt for one.
    # 加解密密码的类
    secrets_manager_cls = ETHKeyFileSecretManger
    client_config_map = load_client_config_map_from_file()

    # 如果在命令行运行命令时没有设置密码，则需要让用户提供
    if args.config_password is None:
        secrets_manager = login_prompt(secrets_manager_cls, style=load_style(client_config_map))
        if not secrets_manager:
            return
    else:
        secrets_manager = secrets_manager_cls(args.config_password)

    try:
        ev_loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    except Exception:
        ev_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        asyncio.set_event_loop(ev_loop)

    ev_loop.run_until_complete(quick_start(args, secrets_manager))


if __name__ == "__main__":
    main()
