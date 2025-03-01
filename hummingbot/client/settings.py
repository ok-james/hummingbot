import importlib
import json
from decimal import Decimal
from enum import Enum
from os import DirEntry, scandir
from os.path import exists, join, realpath
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional, Set, Union, cast

from pydantic import SecretStr

from hummingbot import get_strategy_list, root_path
from hummingbot.core.data_type.trade_fee import TradeFeeSchema
from hummingbot.core.utils.gateway_config_utils import SUPPORTED_CHAINS

if TYPE_CHECKING:
    from hummingbot.client.config.config_data_types import BaseConnectorConfigMap
    from hummingbot.client.config.config_helpers import ClientConfigAdapter
    from hummingbot.connector.connector_base import ConnectorBase
    from hummingbot.connector.gateway.clob_spot.data_sources.clob_api_data_source_base import CLOBAPIDataSourceBase


# Global variables
required_exchanges: Set[str] = set()
requried_connector_trading_pairs: Dict[str, List[str]] = {}
# Set these two variables if a strategy uses oracle for rate conversion
required_rate_oracle: bool = False
rate_oracle_pairs: List[str] = []

# Global static values
KEYFILE_PREFIX = "key_file_"
KEYFILE_POSTFIX = ".yml"
ENCYPTED_CONF_POSTFIX = ".json"
DEFAULT_LOG_FILE_PATH = root_path() / "logs"
DEFAULT_ETHEREUM_RPC_URL = "https://mainnet.coinalpha.com/hummingbot-test-node"
TEMPLATE_PATH = root_path() / "hummingbot" / "templates"
CONF_DIR_PATH = root_path() / "conf"
CLIENT_CONFIG_PATH = CONF_DIR_PATH / "conf_client.yml"
TRADE_FEES_CONFIG_PATH = CONF_DIR_PATH / "conf_fee_overrides.yml"
STRATEGIES_CONF_DIR_PATH = CONF_DIR_PATH / "strategies"
# 用户本地配置的交易所的配置文件的目录
CONNECTORS_CONF_DIR_PATH = CONF_DIR_PATH / "connectors"
CONF_PREFIX = "conf_"
CONF_POSTFIX = "_strategy"
PMM_SCRIPTS_PATH = root_path() / "pmm_scripts"
SCRIPT_STRATEGIES_MODULE = "scripts"
SCRIPT_STRATEGIES_PATH = root_path() / SCRIPT_STRATEGIES_MODULE
DEFAULT_GATEWAY_CERTS_PATH = root_path() / "certs"

GATEWAY_SSL_CONF_FILE = root_path() / "gateway" / "conf" / "ssl.yml"

# Certificates for securely communicating with the gateway api
GATEAWAY_CA_CERT_PATH = DEFAULT_GATEWAY_CERTS_PATH / "ca_cert.pem"
GATEAWAY_CLIENT_CERT_PATH = DEFAULT_GATEWAY_CERTS_PATH / "client_cert.pem"
GATEAWAY_CLIENT_KEY_PATH = DEFAULT_GATEWAY_CERTS_PATH / "client_key.pem"

PAPER_TRADE_EXCHANGES = [  # todo: fix after global config map refactor
    "binance_paper_trade",
    "kucoin_paper_trade",
    "ascend_ex_paper_trade",
    "gate_io_paper_trade",
    "mock_paper_exchange",
]

CONNECTOR_SUBMODULES_THAT_ARE_NOT_CEX_TYPES = ["test_support", "utilities", "gateway"]


class ConnectorType(Enum):
    """
    The types of exchanges that hummingbot client can communicate with.
    """

    # Todo 不同交易所类型之间有什么区别
    AMM = "AMM"
    AMM_LP = "AMM_LP"
    AMM_Perpetual = "AMM_Perpetual"
    CLOB_SPOT = "CLOB_SPOT"
    CLOB_PERP = "CLOB_PERP"
    Connector = "connector"
    Exchange = "exchange"
    Derivative = "derivative"


class GatewayConnectionSetting:
    @staticmethod
    def conf_path() -> str:
        return realpath(join(CONF_DIR_PATH, "gateway_connections.json"))

    @staticmethod
    def load() -> List[Dict[str, str]]:
        connections_conf_path: str = GatewayConnectionSetting.conf_path()
        if exists(connections_conf_path):
            with open(connections_conf_path) as fd:
                return json.load(fd)
        return []

    @staticmethod
    def save(settings: List[Dict[str, str]]):
        connections_conf_path: str = GatewayConnectionSetting.conf_path()
        with open(connections_conf_path, "w") as fd:
            json.dump(settings, fd)

    @staticmethod
    def get_market_name_from_connector_spec(connector_spec: Dict[str, str]) -> str:
        return f"{connector_spec['connector']}_{connector_spec['chain']}_{connector_spec['network']}"

    @staticmethod
    def get_connector_spec(connector_name: str, chain: str, network: str) -> Optional[Dict[str, str]]:
        connector: Optional[Dict[str, str]] = None
        connector_config: List[Dict[str, str]] = GatewayConnectionSetting.load()
        for spec in connector_config:
            if spec["connector"] == connector_name and spec["chain"] == chain and spec["network"] == network:
                connector = spec

        return connector

    @staticmethod
    def get_connector_spec_from_market_name(market_name: str) -> Optional[Dict[str, str]]:
        for chain in SUPPORTED_CHAINS:
            if chain in market_name:
                connector, network = market_name.split(f"_{chain}_")
                return GatewayConnectionSetting.get_connector_spec(connector, chain, network)
        return None

    @staticmethod
    def upsert_connector_spec(
        connector_name: str,
        chain: str,
        network: str,
        trading_type: str,
        chain_type: str,
        wallet_address: str,
        additional_spenders: List[str],
        additional_prompt_values: Dict[str, str],
    ):
        new_connector_spec: Dict[str, str] = {
            "connector": connector_name,
            "chain": chain,
            "network": network,
            "trading_type": trading_type,
            "chain_type": chain_type,
            "wallet_address": wallet_address,
            "additional_spenders": additional_spenders,
            "additional_prompt_values": additional_prompt_values,
        }
        updated: bool = False
        connectors_conf: List[Dict[str, str]] = GatewayConnectionSetting.load()
        for i, c in enumerate(connectors_conf):
            if c["connector"] == connector_name and c["chain"] == chain and c["network"] == network:
                connectors_conf[i] = new_connector_spec
                updated = True
                break

        if updated is False:
            connectors_conf.append(new_connector_spec)
        GatewayConnectionSetting.save(connectors_conf)

    @staticmethod
    def upsert_connector_spec_tokens(connector_chain_network: str, tokens: List[str]):
        updated_connector: Optional[Dict[str, Any]] = GatewayConnectionSetting.get_connector_spec_from_market_name(
            connector_chain_network
        )
        updated_connector["tokens"] = tokens

        connectors_conf: List[Dict[str, str]] = GatewayConnectionSetting.load()
        for i, c in enumerate(connectors_conf):
            if (
                c["connector"] == updated_connector["connector"]
                and c["chain"] == updated_connector["chain"]
                and c["network"] == updated_connector["network"]
            ):
                connectors_conf[i] = updated_connector
                break

        GatewayConnectionSetting.save(connectors_conf)


class ConnectorSetting(NamedTuple):
    # 交易所的名字
    name: str
    # 交易所的类型
    type: ConnectorType
    # Todo 估计是实例的交易对，但是具体作用是什么，有待研究
    example_pair: str
    # Todo 作用有待研究，猜测：是否是中心化交易所
    centralised: bool
    # Todo 作用有待研究
    use_ethereum_wallet: bool
    # 费率信息
    trade_fee_schema: TradeFeeSchema
    # 交易所 secret key 的配置信息
    config_keys: Optional["BaseConnectorConfigMap"]
    # 是否是通过 OTHER_DOMAINS 生成的交易所设置，如果是，则为 True ，反之为 False
    is_sub_domain: bool
    """
    父交易所，一般有两种情况会设置父交易所：
    1. 在交易所代码的 xxx_utils.py 里配置了 OTHER_DOMAINS 的话，会在生成 OTHER_DOMAINS 内的交易所设置时设置父交易所，可以看一下 binance 交易所代码中的相关配置
    2. paper 交易所，会设置父交易所
    说白了，配置父交易所，就是要用父交易所的一些设置，比如获取交易所的交易对时，就可以直接用父交易所的能力
    """
    parent_name: Optional[str]
    # Todo 通过 OTHER_DOMAINS_PARAMETER 中的配置得到的，会作为实例化交易所实例的 domain 入参，但是这个 domain 入参在交易所实例中的作用未知
    domain_parameter: Optional[str]
    # Todo 作用有待研究
    use_eth_gas_lookup: bool
    """
    This class has metadata data about Exchange connections. The name of the connection and the file path location of
    the connector file.
    """

    def uses_gateway_generic_connector(self) -> bool:
        non_gateway_connectors_types = [ConnectorType.Exchange, ConnectorType.Derivative, ConnectorType.Connector]
        return self.type not in non_gateway_connectors_types

    def uses_clob_connector(self) -> bool:
        return self.type in [ConnectorType.CLOB_SPOT, ConnectorType.CLOB_PERP]

    def module_name(self) -> str:
        # returns connector module name, e.g. binance_exchange
        if self.uses_gateway_generic_connector():
            if "AMM" in self.type.name:
                # AMMs currently have multiple generic connectors. chain_type is used to determine the right connector to use.
                connector_spec: Dict[str, str] = GatewayConnectionSetting.get_connector_spec_from_market_name(self.name)
                return f"gateway.{self.type.name.lower()}.gateway_{connector_spec['chain_type'].lower()}_{self._get_module_package()}"
            elif "CLOB" in self.type.name:
                return f"gateway.{self.type.name.lower()}.gateway_{self._get_module_package()}"
            else:
                raise ValueError(f"Unsupported connector type: {self.type}")
        return f"{self.base_name()}_{self._get_module_package()}"

    # 获取交易所模块的完整路径
    def module_path(self) -> str:
        # return connector full path name, e.g. hummingbot.connector.exchange.binance.binance_exchange
        # Todo 去中心化交易所应该会返回这个路径，去中心化交易所难道都是通过 gateway 来访问的吗？ gateway 到底是做什么的？
        if self.uses_gateway_generic_connector():
            return f"hummingbot.connector.{self.module_name()}"
        # 中心化交易所会返回这个路径
        return f"hummingbot.connector.{self._get_module_package()}.{self.base_name()}.{self.module_name()}"

    # 获取交易所模块中导出的类
    def class_name(self) -> str:
        # return connector class name, e.g. BinanceExchange
        if self.uses_gateway_generic_connector():
            file_name = self.module_name().split(".")[-1]
            splited_name = file_name.split("_")
            for i in range(len(splited_name)):
                if splited_name[i] in ["evm", "amm", "clob", "lp", "sol", "spot"]:
                    splited_name[i] = splited_name[i].upper()
                else:
                    splited_name[i] = splited_name[i].capitalize()
            return "".join(splited_name)
        return "".join([o.capitalize() for o in self.module_name().split("_")])

    def get_api_data_source_module_name(self) -> str:
        module_name = ""
        if self.uses_clob_connector():
            if self.type == ConnectorType.CLOB_PERP:
                module_name = f"{self.name.rsplit(sep='_', maxsplit=2)[0]}_api_data_source"
            else:
                module_name = f"{self.name.split('_')[0]}_api_data_source"
        return module_name

    def get_api_data_source_class_name(self) -> str:
        class_name = ""
        if self.uses_clob_connector():
            if self.type == ConnectorType.CLOB_PERP:
                class_name = f"{self.name.split('_')[0].capitalize()}PerpetualAPIDataSource"
            else:
                class_name = f"{self.name.split('_')[0].capitalize()}APIDataSource"
        return class_name

    # 生成初始化交易所实例的入参
    def conn_init_parameters(
        self,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = False,
        api_keys: Optional[Dict[str, Any]] = None,
        client_config_map: Optional["ClientConfigAdapter"] = None,
    ) -> Dict[str, Any]:
        trading_pairs = trading_pairs or []
        api_keys = api_keys or {}
        if self.uses_gateway_generic_connector():  # init parameters for gateway connectors
            params = {}
            if self.config_keys is not None:
                params: Dict[str, Any] = {k: v.value for k, v in self.config_keys.items()}
            connector_spec: Dict[str, str] = GatewayConnectionSetting.get_connector_spec_from_market_name(self.name)
            params.update(
                connector_name=connector_spec["connector"],
                chain=connector_spec["chain"],
                network=connector_spec["network"],
                address=connector_spec["wallet_address"],
            )

            # 如果是 AMM 类
            if not self.uses_clob_connector():
                params["additional_spenders"] = connector_spec.get("additional_spenders", [])
            # 如果是 CLOB 类
            if self.uses_clob_connector():
                params["api_data_source"] = self._load_clob_api_data_source(
                    trading_pairs=trading_pairs,
                    trading_required=trading_required,
                    client_config_map=client_config_map,
                    connector_spec=connector_spec,
                )
        elif not self.is_sub_domain:
            # 如果不是子域名，则是 普通交易所或者paper ， paper 会使用与父交易所相同的 api_keys 
            params = api_keys
        else:
            # 是子域名，需要将 api_keys 中的子域名的名字替换为父交易所的名字
            params: Dict[str, Any] = {k.replace(self.name, self.parent_name): v for k, v in api_keys.items()}
            params["domain"] = self.domain_parameter

        params["trading_pairs"] = trading_pairs
        params["trading_required"] = trading_required
        params["client_config_map"] = client_config_map
        if (
            self.config_keys is not None
            and type(self.config_keys) is not dict
            and "receive_connector_configuration" in self.config_keys.__fields__
            and self.config_keys.receive_connector_configuration
        ):
            params["connector_configuration"] = self.config_keys

        return params

    def add_domain_parameter(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_sub_domain:
            return params
        else:
            params["domain"] = self.domain_parameter
            return params

    def base_name(self) -> str:
        if self.is_sub_domain:
            return self.parent_name
        else:
            return self.name

    # 创建一个没有交易功能的ConnectorBase实例，并使用默认配置进行初始化。
    def non_trading_connector_instance_with_default_configuration(
        self, trading_pairs: Optional[List[str]] = None
    ) -> "ConnectorBase":
        from hummingbot.client.config.config_helpers import ClientConfigAdapter
        from hummingbot.client.hummingbot_application import HummingbotApplication

        trading_pairs = trading_pairs or []
        # 动态导入交易所模块的类
        # 比如，对于 binance 来说，就是动态导入 connector/exchange/binance/binance_exchange.py 下的 BinanceExchange 类
        connector_class = getattr(importlib.import_module(self.module_path()), self.class_name())
        kwargs = {}
        # 下面的 if...elif... 是为了获取交易所的 api secret keys 相关的信息
        if isinstance(self.config_keys, Dict):
            kwargs = {key: (config.value or "") for key, config in self.config_keys.items()}  # legacy
        elif self.config_keys is not None:
            # 新版会把密钥信息给加密
            kwargs = {
                traverse_item.attr: traverse_item.value.get_secret_value()
                if isinstance(traverse_item.value, SecretStr)
                else traverse_item.value or ""
                for traverse_item in ClientConfigAdapter(self.config_keys).traverse()
                if traverse_item.attr != "connector"
            }
        kwargs = self.conn_init_parameters(
            trading_pairs=trading_pairs,
            trading_required=False,
            api_keys=kwargs,
            client_config_map=HummingbotApplication.main_application().client_config_map,
        )
        # 如果当前交易所设置是子域名的话，则向入参中添加 domain 的入参
        kwargs = self.add_domain_parameter(kwargs)
        # 实例化交易所类的实例
        connector = connector_class(**kwargs)

        return connector

    def _load_clob_api_data_source(
        self,
        trading_pairs: List[str],
        trading_required: bool,
        client_config_map: "ClientConfigAdapter",
        connector_spec: Dict[str, str],
    ) -> "CLOBAPIDataSourceBase":
        module_name = self.get_api_data_source_module_name()
        parent_package = f"hummingbot.connector.gateway.{self._get_module_package()}.data_sources"
        module_package = self.name.rsplit(sep="_", maxsplit=2)[0]
        module_path = f"{parent_package}.{module_package}.{module_name}"
        module: ModuleType = importlib.import_module(module_path)
        api_data_source_class = getattr(module, self.get_api_data_source_class_name())
        instance = api_data_source_class(
            trading_pairs=trading_pairs,
            connector_spec=connector_spec,
            client_config_map=client_config_map,
        )
        return instance

    def _get_module_package(self) -> str:
        return self.type.name.lower()


class AllConnectorSettings:
    # 项目中已支持的所有交易所的设置信息
    all_connector_settings: Dict[str, ConnectorSetting] = {}

    # 创建交易所的配置项的信息，通过这个方法，应该可以知道接入一个新的交易所需要符合怎样的目录结构
    @classmethod
    def create_connector_settings(cls):
        """
        Iterate over files in specific Python directories to create a dictionary of exchange names to ConnectorSetting.
        """
        cls.all_connector_settings = {}  # reset
        connector_exceptions = ["mock_paper_exchange", "mock_pure_python_paper_exchange", "paper_trade"]

        type_dirs: List[DirEntry] = [
            cast(DirEntry, f)
            for f in scandir(f"{root_path() / 'hummingbot' / 'connector'}")
            if f.is_dir() and f.name not in CONNECTOR_SUBMODULES_THAT_ARE_NOT_CEX_TYPES
        ]
        for type_dir in type_dirs:
            if type_dir.name == "gateway":
                continue
            # 是 hummingbot/connector/exchange/binance 、 hummingbot/connector/exchange/bybit 这一级目录的列表
            connector_dirs: List[DirEntry] = [
                cast(DirEntry, f) for f in scandir(type_dir.path) if f.is_dir() and exists(join(f.path, "__init__.py"))
            ]
            for connector_dir in connector_dirs:
                if connector_dir.name.startswith("_") or connector_dir.name in connector_exceptions:
                    continue
                if connector_dir.name in cls.all_connector_settings:
                    raise Exception(f"Multiple connectors with the same {connector_dir.name} name.")
                try:
                    util_module_path: str = (
                        f"hummingbot.connector.{type_dir.name}." f"{connector_dir.name}.{connector_dir.name}_utils"
                    )
                    # importlib.import_module：运行时动态加载模块
                    util_module = importlib.import_module(util_module_path)
                except ModuleNotFoundError:
                    continue
                trade_fee_settings: List[float] = getattr(util_module, "DEFAULT_FEES", None)
                trade_fee_schema: TradeFeeSchema = cls._validate_trade_fee_schema(
                    connector_dir.name, trade_fee_settings
                )
                cls.all_connector_settings[connector_dir.name] = ConnectorSetting(
                    name=connector_dir.name,
                    type=ConnectorType[type_dir.name.capitalize()],
                    centralised=getattr(util_module, "CENTRALIZED", True),
                    example_pair=getattr(util_module, "EXAMPLE_PAIR", ""),
                    use_ethereum_wallet=getattr(util_module, "USE_ETHEREUM_WALLET", False),
                    trade_fee_schema=trade_fee_schema,
                    config_keys=getattr(util_module, "KEYS", None),
                    is_sub_domain=False,
                    parent_name=None,
                    domain_parameter=None,
                    use_eth_gas_lookup=getattr(util_module, "USE_ETH_GAS_LOOKUP", False),
                )
                # Adds other domains of connector
                other_domains = getattr(util_module, "OTHER_DOMAINS", [])
                for domain in other_domains:
                    trade_fee_settings = getattr(util_module, "OTHER_DOMAINS_DEFAULT_FEES")[domain]
                    trade_fee_schema = cls._validate_trade_fee_schema(domain, trade_fee_settings)
                    parent = cls.all_connector_settings[connector_dir.name]
                    cls.all_connector_settings[domain] = ConnectorSetting(
                        name=domain,
                        type=parent.type,
                        centralised=parent.centralised,
                        example_pair=getattr(util_module, "OTHER_DOMAINS_EXAMPLE_PAIR")[domain],
                        use_ethereum_wallet=parent.use_ethereum_wallet,
                        trade_fee_schema=trade_fee_schema,
                        config_keys=getattr(util_module, "OTHER_DOMAINS_KEYS")[domain],
                        is_sub_domain=True,
                        parent_name=parent.name,
                        domain_parameter=getattr(util_module, "OTHER_DOMAINS_PARAMETER")[domain],
                        use_eth_gas_lookup=parent.use_eth_gas_lookup,
                    )

        # add gateway connectors
        """
        Hummingbot 的 "gateway" 是指连接到不同加密货币交易所的接口，它充当了 Hummingbot 与交易所之间的桥梁，使 Hummingbot 能够与各种不同的交易所进行交互。
        这个功能对于创建和管理交易机器人非常重要，因为不同的交易所可能有不同的API、安全性要求和数据格式，而 Hummingbot 的 gateway 为用户提供了一个统一的方式来与这些交易所进行通信。

        具体来说，Hummingbot 的 gateway 主要执行以下任务：

        1. 连接交易所：它提供了连接到不同交易所的能力，包括设置API密钥、建立连接和进行身份验证等。
        2. 获取市场数据：Hummingbot 通过 gateway 从交易所获取市场数据，包括交易对价格、深度数据、历史交易等。这些数据对于制定交易策略非常重要。
        3. 执行交易订单：通过 gateway，Hummingbot 可以创建和执行交易订单，包括市价单、限价单、止损单等，从而实现自动交易策略。
        4. 管理账户信息：gateway 也允许 Hummingbot 查询账户余额、交易历史和开放订单等信息，以便更好地监控和管理交易。
        5. 错误处理和安全性：gateway 处理与交易所通信时可能出现的错误，同时确保交易所API的安全性，以防止未经授权的访问。

        总之，Hummingbot 的 gateway 是一个重要的组件，使用户能够轻松地在多个不同的加密货币交易所上运行交易策略，从而实现自动化的加密货币交易。
        """
        gateway_connections_conf: List[Dict[str, str]] = GatewayConnectionSetting.load()
        trade_fee_settings: List[float] = [0.0, 0.0]  # we assume no swap fees for now
        trade_fee_schema: TradeFeeSchema = cls._validate_trade_fee_schema("gateway", trade_fee_settings)

        for connection_spec in gateway_connections_conf:
            market_name: str = GatewayConnectionSetting.get_market_name_from_connector_spec(connection_spec)
            cls.all_connector_settings[market_name] = ConnectorSetting(
                name=market_name,
                type=ConnectorType[connection_spec["trading_type"]],
                centralised=False,
                example_pair="WETH-USDC",
                use_ethereum_wallet=False,
                trade_fee_schema=trade_fee_schema,
                config_keys=None,
                is_sub_domain=False,
                parent_name=None,
                domain_parameter=None,
                use_eth_gas_lookup=False,
            )

        return cls.all_connector_settings

    @classmethod
    def initialize_paper_trade_settings(cls, paper_trade_exchanges: List[str]):
        for e in paper_trade_exchanges:
            base_connector_settings: Optional[ConnectorSetting] = cls.all_connector_settings.get(e, None)
            if base_connector_settings:
                paper_trade_settings = ConnectorSetting(
                    name=f"{e}_paper_trade",
                    type=base_connector_settings.type,
                    centralised=base_connector_settings.centralised,
                    example_pair=base_connector_settings.example_pair,
                    use_ethereum_wallet=base_connector_settings.use_ethereum_wallet,
                    trade_fee_schema=base_connector_settings.trade_fee_schema,
                    config_keys=base_connector_settings.config_keys,
                    is_sub_domain=False,
                    parent_name=base_connector_settings.name,
                    domain_parameter=None,
                    use_eth_gas_lookup=base_connector_settings.use_eth_gas_lookup,
                )
                cls.all_connector_settings.update({f"{e}_paper_trade": paper_trade_settings})

    @classmethod
    def get_connector_settings(cls) -> Dict[str, ConnectorSetting]:
        if len(cls.all_connector_settings) == 0:
            cls.all_connector_settings = cls.create_connector_settings()
        return cls.all_connector_settings

    # 获取 connector 对应的交易所的 secret key 配置项的信息
    @classmethod
    def get_connector_config_keys(cls, connector: str) -> Optional["BaseConnectorConfigMap"]:
        return cls.get_connector_settings()[connector].config_keys

    @classmethod
    def reset_connector_config_keys(cls, connector: str):
        current_settings = cls.get_connector_settings()[connector]
        current_keys = current_settings.config_keys
        new_keys = current_keys if current_keys is None else current_keys.__class__.construct()
        cls.update_connector_config_keys(new_keys)

    @classmethod
    def update_connector_config_keys(cls, new_config_keys: "BaseConnectorConfigMap"):
        current_settings = cls.get_connector_settings()[new_config_keys.connector]
        new_keys_settings_dict = current_settings._asdict()
        new_keys_settings_dict.update({"config_keys": new_config_keys})
        cls.get_connector_settings()[new_config_keys.connector] = ConnectorSetting(**new_keys_settings_dict)

    @classmethod
    def get_exchange_names(cls) -> Set[str]:
        return {
            cs.name
            for cs in cls.get_connector_settings().values()
            if cs.type in [ConnectorType.Exchange, ConnectorType.CLOB_SPOT, ConnectorType.CLOB_PERP]
        }.union(set(PAPER_TRADE_EXCHANGES))

    @classmethod
    def get_derivative_names(cls) -> Set[str]:
        return {
            cs.name
            for cs in cls.all_connector_settings.values()
            if cs.type in [ConnectorType.Derivative, ConnectorType.AMM_Perpetual, ConnectorType.CLOB_PERP]
        }

    @classmethod
    def get_derivative_dex_names(cls) -> Set[str]:
        return {cs.name for cs in cls.all_connector_settings.values() if cs.type is ConnectorType.AMM_Perpetual}

    @classmethod
    def get_other_connector_names(cls) -> Set[str]:
        return {cs.name for cs in cls.all_connector_settings.values() if cs.type is ConnectorType.Connector}

    @classmethod
    def get_eth_wallet_connector_names(cls) -> Set[str]:
        return {cs.name for cs in cls.all_connector_settings.values() if cs.use_ethereum_wallet}

    @classmethod
    def get_gateway_amm_connector_names(cls) -> Set[str]:
        return {cs.name for cs in cls.get_connector_settings().values() if cs.type == ConnectorType.AMM}

    @classmethod
    def get_gateway_evm_amm_lp_connector_names(cls) -> Set[str]:
        return {cs.name for cs in cls.all_connector_settings.values() if cs.type == ConnectorType.AMM_LP}

    @classmethod
    def get_gateway_clob_connector_names(cls) -> Set[str]:
        return {cs.name for cs in cls.all_connector_settings.values() if cs.type == ConnectorType.CLOB_SPOT}

    @classmethod
    def get_example_pairs(cls) -> Dict[str, str]:
        return {name: cs.example_pair for name, cs in cls.get_connector_settings().items()}

    @classmethod
    def get_example_assets(cls) -> Dict[str, str]:
        return {name: cs.example_pair.split("-")[0] for name, cs in cls.get_connector_settings().items()}

    @staticmethod
    def _validate_trade_fee_schema(
        exchange_name: str, trade_fee_schema: Optional[Union[TradeFeeSchema, List[float]]]
    ) -> TradeFeeSchema:
        if not isinstance(trade_fee_schema, TradeFeeSchema):
            # backward compatibility
            maker_percent_fee_decimal = (
                Decimal(str(trade_fee_schema[0])) / Decimal("100") if trade_fee_schema is not None else Decimal("0")
            )
            taker_percent_fee_decimal = (
                Decimal(str(trade_fee_schema[1])) / Decimal("100") if trade_fee_schema is not None else Decimal("0")
            )
            trade_fee_schema = TradeFeeSchema(
                maker_percent_fee_decimal=maker_percent_fee_decimal,
                taker_percent_fee_decimal=taker_percent_fee_decimal,
            )
        return trade_fee_schema


def ethereum_wallet_required() -> bool:
    """
    Check if an Ethereum wallet is required for any of the exchanges the user's config uses.
    """
    return any(e in AllConnectorSettings.get_eth_wallet_connector_names() for e in required_exchanges)


def ethereum_gas_station_required() -> bool:
    """
    Check if the user's config needs to look up gas costs from an Ethereum gas station.
    """
    return any(
        name
        for name, con_set in AllConnectorSettings.get_connector_settings().items()
        if name in required_exchanges and con_set.use_eth_gas_lookup
    )


def ethereum_required_trading_pairs() -> List[str]:
    """
    Check if the trading pairs require an ethereum wallet (ERC-20 tokens).
    """
    ret_val = []
    for conn, t_pair in requried_connector_trading_pairs.items():
        if AllConnectorSettings.get_connector_settings()[conn].use_ethereum_wallet:
            ret_val += t_pair
    return ret_val


def gateway_connector_trading_pairs(connector: str) -> List[str]:
    """
    Returns trading pair used by specified gateway connnector.
    """
    ret_val = []
    for conn, t_pair in requried_connector_trading_pairs.items():
        if AllConnectorSettings.get_connector_settings()[conn].uses_gateway_generic_connector() and conn == connector:
            ret_val += t_pair
    return ret_val


MAXIMUM_OUTPUT_PANE_LINE_COUNT = 1000
MAXIMUM_LOG_PANE_LINE_COUNT = 1000
MAXIMUM_TRADE_FILLS_DISPLAY_OUTPUT = 100

STRATEGIES: List[str] = get_strategy_list()
GATEWAY_CONNECTORS: List[str] = []
