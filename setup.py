import os
import subprocess
import sys

import numpy as np
from setuptools import find_packages, setup
from setuptools.command.build_ext import build_ext
from Cython.Build import cythonize

# 获取操作系统的名字
is_posix = os.name == "posix"

if is_posix:
    # subprocess.check_output：运行命令
    # uname： linux 命令，获取内核名称
    os_name = subprocess.check_output("uname").decode("utf8")
    if "Darwin" in os_name:
        # os.environ：系统的环境变量
        # CFLAGS：用于 c 编译器
        os.environ["CFLAGS"] = "-stdlib=libc++ -std=c++11"
    else:
        os.environ["CFLAGS"] = "-std=c++11"

if os.environ.get("WITHOUT_CYTHON_OPTIMIZATIONS"):
    os.environ["CFLAGS"] += " -O0"


# Avoid a gcc warning below:
# cc1plus: warning: command line option ???-Wstrict-prototypes??? is valid
# for C/ObjC but not for C++
class BuildExt(build_ext):
    def build_extensions(self):
        if os.name != "nt" and "-Wstrict-prototypes" in self.compiler.compiler_so:
            self.compiler.compiler_so.remove("-Wstrict-prototypes")
        super().build_extensions()


def main():
    cpu_count = os.cpu_count() or 8
    version = "20230828"
    # 发现包的目录
    packages = find_packages(include=["hummingbot", "hummingbot.*"])
    package_data = {
        "hummingbot": ["core/cpp/*", "VERSION", "templates/*TEMPLATE.yml"],
    }
    install_requires = [
        "0x-contract-addresses",
        "0x-contract-wrappers",
        "0x-order-utils",
        "aioconsole",
        "aiohttp",
        "asyncssh",
        "appdirs",
        "appnope",
        "async-timeout",
        "bidict",
        "base58",
        "cachetools",
        "certifi",
        "coincurve",
        "cryptography",
        "cython",
        "cytoolz",
        "commlib-py",
        "docker",
        "diff-cover",
        "dydx-python",
        "dydx-v3-python",
        "eip712-structs",
        "eth-abi",
        "eth-account",
        "eth-bloom",
        "eth-keyfile",
        "eth-typing",
        "eth-utils",
        "ethsnarks-loopring",
        "flake8",
        "hexbytes",
        "importlib-metadata",
        "injective-py" "mypy-extensions",
        "nose",
        "nose-exclude",
        "numpy",
        "pandas",
        "pip",
        "pre-commit",
        "prompt-toolkit",
        "psutil",
        "pydantic",
        "pyjwt",
        "pyperclip",
        "python-dateutil",
        "python-telegram-bot",
        "pyOpenSSL",
        "requests",
        "rsa",
        "ruamel-yaml",
        "scipy",
        "signalr-client-aio",
        "simplejson",
        "six",
        "sqlalchemy",
        "tabulate",
        "tzlocal",
        "ujson",
        "web3",
        "websockets",
        "yarl",
    ]

    cython_kwargs = {
        "language": "c++",
        "language_level": 3,
    }

    cython_sources = ["hummingbot/**/*.pyx"]

    if os.environ.get("WITHOUT_CYTHON_OPTIMIZATIONS"):
        compiler_directives = {
            "optimize.use_switch": False,
            "optimize.unpack_method_calls": False,
        }
    else:
        compiler_directives = {}

    if is_posix:
        cython_kwargs["nthreads"] = cpu_count

    if "DEV_MODE" in os.environ:
        version += ".dev1"
        package_data[""] = ["*.pxd", "*.pyx", "*.h"]
        package_data["hummingbot"].append("core/cpp/*.cpp")

    if len(sys.argv) > 1 and sys.argv[1] == "build_ext" and is_posix:
        sys.argv.append(f"--parallel={cpu_count}")

    # setup 方法文档：https://setuptools.pypa.io/en/latest/deprecated/distutils/apiref.html#distutils.core.setup
    setup(
        name="hummingbot",
        version=version,
        description="Hummingbot",
        url="https://github.com/hummingbot/hummingbot",
        author="CoinAlpha, Inc.",
        author_email="dev@hummingbot.io",
        license="Apache 2.0",
        packages=packages,
        # package_data 用来指定除了 .py 文件之外，哪些文件需要作为数据文件，https://setuptools.pypa.io/en/latest/userguide/datafiles.html#package-data
        package_data=package_data,
        install_requires=install_requires,
        ext_modules=cythonize(cython_sources, compiler_directives=compiler_directives, **cython_kwargs),
        include_dirs=[np.get_include()],
        # 要构建和安装的独立脚本文件列表
        scripts=["bin/hummingbot.py", "bin/hummingbot_quickstart.py"],
        cmdclass={"build_ext": BuildExt},
    )


if __name__ == "__main__":
    main()
