import asyncio
from pathlib import Path
from typing import Dict, Optional

from hummingbot.client.config.config_crypt import PASSWORD_VERIFICATION_PATH, BaseSecretsManager, validate_password
from hummingbot.client.config.config_helpers import (
    ClientConfigAdapter,
    api_keys_from_connector_config_map,
    connector_name_from_file,
    get_connector_config_yml_path,
    list_connector_configs,
    load_connector_config_map_from_file,
    reset_connector_hb_config,
    save_to_yml,
    update_connector_hb_config,
)
from hummingbot.core.utils.async_call_scheduler import AsyncCallScheduler
from hummingbot.core.utils.async_utils import safe_ensure_future


class Security:
    __instance = None
    # 用于管理密码的安全管理器
    secrets_manager: Optional[BaseSecretsManager] = None
    # 用于存储交易所的 secret key 的模型对象，其中键是交易所的名字，值是对应交易所的 KEYS 的 model 对象，
    # 具体的 model 对象，可以到 hummingbot/connector 的子目录下找某个交易所的 xxx_utils.py 文件里的 KEYS 看一下，
    # 这个 KEYS 就是各个交易所自己的 secret key 的配置项模型
    _secure_configs = {}
    # 用于标记解析交易所配置是否完成
    _decryption_done = asyncio.Event()

    @staticmethod
    def new_password_required() -> bool:
        return not PASSWORD_VERIFICATION_PATH.exists()

    @classmethod
    def any_secure_configs(cls):
        return len(cls._secure_configs) > 0

    @staticmethod
    def connector_config_file_exists(connector_name: str) -> bool:
        connector_configs_path = get_connector_config_yml_path(connector_name)
        return connector_configs_path.exists()

    # 判断当前用户的登录状态是否有效，也就是判断密码是否有效
    @classmethod
    def login(cls, secrets_manager: BaseSecretsManager) -> bool:
        if not validate_password(secrets_manager):
            return False
        cls.secrets_manager = secrets_manager
        # 异步运行 decrypt_all ，不会阻塞程序的执行
        coro = AsyncCallScheduler.shared_instance().call_async(cls.decrypt_all, timeout_seconds=30)
        safe_ensure_future(coro)
        return True

    # 用于解析用户本地配置的所有交易所的配置信息，注意，是在用户使用时实际配置的交易所，而不是所有支持的交易所
    @classmethod
    def decrypt_all(cls):
        cls._secure_configs.clear()
        cls._decryption_done.clear()
        # 用户本地配置的交易所配置文件的列表
        encrypted_files = list_connector_configs()
        for file in encrypted_files:
            cls.decrypt_connector_config(file)
        cls._decryption_done.set()

    @classmethod
    def decrypt_connector_config(cls, file_path: Path):
        connector_name = connector_name_from_file(file_path)
        cls._secure_configs[connector_name] = load_connector_config_map_from_file(file_path)

    @classmethod
    def update_secure_config(cls, connector_config: ClientConfigAdapter):
        connector_name = connector_config.connector
        file_path = get_connector_config_yml_path(connector_name)
        save_to_yml(file_path, connector_config)
        update_connector_hb_config(connector_config)
        cls._secure_configs[connector_name] = connector_config

    @classmethod
    def remove_secure_config(cls, connector_name: str):
        file_path = get_connector_config_yml_path(connector_name)
        file_path.unlink(missing_ok=True)
        reset_connector_hb_config(connector_name)
        cls._secure_configs.pop(connector_name)

    @classmethod
    def is_decryption_done(cls):
        return cls._decryption_done.is_set()

    @classmethod
    def decrypted_value(cls, key: str) -> Optional[ClientConfigAdapter]:
        return cls._secure_configs.get(key, None)

    @classmethod
    def all_decrypted_values(cls) -> Dict[str, ClientConfigAdapter]:
        return cls._secure_configs.copy()

    @classmethod
    async def wait_til_decryption_done(cls):
        await cls._decryption_done.wait()

    @classmethod
    def api_keys(cls, connector_name: str) -> Dict[str, Optional[str]]:
        connector_config = cls.decrypted_value(connector_name)
        keys = api_keys_from_connector_config_map(connector_config) if connector_config is not None else {}
        return keys
