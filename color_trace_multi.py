#!/usr/bin/env python
"""trace multiple color images with potrace"""

# color_trace_multi
# Written by ukurereh
# May 20, 2012

# 赵豪杰在 Python3.8 下重写
# 2021年8月5日

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


# 外部程序的路径
PNGQUANT_路径 = 'pngquant'
PNGNQ_路径 = 'pngnq'
IMAGEMAGICK_CONVERT_路径 = 'magick convert'
IMAGEMAGICK_IDENTIFY_路径 = 'magick identify'
POTRACE_路径 = 'potrace'

POTRACE_DPI = 90.0  # potrace docs 说它是 72, 但这个数值似乎效果最好
命令行最长 = 1900  # 命令行长度限制
日志级别 = 0  # 不止是一个常数，它也会爱 -v/--verbose 选项影响

版本 = '1.01'

import os, sys
import shutil
import subprocess
import argparse
from glob import iglob
import functools
import queue
import multiprocessing
import queue
import tempfile
import time

from svg_stack import svg_stack


def 汇报(*args, level=1):
    if 日志级别 >= level:
        print(*args)


def 处理命令(命令, stdinput=None, stdout_=False, stderr_=False):
    """在后台 shell 中运行命令，返回 stdout 和/或 stderr

    返回 stdout, stderr 或一个数组（stdout, stderr），取决于 stdout, stderr 参数
    是否为 True。如果遇到错误，则抛出。

    命令: 要运行的命令
    stdinput: data (bytes) to send to command's stdin, or None
    stdout_: True to receive command's stdout in the return value
    stderr_: True to receive command's stderr in the return value
"""
    汇报(命令)
    stdin_pipe = (subprocess.PIPE if stdinput is not None else None)
    stdout_pipe = (subprocess.PIPE if stdout_ is True else None)
    stderr_pipe = subprocess.PIPE

    # process = subprocess.Popen(command, stdin=stdin_pipe, stderr=stderr_pipe, stdout=stdout_pipe,
    # shell=True, creationflags=subprocess.SW_HIDE)
    进程 = subprocess.Popen(命令, stdin=stdin_pipe, stderr=stderr_pipe, stdout=stdout_pipe,
                          shell=True)

    stdoutput, stderror = 进程.communicate(stdinput)
    # print(stderror)
    返回码 = 进程.wait()
    if 返回码 != 0:
        Exception(stderror.decode())
    if stdout_ and not stderr_:
        return stdoutput
    elif stderr_ and not stdout_:
        return stderr
    elif stdout_ and stderr_:
        return (stdoutput, stderror)
    elif not stdout_ and not stderr_:
        return None


def 重缩放(源, 目标, 缩放, 滤镜='lanczos'):
    """rescale src image to scale, save to destscale

    full list of filters is available from ImageMagick's documentation.
"""
    if 缩放 == 1.0:  # just copy it over
        shutil.copyfile(源, 目标)
    else:
        命令 = '"{convert}" "{src}" -filter {filter} -resize {resize}% "{dest}"'.format(
            convert=IMAGEMAGICK_CONVERT_路径, src=源, filter=滤镜, resize=缩放 * 100,
            dest=目标)
        处理命令(命令)


def 量化(源, 量化目标, 颜色数, 算法='mc', 拟色=None):
    """将源图像量化到指定数量的颜色，保存到量化目标

    量化：缩减颜色数量，只保留最主要的颜色

    使用指定的算法来量化图像。
    源：源图像的路径，必须是 png 文件
    量化目标：输出图像的路径
    颜色数：要缩减到的颜色数量，0 就是不量化
    算法：
        - 'mc' = median-cut 中切 (默认值, 只有少量颜色, 使用 pngquant)
        - 'as' = adaptive spatial subdivision 自适应空间细分 (使用 imagemagick, 产生的颜色更少)
        - 'nq' = neuquant (生成许多颜色, 使用 pngnq)
    拟色: 量化时使用的抖动拟色算法
        None: 默认，不拟色
        'floydsteinberg': 当使用 'mc', 'as', 和 'nq' 时可用
        'riemersma': 只有使用 'as' 时可用
    """
    # 创建和执行量化图像的命令

    if 颜色数 == 0:
        # 跳过量化，直接复制输入到输出
        shutil.copyfile(源, 量化目标)

    elif 算法 == 'mc':  # median-cut 中切
        if 拟色 is None:
            拟色选项 = '-nofs '
        elif 拟色 == 'floydsteinberg':
            拟色选项 = ''
        else:
            raise ValueError("对 'mc' 量化方法使用了错误的拟色类型：'{0}' ".format(拟色))
        # 因为 pngquant 不能保存到中文路径，所以使用 stdin/stdout 操作 pngquant
        命令 = '"{pngquant}" {dither}-force {colors}'.format(
            pngquant=PNGQUANT_路径, dither=拟色选项, colors=颜色数)
        with open(源, 'rb') as 源文件:
            stdinput = 源文件.read()
        stdoutput = 处理命令(命令, stdinput=stdinput, stdout_=True)
        with open(量化目标, 'wb') as 目标文件:
            目标文件.write(stdoutput)

    elif 算法 == 'as':  # adaptive spatial subdivision 自适应空间细分
        if 拟色 is None:
            拟色选项 = 'None'
        elif 拟色 in ('floydsteinberg', 'riemersma'):
            拟色选项 = 拟色
        else:
            raise ValueError("Invalid dither type '{0}' for 'as' quantization".format(拟色))
        命令 = '"{convert}" "{src}" -dither {dither} -colors {colors} "{dest}"'.format(
            convert=IMAGEMAGICK_CONVERT_路径, src=源, dither=拟色选项, colors=颜色数, dest=量化目标)
        处理命令(命令)

    elif 算法 == 'nq':  # neuquant
        ext = "~quant.png"
        destdir = os.path.dirname(量化目标)
        if 拟色 is None:
            拟色选项 = ''
        elif 拟色 == 'floydsteinberg':
            拟色选项 = '-Q f '
        else:
            raise ValueError("Invalid dither type '{0}' for 'nq' quantization".format(拟色))
        命令 = '"{pngnq}" -f {dither}-d "{destdir}" -n {colors} -e {ext} "{src}"'.format(
            pngnq=PNGNQ_路径, dither=拟色选项, destdir=destdir, colors=颜色数, ext=ext, src=源)
        处理命令(命令)
        # 因为 pngnq 不支持保存到自定义目录，所以先输出文件到当前目录，再移动到量化目标
        旧输出 = os.path.join(destdir, os.path.splitext(os.path.basename(源))[0] + ext)
        os.rename(旧输出, 量化目标)
    else:
        # 在错误到达这里前 argparse 应该已经先捕捉到了
        raise NotImplementedError('未知的量化算法 "{0}"'.format(算法))


def 调色板重映射(源, 重映射目标, 调色板图像, 拟色=None):
    """用调色板图像的颜色重映射源图像，保存到重映射目标

    源: 源图像路径
    重映射目标: 输出保存路径
    调色板图像: 一个图像路径，它包含了 src 将重映射的颜色
    拟色: 重映射时的拟色算法
        选项有：None, 'floydsteinberg', 和 'riemersma'
"""

    if not os.path.exists(调色板图像):  # 因为 ImageMagick 不会检查
        raise IOError("未找到重映射调色板：{0} ".format(调色板图像))

    if 拟色 is None:
        拟色选项 = 'None'
    elif 拟色 in ('floydsteinberg', 'riemersma'):
        拟色选项 = 拟色
    else:
        raise ValueError("不合理的重映射拟色类型：'{0}' ".format(拟色))
    命令 = '"{convert}" "{src}" -dither {dither} -remap "{paletteimg}" "{dest}"'.format(
        convert=IMAGEMAGICK_CONVERT_路径, src=源, dither=拟色选项, paletteimg=调色板图像, dest=重映射目标)
    处理命令(命令)


def 制作调色板(源图像):
    """从源图像得到独特的颜色，返回 #rrggbb 16进制颜色"""

    命令 = '"{convert}" "{srcimage}" -unique-colors -compress none ppm:-'.format(
        convert=IMAGEMAGICK_CONVERT_路径, srcimage=源图像)
    stdoutput = 处理命令(命令, stdout_=True)

    # separate stdout ppm image into its colors
    # 将 stdout ppm 图像分离到它的颜色
    ppm_行 = stdoutput.decode().splitlines()[3:]
    del stdoutput  # 提前释放一部分内存
    颜色值 = tuple()
    for 行 in ppm_行:
        颜色值 += tuple(int(s) for s in 行.split())

    # create i:j ranges that get every 3 values in colorvals
    # 建立在颜色值中得到每 3 个数值的 i:j 范围
    i范围 = range(0, len(颜色值), 3)
    j范围 = range(3, len(颜色值) + 1, 3)
    十六进制颜色 = []
    for i, j in zip(i范围, j范围):
        rgb = 颜色值[i:j]
        十六进制颜色.append("#{0:02x}{1:02x}{2:02x}".format(*rgb))
    十六进制颜色.reverse()  # 生成由亮色背景到暗色背景
    return 十六进制颜色


def 得到调色板外的颜色(调色板, 从黑色开始=True, 规避颜色=None):
    """return a color hex string not listed in palette
    返回一个不在调色板内的16进制颜色字符串

    从黑色开始: 从黑色开始搜索颜色，否则从白色开始
    规避颜色: 一个列表, 指定在搜索时需要规避的颜色
"""
    if 规避颜色 is None:
        最终调色板 = tuple(调色板)
    else:
        最终调色板 = tuple(调色板) + tuple(规避颜色)
    if 从黑色开始:
        颜色范围 = range(int('ffffff', 16))
    else:
        颜色范围 = range(int('ffffff', 16), 0, -1)
    for i in 颜色范围:
        颜色 = "#{0:06x}".format(i)
        if 颜色 not in 最终调色板:
            return 颜色
    # 当调色板加上规避颜色，包含所有颜色 #000000-#ffffff 时，抛出错误
    raise Exception("未能找到调色板之外的颜色")


# def isolate_color(src, destlayer, target_color, palette, stack=False):
#     """fills the specified color of src with black, all else is white

#     src: source image path, must match palette's colors
#     destlayer: path to save output image
#     target_color: the color to isolate (from palette)
#     palette: list of "#010101" etc. (output from make_palette)
#     stack: if True, colors before coloridx are white, colors after are black
# """
#     coloridx = palette.index(target_color)
#     # to avoid problems when the palette contains black or white, background and
#     # foreground colors are chosen that are not in the palette (nor black or white)
#     bg_white = "#FFFFFF"
#     fg_black = "#000000"
#     bg_almost_white = get_nonpalette_color(palette, False, (bg_white, fg_black))
#     fg_almost_black = get_nonpalette_color(palette, True, (bg_almost_white, bg_white, fg_black))

#     # start off the piping of stdin/stdout
#     with open(src, 'rb') as srcfile:
#         stdinput = srcfile.read()

#     for i, col in enumerate(palette):
#         # fill this color with background or foreground?
#         if i == coloridx:
#             fill = fg_almost_black
#         elif i > coloridx and stack:
#             fill = fg_almost_black
#         else:
#             fill = bg_almost_white

#         # build the imagemagick filling command and execute it
#         command = '"{convert}" - -fill {fill} -opaque "{color}" -'.format(
#             convert = IMAGEMAGICK_CONVERT_PATH, fill=fill, color=col)

#         stdoutput = process_command(command, stdinput=stdinput, stdout_=True)
#         stdinput = stdoutput

#     # now color the foreground black and background white
#     command = '"{convert}" - -fill {fillbg} -opaque "{colorbg}" -fill {fillfg} -opaque {colorfg} "{dest}"'.format(
#         convert = IMAGEMAGICK_CONVERT_PATH, fillbg=bg_white, colorbg=bg_almost_white,
#         fillfg=fg_black, colorfg=fg_almost_black, dest=destlayer)
#     process_command(command, stdinput=stdinput)


def 孤立颜色(源, 目标临时文件, 目标图层, 目标颜色, 调色板, stack=False):  # new version
    """将指定颜色区域替换为黑色，其他区域为白色

    源: 源图像路径，必须匹配调色板的颜色
    目标图层: 输出图像的路径
    目标颜色: 要孤立的颜色 (来自调色板)
    调色板: 包含例如 "#010101" 的列表. (从制作调色板输出得到)
    stack: 如果 True，在颜色索引之前的颜色为白，之后的为黑
"""
    颜色索引 = 调色板.index(目标颜色)

    # 为了避免调色板包含纯黑和纯白，背景和前景色都是非调色板的颜色（黑或白）
    背景白 = "#FFFFFF"
    前景黑 = "#000000"
    背景接近白 = 得到调色板外的颜色(调色板, False, (背景白, 前景黑))
    前景接近黑 = 得到调色板外的颜色(调色板, True, (背景接近白, 背景白, 前景黑))

    # 打开管道 stdin/stdout
    with open(源, 'rb') as 源文件:
        stdinput = 源文件.read()

    # 新建一个很长的命令，当它达到足够长度时就执行
    # 因为分别执行填充命令非常的慢
    last_iteration = len(调色板) - 1  # new
    命令前缀 = '"{convert}" "{src}" '.format(convert=IMAGEMAGICK_CONVERT_路径, src=源)
    命令后缀 = ' "{target}"'.format(target=目标临时文件)
    命令中间 = ''

    for i, 颜色 in enumerate(调色板):
        # fill this color with background or foreground?
        if i == 颜色索引:
            填充色 = 前景接近黑
        elif i > 颜色索引 and stack:
            填充色 = 前景接近黑
        else:
            填充色 = 背景接近白

        命令中间 += ' -fill "{fill}" -opaque "{color}"'.format(fill=填充色, color=颜色)
        if len(命令中间) >= 命令行最长 or (i == last_iteration and 命令中间):
            命令 = 命令前缀 + 命令中间 + 命令后缀

            stdoutput = 处理命令(命令, stdinput=stdinput, stdout_=True)
            stdinput = stdoutput
            命令中间 = ''  # reset

    # 现在将前景变黑，背景变白
    命令 = '"{convert}" "{src}" -fill "{fillbg}" -opaque "{colorbg}" -fill "{fillfg}" -opaque "{colorfg}" "{dest}"'.format(
        convert=IMAGEMAGICK_CONVERT_路径, src=目标临时文件, fillbg=背景白, colorbg=背景接近白,
        fillfg=前景黑, colorfg=前景接近黑, dest=目标图层)
    处理命令(命令, stdinput=stdinput)


def 使用颜色填充(源, 目标):
    命令 = '"{convert}" "{src}" -fill "{color}" +opaque none "{dest}"'.format(
        convert=IMAGEMAGICK_CONVERT_路径, src=源, color="#000000", dest=目标)
    处理命令(命令)


def 得到宽度(源):
    """返回头像宽多少像素"""
    命令 = '"{identify}" -ping -format "%w" "{src}"'.format(
        identify=IMAGEMAGICK_IDENTIFY_路径, src=源)
    stdoutput = 处理命令(命令, stdout_=True)
    宽 = int(stdoutput)
    return 宽


def 描摹(源, 描摹目标, 输出颜色, 抑制斑点像素数=2, 平滑转角=1.0, 优化路径=0.2, 宽度=None):
    """在指定的颜色、选项下，运行 potrace

    源: 源文件
    描摹目标: 输出目标文件
    输出颜色: 描摹路径填充的颜色
    抑制斑点像素数: 抑制指定像素数量的斑点
        (等同于 potrace --turdsize)
    平滑转角: 平滑转角: 0 表示不平滑, 1.334 为最大
        (等同于 potrace --alphamax)
    优化路径: 贝塞尔曲线优化: 0 最小, 5 最大
        (等同于 potrace --opttolerance)
    宽度: 输出的 svg 像素宽度, 默认 None. 保持原始比例.
"""

    if 宽度 is not None:
        宽度 = 宽度 / POTRACE_DPI
    命令 = ('"{potrace}" --svg -o "{dest}" -C "{outcolor}" -t {despeckle} '
          '-a {smoothcorners} -O {optimizepaths} {W}{width} "{src}"').format(
        potrace=POTRACE_路径, dest=描摹目标, outcolor=输出颜色,
        despeckle=抑制斑点像素数, smoothcorners=平滑转角, optimizepaths=优化路径,
        W=('-W ' if 宽度 is not None else ''), width=(宽度 if 宽度 is not None else ''),
        src=源)

    处理命令(命令)


def 检查范围(min, max, typefunc, typename, strval):
    """对 argparse 的参数，检查参数是否符合范围

    min: 可接受的最小值
    max: 可接受的最大值
    typefunc: 值转换函数, e.g. float, int
    typename: 值的类型, e.g. "an integer"
    strval: 包含期待值的字符串
"""
    try:
        val = typefunc(strval)
    except ValueError:
        msg = "must be {typename}".format(typename=typename)
        raise argparse.ArgumentTypeError(msg)
    if (max is not None) and (not min <= val <= max):
        msg = "must be between {min} and {max}".format(min=min, max=max)
        raise argparse.ArgumentTypeError(msg)
    elif not min <= val:
        msg = "must be {min} or greater".format(min=min)
        raise argparse.ArgumentTypeError(msg)
    return val


def 获得参数(cmdargs=None):
    """return parser and namespace of parsed command-line arguments

    cmdargs: if specified, a list of command-line arguments to use instead of
        those provided to this script (i.e. a string that has been shlex.split)
"""
    parser = argparse.ArgumentParser(description="trace a color image with "
                                                 "potrace, output color SVG file", add_help=False, prefix_chars='-/')
    # help also accessible via /?
    parser.add_argument(
        '-h', '--help', '/?',
        action='help',
        help="show this help message and exit")
    # file io arguments
    parser.add_argument('-i',
                        '--input', metavar='src', nargs='+', required=True,
                        help="path of input image(s) to trace, supports * and ? wildcards")
    parser.add_argument('-o',
                        '--output', metavar='dest',
                        help="path of output image to save to, supports * wildcard")
    parser.add_argument('-d',
                        '--directory', metavar='destdir',
                        help="outputs to destdir")
    # processing arguments
    parser.add_argument('-C',
                        '--cores', metavar='N',
                        type=functools.partial(检查范围, 0, None, int, "an integer"),
                        help="number of cores to use for image processing. "
                             "Ignored if processing a single file with 1 color "
                             "(default tries to use all cores)")
    # color trace options
    # make colors & palette mutually exclusive
    color_palette_group = parser.add_mutually_exclusive_group(required=True)
    color_palette_group.add_argument('-c',
                                     '--colors', metavar='N',
                                     type=functools.partial(检查范围, 0, 256, int, "an integer"),
                                     help="[required unless -p is used instead] "
                                          "number of colors to reduce each image to before tracing, up to 256. "
                                          "Value of 0 skips color reduction (not recommended unless images "
                                          "are already color-reduced)")
    parser.add_argument('-q',
                        '--quantization', metavar='algorithm',
                        choices=('mc', 'as', 'nq'), default='mc',
                        help="color quantization algorithm: mc, as, or nq. "
                             "'mc' (Median-Cut, default); "
                             "'as' (Adaptive Spatial Subdivision, may result in fewer colors); "
                             "'nq' (NeuQuant, for hundreds of colors). Disabled if --colors 0")
    # make --floydsteinberg and --riemersma dithering mutually exclusive
    dither_group = parser.add_mutually_exclusive_group()
    dither_group.add_argument('-fs',
                              '--floydsteinberg', action='store_true',
                              help="enable Floyd-Steinberg dithering (for any quantization or -p/--palette)."
                                   " Warning: any dithering will greatly increase output svg's size and complexity.")
    dither_group.add_argument('-ri',
                              '--riemersma', action='store_true',
                              help="enable Rimersa dithering (only for Adaptive Spatial Subdivision quantization or -p/--palette)")
    color_palette_group.add_argument('-r',
                                     '--remap', metavar='paletteimg',
                                     help=("use a custom palette image for color reduction [overrides -c "
                                           "and -q]"))
    # image options
    parser.add_argument('-s',
                        '--stack',
                        action='store_true',
                        help="stack color traces (recommended for more accurate output)")
    parser.add_argument('-p',
                        '--prescale', metavar='size',
                        type=functools.partial(检查范围, 0, None, float, "a floating-point number"), default=2,
                        help="scale image this much before tracing for greater detail (default: 2). "
                             "The image's output size is not changed. (2 is recommended, or 3 for smaller "
                             "details.)")
    # potrace options
    parser.add_argument('-D',
                        '--despeckle', metavar='size',
                        type=functools.partial(检查范围, 0, None, int, "an integer"), default=2,
                        help='supress speckles of this many pixels (default: 2)')
    parser.add_argument('-S',
                        '--smoothcorners', metavar='threshold',
                        type=functools.partial(检查范围, 0, 1.334, float, "a floating-point number"), default=1.0,
                        help="set corner smoothing: 0 for no smoothing, 1.334 for max "
                             "(default: 1.0)")
    parser.add_argument('-O',
                        '--optimizepaths', metavar='tolerance',
                        type=functools.partial(检查范围, 0, 5, float, "a floating-point number"), default=0.2,
                        help="set Bezier curve optimization: 0 for least, 5 for most "
                             "(default: 0.2)")
    parser.add_argument('-bg',
                        '--background', action='store_true',
                        help=("set first color as background and posibly optimize final svg"))
    # other options
    parser.add_argument('-v',
                        '--verbose', action='store_true',
                        help="print details about commands executed by this script")
    parser.add_argument('--version', action='version',
                        version='%(prog)s {ver}'.format(ver=版本))

    if cmdargs is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(cmdargs)

    # with multiple inputs, --output must use at least one * wildcard
    multi_inputs = False
    for i, input_ in enumerate(得到输入输出(args.input)):
        if i:
            multi_inputs = True
            break
    if multi_inputs and args.output is not None and '*' not in args.output:
        parser.error("argument -o/--output: must contain '*' wildcard when using multiple input files")

    # 'riemersma' dithering is only allowed with 'as' quantization or --palette option
    if args.riemersma:
        if args.quantization != 'as' and args.palette is None:
            parser.error("argument -ri/--riemersma: only allowed with 'as' quantization")

    return args


def 转义括号(string):
    '''使用 [[] 换替 [，使用 []] 换替 ]  (i.e. escapes [ and ] for globbing)'''
    letters = list(string)
    for i, letter in enumerate(letters[:]):
        if letter == '[':
            letters[i] = '[[]'
        elif letter == ']':
            letters[i] = '[]]'
    return ''.join(letters)


def 得到输入输出(arg_inputs, output_pattern="{0}.svg", ignore_duplicates=True):
    """使用 *? shell 通配符展开，得到 (input, matching output) 的遍历器

    arg_inputs: command-line-given inputs, can include *? wildcards
    output_pattern: pattern to rename output file, with {0} for input's base
        name without extension e.g. pic.png + {0}.svg = pic.svg
    ignore_duplicates: don't process or return inputs that have been returned already.
        Warning: this stores all previous inputs, so can be slow given many inputs
"""
    old_inputs = set()
    for arg_input in arg_inputs:
        if '*' in arg_input or '?' in arg_input:
            # preventing [] expansion here because glob has problems with legal [] filenames
            # ([] expansion still works in a Unix shell, it happens before Python even executes)
            if '[' in arg_input or ']' in arg_input:
                arg_input = 转义括号(arg_input)
            inputs_ = tuple(iglob(os.path.abspath(arg_input)))
        else:
            # ensures non-existing file paths are included so they are reported as such
            # (glob silently skips over non-existing files, but we want to know about them)
            inputs_ = (arg_input,)
        for input_ in inputs_:
            if ignore_duplicates:
                if input_ not in old_inputs:
                    old_inputs.add(input_)
                    basename = os.path.basename(os.path.splitext(input_)[0])
                    output = output_pattern.format(basename)
                    yield input_, output
            else:
                basename = os.path.basename(os.path.splitext(input_)[0])
                output = output_pattern.format(basename)
                yield input_, output


def 队列1_任务(队列2, 总数, 图层, 设置, 输入索引, 输入, 输出):
    """ 初始化文件、重新缩放、缩减颜色

    队列2: 第二个任务列表 (颜色孤立 + 临摹)
    总数: 用于测量队列二任务总数的值
    图层: 一个已经排序的列表，包含了 svg 格式的临摹图层文件
    设置: 一个字典，包含以下的键：
        colors, quantization, dither, remap, prescale, tmp
        See color_trace_multi for details of the values
    输入索引: 输入文件的整数索引 findex
    输入: 输入 png 文件
    输出: 输出 svg 路径
"""
    # 如果输出目录不存在，则创建
    目标文件夹 = os.path.dirname(os.path.abspath(输出))
    if not os.path.exists(目标文件夹):
        os.makedirs(目标文件夹)

    # 临时文件会放置在各个输出文件的旁边
    缩放文件 = os.path.abspath(os.path.join(设置['tmp'], '{0}~scaled.png'.format(输入索引)))
    减色文件 = os.path.abspath(os.path.join(设置['tmp'], '{0}~reduced.png'.format(输入索引)))

    try:
        # 如果跳过了量化，则必须使用不会增加颜色数量的缩放方法
        if 设置['colors'] == 0:
            滤镜 = 'point'
        else:
            滤镜 = 'lanczos'
        重缩放(输入, 缩放文件, 设置['prescale'], 滤镜=滤镜)

        if 设置['colors'] is not None:
            量化(缩放文件, 减色文件, 设置['colors'], 算法=设置['quantization'], 拟色=设置['dither'])
        elif 设置['remap'] is not None:
            调色板重映射(缩放文件, 减色文件, 设置['remap'], 拟色=设置['dither'])
        else:
            # argparse 应该已经抛出这个错误
            raise Exception("至少应该设置 'colors' 、 'remap' 中最少一个参数")
        调色板 = 制作调色板(减色文件)

        # 基于调色板中颜色的数量更新总数
        if 设置['colors'] is not None:
            总数.value -= 设置['colors'] - len(调色板)
        else:
            总数.value -= 设置['palettesize'] - len(调色板)
        # 初始化输入索引所指文件的图层
        图层[输入索引] += [False] * len(调色板)

        # 得到图像宽度
        宽度 = 得到宽度(输入)

        # 添加任务到第二个任务队列
        for i, 颜色 in enumerate(调色板):
            队列2.put(
                {'width': 宽度, 'color': 颜色, 'palette': 调色板, 'reduced': 减色文件, 'output': 输出, 'findex': 输入索引, 'cindex': i})

    except (Exception, KeyboardInterrupt) as e:
        # 发生错误时删除临时文件
        删除文件(缩放文件, 减色文件)
        raise e
    else:
        # 描摹后删除文件
        删除文件(缩放文件)


def 队列2_任务(图层, 图层锁, 设置, 宽度, 颜色, 调色板, 文件索引, 颜色索引, 已缩减图像, 输出路径):
    """ 分离颜色并描摹

    图层: 一个有序列表，包含了 svg 文件的临摹图层
    图层锁: 读取和写入图层对象时必须获取的锁
    设置: 一个字典，必须有以下键值:
        stack, despeckle, smoothcorners, optimizepaths, tmp
        See color_trace_multi for details of the values
    宽度: 输入图像的宽度
    颜色: 要孤立的颜色
    文件索引: 输入文件的整数索引
    颜色索引: 颜色的整数索引
    已缩减图像: 已经缩减颜色的输入图像
    输出路径: 输出路径，svg 文件
"""
    # 临时文件放在每个输出文件的旁边
    该文件孤立颜色图像 = os.path.abspath(os.path.join(设置['tmp'], '{0}-{1}~isolated.png'.format(文件索引, 颜色索引)))
    该文件图层 = os.path.abspath(os.path.join(设置['tmp'], '{0}-{1}~layer.ppm'.format(文件索引, 颜色索引)))
    描摹格式 = '{0}-{1}~trace.svg'
    描摹文件 = os.path.abspath(os.path.join(设置['tmp'], 描摹格式.format(文件索引, 颜色索引)))

    try:
        # 如果颜色索引是 0 并且 -bg 选项被激活
        # 直接用匹配的颜色填充图像，否则使用孤立颜色
        if 颜色索引 == 0 and 设置['background']:
            汇报("Index {}".format(颜色))
            使用颜色填充(已缩减图像, 该文件图层)
        else:
            孤立颜色(已缩减图像, 该文件孤立颜色图像, 该文件图层, 颜色, 调色板, stack=设置['stack'])
        # 描摹这个颜色，添加到 svg 栈
        描摹(该文件图层, 描摹文件, 颜色, 设置['despeckle'], 设置['smoothcorners'], 设置['optimizepaths'], 宽度)
    except (Exception, KeyboardInterrupt) as e:
        # 若出错，则先删掉临时文件
        删除文件(已缩减图像, 该文件孤立颜色图像, 该文件图层, 描摹文件)
        raise e
    else:
        # 完成任务后删除临时文件
        删除文件(该文件孤立颜色图像, 该文件图层)

    图层锁.acquire()
    try:
        # 添加图层
        图层[文件索引][颜色索引] = True

        # 检查这个文件所有的图层是否都被临摹了
        是最后一个 = False not in 图层[文件索引]
    finally:
        图层锁.release()

    # 如果已经就绪，则保存 svg 文档
    if 是最后一个:
        # 开始 svg 堆栈
        布局 = svg_stack.CBoxLayout()

        临摹图层 = [os.path.abspath(os.path.join(设置['tmp'], 描摹格式.format(文件索引, l))) for l in range(len(图层[文件索引]))]

        # 添加图层到 svg
        for t in 临摹图层:
            布局.addSVG(t)

        # 保存堆栈好的 svg 输出
        文档 = svg_stack.Document()
        文档.setLayout(布局)
        with open(输出路径, 'w') as 文件:
            文档.save(文件)

        删除文件(已缩减图像, *临摹图层)


def 进程处理(第一个任务队列, 第二个任务队列, 已完成任务数, 任务总数, 图层, 图层锁, 设置):
    """ 处理 process 任务的函数

    q1: 第一个任务队列 (缩放 + 颜色缩减)
    q2: 第二个任务队列 (颜色隔离 + 描摹)
    progress: 第二个队列已完成任务数
    total: 第二个队列总任务数
    layers: 一个嵌套列表， layers[file_index][color_index] 是一个布尔值，
            表示 file_index 所指文件的 color_index 所指颜色的图层是否已经被描摹
    layers_lock: 读取和写入第二个任务队列中图层对象时的锁
    settings: 一个字典，必须包含下述键值:
        quantization, dither, remap, stack, prescale, despeckle, smoothcorners,
        optimizepaths, colors, tmp
        See color_trace_multi for details of the values
"""
    while True:
        # 在第一个任务队列之前，从第二个人队列取一个工作，以节省临时文件和内存
        while not 第二个任务队列.empty():
            try:
                工作参数 = 第二个任务队列.get(block=False)
                队列2_任务(图层, 图层锁, 设置, **工作参数)
                第二个任务队列.task_done()
                已完成任务数.value += 1
            except queue.Empty:
                break

        # 自第二个任务队列为空后，从第一个任务队列获取工作
        try:
            工作参数 = 第一个任务队列.get(block=False)

            队列1_任务(第二个任务队列, 任务总数, 图层, 设置, **工作参数)
            第一个任务队列.task_done()
        except queue.Empty:
            time.sleep(.01)

        if 第二个任务队列.empty() and 第一个任务队列.empty():
            break


def 彩色描摹(输入列表, 输出列表, 颜色数, 进程数, quantization='mc', 拟色=None,
         remap=None, stack=False, prescale=2, despeckle=2, smoothcorners=1.0, optimizepaths=0.2, background=False):
    """用指定选项彩色描摹输入图片

    输入列表: 输入文件列表，源 png 文件
    输出列表: 输出文件列表，目标 svg 文件
    颜色数: 要亮化缩减到的颜色质量，0 表示不量化
    进程数: 图像处理进程数
    量化算法: 要使用的量化算法:
        - 'mc' = median-cut 中切 (默认值, 只有少量颜色, 使用 pngquant)
        - 'as' = adaptive spatial subdivision 自适应空间细分 (使用 imagemagick, 产生的颜色更少)
        - 'nq' = neuquant (生成许多颜色, 使用 pngnq)
    拟色: 量化时使用的抖动拟色算法 (提醒，最后的输出结果受 despeckle 影响)
        None: 默认，不拟色
        'floydsteinberg': 当使用 'mc', 'as', 和 'nq' 时可用
        'riemersma': 只有使用 'as' 时可用
    调色板：用于颜色缩减的自定义调色板图像的源（覆盖颜色数和量化）
    堆栈: 是否堆栈彩色描摹 (可以得到更精确的输出)
    抑制斑点像素数: 抑制指定像素数量的斑点
    平滑转角: 平滑转角: 0 表示不平滑, 1.334 为最大
        (等同于 potrace --alphamax)
    优化路径: 贝塞尔曲线优化: 0 最小, 5 最大
        (等同于 potrace --opttolerance)
    背景：设置第一个颜色为整个 svg 背景，以减小 svg 体积
"""
    临时文件 = tempfile.mkdtemp()

    # 新建两个任务队列
    # 第一个任务队列 = 缩放和颜色缩减
    第一个任务队列 = multiprocessing.JoinableQueue()
    # 第二个任务队列 = 颜色分离和描摹
    第二个任务队列 = multiprocessing.JoinableQueue()

    # 创建一个管理器，在两个进程时间共享图层
    管理器 = multiprocessing.Manager()
    图层 = []
    for i in range(min(len(输入列表), len(输出列表))):
        图层.append(管理器.list())
    # 创建一个读取和修改图层的锁
    图层锁 = multiprocessing.Lock()

    # 创建一个共享内存计数器，表示任务总数和已完成任务数
    已完成任务数 = multiprocessing.Value('i', 0)
    if 颜色数 is not None:
        # 这只是一个估计值，因为量化可能会生成更少的颜色
        # 该值由第一个任务队列校正以收敛于实际总数
        总任务数 = multiprocessing.Value('i', len(图层) * 颜色数)
    elif 重映射 is not None:
        # 得到调色板图像的银色数量
        调色板大小 = len(制作调色板(重映射))
        # this is only an estimate because remapping can result in less colors
        # than in the remap variable. This value is corrected by q1 tasks to converge
        # on the real total.
        # 这只是一个估计值，因为量化可能会生成更少的颜色
        # 该值由第一个任务队列校正以收敛于实际总数
        总任务数 = multiprocessing.Value('i', len(图层) * 调色板大小)
    else:
        # argparse 应当已经提前捕获这个错误
        raise Exception("应当提供 'colors' 和 'remap' 至少一个参数")

    # 创建和开始进程
    进程列表 = []
    for i in range(进程数):
        进程 = multiprocessing.Process(target=进程处理, args=(第一个任务队列, 第二个任务队列, 已完成任务数, 总任务数, 图层, 图层锁, locals()))
        进程.name = "color_trace worker #" + str(i)
        进程.start()
        进程列表.append(进程)

    try:
        # 对每个收入和相应的输出
        for 索引, (输入, 输出) in enumerate(zip(输入列表, 输出列表)):
            汇报(输入, ' -> ', 输出)

            # add a job to the first job queue
            第一个任务队列.put({'input': 输入, 'output': 输出, 'findex': 索引})

        # show progress until all jobs have been completed
        while 已完成任务数.value < 总任务数.value:
            sys.stdout.write("\r%.1f%%" % (已完成任务数.value / 总任务数.value * 100))
            sys.stdout.flush()
            time.sleep(0.25)

        sys.stdout.write("\rTracing complete!\n")

        # join the queues just in case progress is wrong
        第一个任务队列.join()
        第二个任务队列.join()
    except (Exception, KeyboardInterrupt) as e:
        # shut down subproesses
        for 进程 in 进程列表:
            进程.terminate()
        shutil.rmtree(临时文件)
        raise e

    # close all processes
    for 进程 in 进程列表:
        进程.terminate()
    shutil.rmtree(临时文件)


def 删除文件(*filepaths):
    """如果文件存在则删除"""
    for f in filepaths:
        if os.path.exists(f):
            os.remove(f)


def main(参数=None):
    """main function to collect arguments and run color_trace_multi

    args: if specified, a Namespace of arguments (see argparse) to use instead
        of those supplied to this script at the command line
"""
    if 参数 is None:
        参数 = 获得参数()

    # set verbosity level
    if 参数.verbose:
        global 日志级别
        日志级别 = 1

    # set output filename pattern depending on --output argument
    if 参数.output is None:
        输出形式 = "{0}.svg"
    elif '*' in 参数.output:
        输出形式 = 参数.output.replace('*', "{0}")
    else:
        输出形式 = 参数.output

    # --directory: add dir to output paths
    if 参数.directory is not None:
        目标文件夹 = 参数.directory.strip('\"\'')
        输出形式 = os.path.join(目标文件夹, 输出形式)

    # 如果没有指定的话，设置进程数
    if 参数.cores is None:
        try:
            进程数 = multiprocessing.cpu_count()
        except NotImplementedError:
            汇报("Could not determine total number of cores, assuming 1")
            进程数 = 1
    else:
        进程数 = 参数.cores

    # collect only those arguments needed for color_trace_multi
    输入输出 = zip(*得到输入输出(参数.input, 输出形式))
    try:
        输入列表, 输出列表 = 输入输出
    except ValueError:  # nothing to unpack
        输入列表, 输出列表 = [], []
    if 参数.floydsteinberg:
        拟色 = 'floydsteinberg'
    elif 参数.riemersma:
        拟色 = 'riemersma'
    else:
        拟色 = None
    颜色数 = 参数.colors
    彩色描摹参数 = vars(参数)
    for k in ('colors', 'directory', 'input', 'output', 'cores', 'floydsteinberg', 'riemersma', 'verbose'):
        彩色描摹参数.pop(k)

    彩色描摹(输入列表, 输出列表, 颜色数, 进程数, 拟色=拟色, **彩色描摹参数)

if __name__ == '__main__':
    main()
