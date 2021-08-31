"""检查并自动安装外部依赖程序
"""
import os
import platform
import shutil
import pathlib
import argparse

from .exception import ColorTraceEnvironmentError

# 外部程序
cli_pngquant = "pngquant"
cli_pngnq = "pngnq"
cli_imagemagick = "magick"
cli_potrace = "potrace"

MUST_INSTALL = [cli_pngquant, cli_imagemagick, cli_potrace]
OPTIONAL_INSTALL = [cli_pngnq]

def localbin目录():
    """当找不到依赖程序的可执行文件时，将考虑把新下载的程序存储在 ~/.local/bin 目录中
    """
    if platform.system() == "Windows":
        homedir = pathlib.Path(os.getenv("USERPROFILE"))
    else:
        homedir = pathlib.Path(os.getenv("HOME"))
    localbin = homedir / ".local" / "bin"
    if not localbin.exists():
        localbin.mkdir(parents=True)
    return localbin


def 检查外部依赖程序的安装():
    """当存在缺失的必要依赖时，抛出 ColorTraceEnvironmentError，并包含相关名称列表
    """
    必要依赖 = [shutil.which(exe) for exe in MUST_INSTALL]

    if not all(必要依赖):
        未安装的必要依赖 = [name for name, path in zip(MUST_INSTALL, 必要依赖) if path is None]
        raise ColorTraceEnvironmentError(未安装的必要依赖)


def cli_install(debug_args=None):
    """公开函数，由命令行调用

    :param debug_args: 调试时传入 List[str]，正常时传入 None 而从 sys.argv 读取。
    """
    p = argparse.ArgumentParser(prog="color-trace-install", description=f"安装指定的依赖程序({','.join(MUST_INSTALL + OPTIONAL_INSTALL)})")
    p.add_argument("NAME", nargs="*", help="需要安装的依赖名称，默认安装全部必要依赖")
    args = p.parse_args(debug_args)

    if args.NAME:
        for name in args.NAME:
            path = shutil.which(name)
            if path:
                print(f"(install): {name} 已安装在 {path!r}，跳过安装")
            else:
                安装依赖(name)
    else:
        try:
            检查外部依赖程序的安装()
        except ColorTraceEnvironmentError as e:
            NEED_INSTALL = e.args[0]
            print(f"(install): 安装缺失的必要依赖 {NEED_INSTALL!r}")
            for name in NEED_INSTALL:
                安装依赖(name)


def 安装依赖(name):
    if name == "pngquant":
        install_pngquant()
    elif name == "pngnq":
        install_pngnq()
    elif name == "imagemagick":
        install_imagemagick()
    elif name == "potrace":
        install_potrace()
    else:
        print(f"(install): 不支持的名称 {name!r}，应为 {','.join(MUST_INSTALL + OPTIONAL_INSTALL)!r} 之一")
        raise ValueError(name)

def install_pngquant():
    homepage = "https://pngquant.org/"
    raise NotImplementedError(f"暂未实现，请跳转至官网 {homepage}")


def install_pngnq():
    homepage = "http://pngnq.sourceforge.net/"
    raise NotImplementedError(f"暂未实现，请跳转至官网 {homepage}")


def install_imagemagick():
    homepage = "https://imagemagick.org/index.php"
    raise NotImplementedError(f"暂未实现，请跳转至官网 {homepage}")


def install_potrace():
    homepage = "http://potrace.sourceforge.net/"
    raise NotImplementedError(f"暂未实现，请跳转至官网 {homepage}")