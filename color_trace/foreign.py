"""检查并自动安装外部依赖程序
"""
import os
import platform
import shutil
import pathlib

from .exception import ColorTraceEnvironmentError

# 外部程序
cli_pngquant = "pngquant"
cli_pngnq = "pngnq"
cli_imagemagick = "magick"
cli_potrace = "potrace"

MUST_INSTALLED = [cli_pngquant, cli_imagemagick, cli_potrace]
OPTIONAL_INSTALLED = [cli_pngnq]

def localbin目录():
    """当找不到依赖程序的可执行文件时，将考虑把新下载的程序存储在 ~/.local/bin 目录中
    """
    if platform.system() == "Windows":
        homedir = pathlib.Path(os.getenv("USERPROFILE"))
    else:
        homedir = pathlib.Path(os.getenv("HOME"))
    localbin = homedir / ".local" / "bin"
    return localbin


def 检查外部依赖程序的安装():
    必要依赖 = [shutil.which(exe) for exe in MUST_INSTALLED]
    # 可选依赖 = [shutil.which(exe) for exe in OPTIONAL_INSTALLED]

    if not all(必要依赖):
        未安装的必要依赖 = [name for name, path in zip(MUST_INSTALLED, 必要依赖) if path is None]
        for name in 未安装的必要依赖:
            print("错误：存在未安装的必要依赖 {!r}，程序无法运行".format(name))
        raise ColorTraceEnvironmentError(未安装的必要依赖)
