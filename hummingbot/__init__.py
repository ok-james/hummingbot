import logging
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from os import listdir, path
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from hummingbot.logger.struct_logger import StructLogger, StructLogRecord

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter as _ClientConfigAdapter

STRUCT_LOGGER_SET = False
DEV_STRATEGY_PREFIX = "dev"
_prefix_path = None

# Do not raise exceptions during log handling
logging.setLogRecordFactory(StructLogRecord)
logging.setLoggerClass(StructLogger)

_shared_executor = None
_data_path = None
_cert_path = None


def root_path() -> Path:
    from os.path import join, realpath

    # root_path 这个方法无论是在哪里调用，__file__ 的值都是指当前文件，而
    # 这里有点反直觉， "../../" 对应的是当前项目的根目录，当前文件用如下路径表示： /hummingbot/__init__.py ，那么 "../../" 就是指的开头的 "/"，
    # 而如果是 "../" 的话，对应的就是 "/hummingbot" ，感觉是 __init__.py 也是一级路径
    # 这可能是由于 join(__file__, "../../") 的结果导致的：/Users/zhangwubin/Desktop/source/deploy-examples/hello/hello.py/../../
    # 这里给出一个示例，只需关注这个路径的后面部分，这样就比较清晰了，当前文件确实被当做其中的一级路径了
    return Path(realpath(join(__file__, "../../")))


def get_executor() -> ThreadPoolExecutor:
    global _shared_executor
    if _shared_executor is None:
        _shared_executor = ThreadPoolExecutor()
    return _shared_executor


# 项目运行的根目录
def prefix_path() -> str:
    global _prefix_path
    if _prefix_path is None:
        from os.path import join, realpath

        _prefix_path = realpath(join(__file__, "../../"))
    return _prefix_path


def set_prefix_path(p: str):
    global _prefix_path
    _prefix_path = p


def data_path() -> str:
    global _data_path
    if _data_path is None:
        from os.path import join, realpath

        _data_path = realpath(join(prefix_path(), "data"))

    import os

    if not os.path.exists(_data_path):
        os.makedirs(_data_path)
    return _data_path


def set_data_path(path: str):
    global _data_path
    _data_path = path


_independent_package: Optional[bool] = None


def is_independent_package() -> bool:
    global _independent_package
    import os

    if _independent_package is None:
        _independent_package = not os.path.basename(sys.executable).startswith("python")
    return _independent_package


def check_dev_mode():
    try:
        if is_independent_package():
            return False
        if not path.isdir(".git"):
            return False
        current_branch = subprocess.check_output(["git", "symbolic-ref", "--short", "HEAD"]).decode("utf8").rstrip()
        if current_branch != "master":
            return True
    except Exception:
        return False


def chdir_to_data_directory():
    if not is_independent_package():
        # Do nothing.
        return

    import os

    import appdirs

    app_data_dir: str = appdirs.user_data_dir("Hummingbot", "hummingbot.io")
    os.makedirs(os.path.join(app_data_dir, "logs"), 0o711, exist_ok=True)
    os.makedirs(os.path.join(app_data_dir, "conf"), 0o711, exist_ok=True)
    os.makedirs(os.path.join(app_data_dir, "pmm_scripts"), 0o711, exist_ok=True)
    os.makedirs(os.path.join(app_data_dir, "certs"), 0o711, exist_ok=True)
    os.makedirs(os.path.join(app_data_dir, "scripts"), 0o711, exist_ok=True)
    os.chdir(app_data_dir)
    set_prefix_path(app_data_dir)


def get_logging_conf(conf_filename: str = "hummingbot_logs.yml"):
    import io
    from os.path import join
    from typing import Dict

    from ruamel.yaml import YAML

    file_path: str = join(prefix_path(), "conf", conf_filename)
    yaml_parser: YAML = YAML()
    if not path.exists(file_path):
        return {}
    with open(file_path) as fd:
        yml_source: str = fd.read()
        io_stream: io.StringIO = io.StringIO(yml_source)
        config_dict: Dict = yaml_parser.load(io_stream)
        return config_dict


def init_logging(
    conf_filename: str,
    client_config_map: "_ClientConfigAdapter",
    override_log_level: Optional[str] = None,
    strategy_file_path: str = "hummingbot",
):
    import io
    import logging.config
    from os.path import join
    from typing import Dict

    import pandas as pd
    from ruamel.yaml import YAML

    from hummingbot.logger.struct_logger import StructLogger, StructLogRecord

    global STRUCT_LOGGER_SET
    if not STRUCT_LOGGER_SET:
        # 这两行代码设置了 Python 的日志系统，使其使用自定义的 StructLogRecord 和 StructLogger 来处理日志记录。
        logging.setLogRecordFactory(StructLogRecord)
        logging.setLoggerClass(StructLogger)
        STRUCT_LOGGER_SET = True

    # Do not raise exceptions during log handling
    logging.raiseExceptions = False

    file_path: str = join(prefix_path(), "conf", conf_filename)
    yaml_parser: YAML = YAML()
    with open(file_path) as fd:
        yml_source: str = fd.read()
        # 替换配置文件中的占位符：在读取配置文件后，代码对配置文件内容进行了一系列的替换操作
        yml_source = yml_source.replace("$PROJECT_DIR", prefix_path())
        yml_source = yml_source.replace("$DATETIME", pd.Timestamp.now().strftime("%Y-%m-%d-%H-%M-%S"))
        yml_source = yml_source.replace("$STRATEGY_FILE_PATH", strategy_file_path.replace(".yml", ""))
        io_stream: io.StringIO = io.StringIO(yml_source)
        config_dict: Dict = yaml_parser.load(io_stream)
        if override_log_level is not None and "loggers" in config_dict:
            for logger in config_dict["loggers"]:
                if logger in client_config_map.logger_override_whitelist:
                    config_dict["loggers"][logger]["level"] = override_log_level
        # 将 config_dict 中的配置应用到 Python 的日志系统中，从而配置了日志记录的格式和行为。
        logging.config.dictConfig(config_dict)


def get_strategy_list() -> List[str]:
    """
    Search `hummingbot.strategy` folder for all available strategies
    Automatically hide all strategies that starts with "dev" if on master branch
    """
    try:
        folder = path.realpath(path.join(__file__, "../strategy"))
        # Only include valid directories
        strategies = [d for d in listdir(folder) if path.isdir(path.join(folder, d)) and not d.startswith("__")]
        on_dev_mode = check_dev_mode()
        if not on_dev_mode:
            strategies = [s for s in strategies if not s.startswith(DEV_STRATEGY_PREFIX)]
        return sorted(strategies)
    except Exception as e:
        logging.getLogger().warning(f"Error getting strategy set: {str(e)}")
        return []
