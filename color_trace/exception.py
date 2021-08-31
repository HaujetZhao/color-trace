class ColorTraceError(Exception):
    pass

class ColorTraceEnvironmentError(ColorTraceError):
    """依赖环境发生问题，可能发生的原因

    1. Path 环境变量没配置好，导致找不到外部程序的可执行文件
    2. 外部程序没有安装
    """


class ColorTraceForeignCallError(ColorTraceError):
    """外部程序的调用上发生问题，可能发生的原因：

    1. 命令行参数没配置对
    """