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


命令行最长 = 1900  # 命令行长度限制
汇报级别 = 0  # 不止是一个常数，它也会爱 -v/--verbose 选项影响

版本 = '1.01'

import os, sys
import shutil
import subprocess
import argparse
from glob import iglob
import functools
import multiprocessing
import queue
import tempfile
import time
import shlex
import re
from pprint import pprint


from .svg_stack import svg_stack
from .foreign import cli_pngnq, cli_potrace, cli_imagemagick, cli_pngquant
from .exception import *

def 汇报(*args, level=1):
    global 汇报级别
    if 汇报级别 >= level:
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
    stdin_pipe = (subprocess.PIPE if stdinput is not None else None)
    stdout_pipe = (subprocess.PIPE if stdout_ is True else None)
    stderr_pipe = subprocess.PIPE

    汇报(f'命令：{命令}')
    进程 = subprocess.Popen(shlex.split(命令),
                          stdin=stdin_pipe,
                          stderr=stderr_pipe,
                          stdout=stdout_pipe,
                          shell=True)

    stdoutput, stderror = 进程.communicate(input=stdinput)

    # 10 分钟不结束就报错，免得一直卡住
    返回码 = 进程.wait(timeout=600)
    if 返回码 != 0:
        raise Exception(stderror.decode(encoding=sys.getfilesystemencoding()))

    if stdout_ and not stderr_:
        return stdoutput
    elif stderr_ and not stdout_:
        return stderror
    elif stdout_ and stderr_:
        return (stdoutput, stderror)
    elif not stdout_ and not stderr_:
        return None


def 重缩放(源, 目标, 缩放, 滤镜='lanczos'):
    """使用 ImageMagick 将图片重新缩放、转为 png 格式
"""
    if 缩放 == 1.0:  # 不缩放。检查格式
        if os.path.splitext(源)[1].lower() not in ['.png']: # 非 png 则转格式
            命令 = f'{cli_imagemagick} convert "{源}" "{目标}"'
            处理命令(命令)
        else: # png 格式则直接复制
            shutil.copyfile(源, 目标)
    else:
        命令 = f'{cli_imagemagick} convert "{源}" -filter {滤镜} -resize {缩放 * 100}% "{目标}"'
        处理命令(命令)

def 量化缩减图片颜色(源, 量化目标, 颜色数, 算法='mc', 拟色=None):
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

    if 颜色数 in [0, 1]:
        # 跳过量化，直接复制输入到输出
        shutil.copyfile(源, 量化目标)

    elif 算法 == 'mc':  # median-cut 中切
        if 拟色 is None:
            拟色选项 = '--nofs'
        elif 拟色 == 'floydsteinberg':
            拟色选项 = ''
        else:
            raise ColorTraceForeignCallError(f"(pngquant): 对 'mc' 量化方法使用了错误的拟色类型: {拟色!r}")
        # 因为 pngquant 不能保存到中文路径，所以使用 stdin/stdout 操作 pngquant
        命令 = f'{cli_pngquant} --force {拟色选项} {颜色数} - < "{源}" > "{量化目标}"'
        stdoutput = 处理命令(命令)

    elif 算法 == 'as':  # adaptive spatial subdivision 自适应空间细分
        if 拟色 is None:
            拟色选项 = 'None'
        elif 拟色 in ('floydsteinberg', 'riemersma'):
            拟色选项 = 拟色
        else:
            raise ColorTraceForeignCallError(f"(imagemagick): 对 'as' 量化方法使用了错误的拟色类型 {拟色!r}")
        命令 = f'{cli_imagemagick} convert "{源}" -dither {拟色选项} -colors {颜色数} "{量化目标}"'
        处理命令(命令)

    elif 算法 == 'nq':  # neuquant
        ext = "~quant.png"
        destdir = os.path.dirname(量化目标)
        if 拟色 is None:
            拟色选项 = ''
        elif 拟色 == 'floydsteinberg':
            拟色选项 = '-Q f '
        else:
            raise ColorTraceForeignCallError(f"(imagemagick): 对 'nq' 量化方法使用了错误的拟色类型 {拟色!r}")
        命令 = f'"{cli_pngnq}" -f {拟色选项} -d "{destdir}" -n {颜色数} -e {ext} "{源}"'
        处理命令(命令)
        # 因为 pngnq 不支持保存到自定义目录，所以先输出文件到当前目录，再移动到量化目标
        旧输出 = os.path.join(destdir, os.path.splitext(os.path.basename(源))[0] + ext)
        os.rename(旧输出, 量化目标)
    else:
        # 在错误到达这里前 argparse 应该已经先捕捉到了
        raise NotImplementedError(f'未知的量化算法 {算法!r}')


def 用调色板对图片重映射(源, 重映射目标, 调色板图像, 拟色=None):
    """用调色板图像的颜色重映射源图像，保存到重映射目标

    源: 源图像路径
    重映射目标: 输出保存路径
    调色板图像: 一个图像路径，它包含了 src 将重映射的颜色
    拟色: 重映射时的拟色算法
        选项有：None, 'floydsteinberg', 和 'riemersma'
"""

    if not os.path.exists(调色板图像):  # 确认下调色板图像存在
        raise IOError(f"未找到重映射调色板：{调色板图像} ")

    if 拟色 is None:
        拟色选项 = 'None'
    elif 拟色 in ('floydsteinberg', 'riemersma'):
        拟色选项 = 拟色
    else:
        raise ColorTraceForeignCallError(f"(imagemagick): 不合理的重映射拟色类型: {拟色!r}")

    # magick convert "src.png" -dither None -remap "platte.png" "output.png"
    命令 = f'{cli_imagemagick} convert "{源}" -dither {拟色选项} -remap "{调色板图像}" "{重映射目标}"'
    处理命令(命令)



def 制作颜色表(源图像):
    """从源图像得到特征色，返回 #rrggbb 16进制颜色"""

    命令 = f'{cli_imagemagick} convert "{源图像}"  -unique-colors txt:-'
    stdoutput = 处理命令(命令, stdout_=True) # 这个输出中包含了颜色

    正则模式 = '#[0-9A-F]{6}'
    IM输出 = stdoutput.decode(sys.getfilesystemencoding())
    十六进制颜色 = re.findall(正则模式, IM输出)

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
        颜色 = f"#{i:06x}"
        if 颜色 not in 最终调色板:
            return 颜色
    # 当调色板加上规避颜色，包含所有颜色 #000000-#ffffff 时，抛出错误
    raise ColorTraceError("未能找到调色板之外的颜色")


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
    命令前缀 = f'{cli_imagemagick} convert "{源}" '
    命令后缀 = f' "{目标临时文件}"'
    命令中间 = ''

    for i, 颜色 in enumerate(调色板):
        # fill this color with background or foreground?
        if i == 颜色索引:
            填充色 = 前景接近黑
        elif i > 颜色索引 and stack:
            填充色 = 前景接近黑
        else:
            填充色 = 背景接近白

        命令中间 += f' -fill "{填充色}" -opaque "{颜色}"'
        if len(命令中间) >= 命令行最长 or (i == last_iteration and 命令中间):
            命令 = 命令前缀 + 命令中间 + 命令后缀

            stdoutput = 处理命令(命令, stdinput=stdinput, stdout_=True)
            stdinput = stdoutput
            命令中间 = ''  # reset

    # 现在将前景变黑，背景变白
    命令 = f'{cli_imagemagick} convert "{目标临时文件}" -fill "{背景白}" -opaque "{背景接近白}" -fill "{前景黑}" -opaque "{前景接近黑}" "{目标图层}"'
    处理命令(命令, stdinput=stdinput)


def 使用颜色填充(源, 目标):
    命令 = f'{cli_imagemagick} convert "{源}" -fill "#000000" +opaque none "{目标}"'
    处理命令(命令)


def 得到宽度(源):
    """返回头像宽多少像素"""
    命令 = f'{cli_imagemagick} identify -ping -format "%w" "{源}"'
    stdoutput = 处理命令(命令, stdout_=True)
    宽 = int(stdoutput)
    return 宽


def 描摹(源, 描摹目标, 输出颜色, 抑制斑点像素数=2, 平滑转角=1.0, 优化路径=0.2, 宽度=None, 高度=None, 分辨率=None):
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

    宽度参数 = f'--width {宽度}' if 宽度 is not None else ''
    高度参数 = f'--height {高度}' if 高度 is not None else ''
    分辨率参数 = f'--resolution {分辨率}' if 分辨率 is not None else ''

    命令 = f'''{cli_potrace} --svg -o "{描摹目标}" -C "{输出颜色}" -t {抑制斑点像素数} -a {平滑转角} -O {优化路径}
                {宽度参数} {高度参数} {分辨率参数} "{源}"'''
    汇报(命令)

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
        msg = f"must be {typename}"
        raise argparse.ArgumentTypeError(msg)
    if (max is not None) and (not min <= val <= max):
        msg = f"must be between {min} and {max}"
        raise argparse.ArgumentTypeError(msg)
    elif not min <= val:
        msg = f"must be {min} or greater"
        raise argparse.ArgumentTypeError(msg)
    return val



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


def 队列1_任务(队列2, 总数, 图层, 设置, findex, 输入文件, output):
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
    目标文件夹 = os.path.dirname(os.path.abspath(output))
    if not os.path.exists(目标文件夹):
        os.makedirs(目标文件夹)

    # 临时文件会放置在各个输出文件的旁边
    缩放文件 = os.path.abspath(os.path.join(设置['临时文件'], f'{findex}~scaled.png'))
    减色文件 = os.path.abspath(os.path.join(设置['临时文件'], f'{findex}~reduced.png'))

    try:
        # 如果跳过了量化，则必须使用不会增加颜色数量的缩放方法
        if 设置['颜色数'] == 0:
            滤镜 = 'point'
        else:
            滤镜 = 'lanczos'
        重缩放(输入文件, 缩放文件, 设置['prescale'], 滤镜=滤镜)


        if 设置['颜色数'] is not None: # 如果设置了颜色数量，就将原图缩减颜色
            量化缩减图片颜色(缩放文件, 减色文件, 设置['颜色数'], 算法=设置['quantization'], 拟色=设置['拟色'])
        elif 设置['remap'] is not None: # 如果设置了调色板图片，就将原图按调色板进行重映射
            用调色板对图片重映射(缩放文件, 减色文件, 设置['remap'], 拟色=设置['拟色'])
        else:
            # argparse 应该已经抛出这个错误
            raise Exception("至少应该设置 'colors' 、 'remap' 中最少一个参数")
        if 设置['颜色数'] == 1:
            颜色表 = ['#000000']
        else:
            颜色表 = 制作颜色表(减色文件)

        # 基于调色板中颜色的数量更新总数
        if 设置['颜色数'] is not None:
            总数.value -= 设置['颜色数'] - len(颜色表)
        else:
            总数.value -= 设置['调色板颜色数'] - len(颜色表)
        # 初始化输入索引所指文件的图层
        图层[findex] += [False] * len(颜色表)

        # 得到图像宽度
        # 优先使用用户设置的宽度，如果没设置，那就去获得原来的宽度
        宽度 = 设置['width'] if 设置['width'] else f'{得到宽度(输入文件)}pt'
        高度 = 设置['height']
        分辨率 = 设置['resolution']


        # 添加任务到第二个任务队列
        for i, 颜色 in enumerate(颜色表):
            队列2.put(
                {'宽度': 宽度,
                 '高度': 高度,
                 '分辨率': 分辨率,
                 '颜色': 颜色,
                 '调色板': 颜色表,
                 '已缩减图像': 减色文件,
                 '输出路径': output,
                 '文件索引': findex,
                 '颜色索引': i})

    except (Exception, KeyboardInterrupt) as e:
        # 发生错误时删除临时文件
        # 删除文件(缩放文件, 减色文件)
        raise e
    else:
        # 描摹后删除文件
        删除文件(缩放文件)


def 队列2_任务(图层, 图层锁, 设置, 宽度, 高度, 分辨率, 颜色, 调色板, 文件索引, 颜色索引, 已缩减图像, 输出路径):
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
    该文件孤立颜色图像 = os.path.abspath(os.path.join(设置['临时文件'], f'{文件索引}-{颜色索引}~isolated.png'))
    该文件图层 = os.path.abspath(os.path.join(设置['临时文件'], f'{文件索引}-{颜色索引}~layer.ppm'))
    描摹格式 = '{0}-{1}~trace.svg'
    描摹文件 = os.path.abspath(os.path.join(设置['临时文件'], f'{文件索引}-{颜色索引}~trace.svg'))

    try:
        # 如果颜色索引是 0 并且 -bg 选项被激活
        # 直接用匹配的颜色填充图像，否则使用孤立颜色
        if 颜色索引 == 0 and 设置['background']:
            汇报(f"Index {颜色}")
            使用颜色填充(已缩减图像, 该文件图层)
        else:
            孤立颜色(已缩减图像, 该文件孤立颜色图像, 该文件图层, 颜色, 调色板, stack=设置['stack'])
        # 描摹这个颜色，添加到 svg 栈
        描摹(该文件图层, 描摹文件, 颜色, 设置['despeckle'], 设置['smoothcorners'], 设置['optimizepaths'], 宽度, 高度, 分辨率)
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

        临摹图层 = [os.path.abspath(os.path.join(设置['临时文件'], 描摹格式.format(文件索引, l))) for l in range(len(图层[文件索引]))]

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
         remap=None, stack=False, prescale=2, despeckle=2, smoothcorners=1.0,
         optimizepaths=0.2, background=False,
         width=None, height=None, resolution=None):
    """用指定选项彩色描摹输入图片

    输入列表: 输入文件列表，源 png 文件
    输出列表: 输出文件列表，目标 svg 文件
    颜色数: 要亮化缩减到的颜色质量，0 表示不量化
    进程数: 图像处理进程数
    quantization: 要使用的量化算法:
        - 'mc' = median-cut 中切 (默认值, 只有少量颜色, 使用 pngquant)
        - 'as' = adaptive spatial subdivision 自适应空间细分 (使用 imagemagick, 产生的颜色更少)
        - 'nq' = neuquant (生成许多颜色, 使用 pngnq)
    拟色: 量化时使用的抖动拟色算法 (提醒，最后的输出结果受 despeckle 影响)
        None: 默认，不拟色
        'floydsteinberg': 当使用 'mc', 'as', 和 'nq' 时可用
        'riemersma': 只有使用 'as' 时可用
    remap：用于颜色缩减的自定义调色板图像的源（覆盖颜色数和量化）
    stack: 是否堆栈彩色描摹 (可以得到更精确的输出)
    despeckle: 抑制指定像素数量的斑点
    smoothcorners: 平滑转角: 0 表示不平滑, 1.334 为最大
        (等同于 potrace --alphamax)
    optimizepaths: 贝塞尔曲线优化: 0 最小, 5 最大
        (等同于 potrace --opttolerance)
    background：设置第一个颜色为整个 svg 背景，以减小 svg 体积
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
    elif remap is not None:
        # 得到调色板图像的银色数量
        调色板颜色数 = len(制作颜色表(remap))
        # this is only an estimate because remapping can result in less colors
        # than in the remap variable. This value is corrected by q1 tasks to converge
        # on the real total.
        # 这只是一个估计值，因为量化可能会生成更少的颜色
        # 该值由第一个任务队列校正以收敛于实际总数
        总任务数 = multiprocessing.Value('i', len(图层) * 调色板颜色数)
    else:
        # argparse 应当已经提前捕获这个错误
        raise Exception("应当提供 'colors' 和 'remap' 至少一个参数")

    # 创建和开始进程
    进程列表 = []
    for i in range(进程数):

        本地 = locals()
        本地.pop('图层')
        本地.pop('图层锁')
        本地.pop('已完成任务数')
        本地.pop('总任务数')
        本地.pop('第一个任务队列')
        本地.pop('第二个任务队列')
        本地.pop('管理器')
        本地['本地'] = None
        本地['进程'] = None
        本地['进程列表'] = None

        进程 = multiprocessing.Process(target=进程处理, args=(第一个任务队列, 第二个任务队列, 已完成任务数, 总任务数, 图层, 图层锁, 本地))
        进程.name = "color_trace worker #" + str(i)
        进程.start()
        进程列表.append(进程)

    try:
        # 对每个收入和相应的输出
        for 索引, (输入, 输出) in enumerate(zip(输入列表, 输出列表)):
            汇报(输入, ' -> ', 输出)

            # add a job to the first job queue
            第一个任务队列.put({'输入文件': 输入, 'output': 输出, 'findex': 索引})

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


def 获得参数(cmdargs=None):
    """返回从命令行得到的参数

    cmdargs: 如果指定了，则使用这些参数，而不使用提供的脚本的参数
"""
    parser = argparse.ArgumentParser(description="使用 potrace 将位图转化为彩色 svg 矢量图",
                                     add_help=False, prefix_chars='-/')
    # 也可以通过 /? 获得帮助
    parser.add_argument(
        '-h', '--help', '/?',
        action='help',
        help="显示帮助")
    # 文件输入输出参数
    parser.add_argument('-i',
                        '--input', metavar='src', nargs='+', required=True,
                        help="输入文件，支持 * 和 ? 通配符")
    parser.add_argument('-o',
                        '--output', metavar='dest',
                        help="输出保存路径，支持 * 通配符")
    parser.add_argument('-d',
                        '--directory', metavar='destdir',
                        help="输出保存的文件夹")
    # 处理参数
    parser.add_argument('-C',
                        '--cores', metavar='N',
                        type=functools.partial(检查范围, 0, None, int, "an integer"),
                        help="多进程处理的进程数 (默认使用全部核心)")
    # 尺寸参数
    parser.add_argument('--width', metavar='<dim>',
                        help="输出 svg 图像宽度，例如：6.5in、 15cm、100pt，默认单位是 inch")
    parser.add_argument('--height', metavar='<dim>',
                        help="输出 svg 图像高度，例如：6.5in、 15cm、100pt，默认单位是 inch")
    # parser.add_argument('--resolution', metavar='resolution', default='72',
    #                     help="输出 svg 图像分辨率，单位 dpi，例如：300、 300x150。默认值：72")
    # svg 文件似乎没有 dpi 概念

    # 彩色描摹选项
    # 颜色数和调色板互斥
    颜色数调色板组 = parser.add_mutually_exclusive_group(required=True)
    颜色数调色板组.add_argument('-c',
                                     '--colors', metavar='N',
                                     type=functools.partial(检查范围, 0, 256, int, "an integer"),
                                     help="[若未使用 -p 参数，则必须指定该参数] "
                                          "表示在描摹前，先缩减到多少个颜色。最多 256 个。"
                                          "0表示跳过缩减颜色 (除非你的图片已经缩减过颜色，否则不推荐0)。")
    parser.add_argument('-q',
                        '--quantization', metavar='algorithm',
                        choices=('mc', 'as', 'nq'), default='mc',
                        help="颜色量化算法，即缩减颜色算法: mc, as, or nq. "
                             "'mc' (Median-Cut，中切，由 pngquant 实现，产生较少的颜色，这是默认); "
                             "'as' (Adaptive Spatial Subdivision 自适应空间细分，由 ImageMagick 实现，产生的颜色更少); "
                             "'nq' (NeuQuant 神经量化, 可以生成更多的颜色，由 pnqng 实现)。 如果 --colors 0 则不启用量化。")


    # make --floydsteinberg and --riemersma dithering mutually exclusive
    dither_group = parser.add_mutually_exclusive_group()
    dither_group.add_argument('-fs',
                              '--floydsteinberg', action='store_true',
                              help="启用 Floyd-Steinberg 拟色 (适用于所有量化算法或 -p/--palette)."
                                   "警告: 任何米色算法都会显著的增加输出 svg 图片的大小和复杂度")
    dither_group.add_argument('-ri',
                              '--riemersma', action='store_true',
                              help="启用 Rimersa 拟色 (只适用于 as 量化算法或 -p/--palette)")
    颜色数调色板组.add_argument('-r',
                                     '--remap', metavar='paletteimg',
                                     help=("使用一个自定义调色板图像，用于颜色缩减 [覆盖 -c 和 -q 选项]"))
    # image options
    parser.add_argument('-s',
                        '--stack',
                        action='store_true',
                        help="堆栈描摹 (若要更精确的输出，推荐用这个)")
    parser.add_argument('-p',
                        '--prescale', metavar='size',
                        type=functools.partial(检查范围, 0, None, float, "a floating-point number"), default=1,
                        help="为得到更多的细节，在描摹前，先将图片进行缩放 (默认值: 1)。"
                             "例如使用 2，描摹前先预放大两倍")
    # potrace options
    parser.add_argument('-D',
                        '--despeckle', metavar='size',
                        type=functools.partial(检查范围, 0, None, int, "an integer"), default=2,
                        help='抑制斑点的大小（单位是像素） (默认值：2)')
    parser.add_argument('-S',
                        '--smoothcorners', metavar='threshold',
                        type=functools.partial(检查范围, 0, 1.334, float, "a floating-point number"), default=1.0,
                        help="转角平滑参数：0 表示不作平滑处理，1.334 是最大。（默认值：1.0")
    parser.add_argument('-O',
                        '--optimizepaths', metavar='tolerance',
                        type=functools.partial(检查范围, 0, 5, float, "a floating-point number"), default=0.2,
                        help="贝塞尔曲线优化参数: 最小是0，最大是5"
                             "(默认值：0.2)")
    parser.add_argument('-bg',
                        '--background', action='store_true',
                        help=("将第一个颜色这背景色，并尽可能优化最终的 svg"))
    # other options
    parser.add_argument('-v',
                        '--verbose', action='store_true',
                        help="打印出运行时的细节")
    parser.add_argument('--version', action='version',
                        version='%(prog)s {ver}'.format(ver=版本), help='显示程序版本')

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


def main(参数=None):
    """收集参数和运行描摹"""

    if 参数 is None:
        参数 = 获得参数()

    # 设置汇报级别
    if 参数.verbose:
        global 汇报级别
        汇报级别 = 1

    # 设置输出文件名形式
    if 参数.output is None:
        输出形式 = "{0}.svg"
    elif '*' in 参数.output:
        输出形式 = 参数.output.replace('*', "{0}")
    else:
        输出形式 = 参数.output

    # --directory: 添加输出文件加路径
    if 参数.directory is not None:
        目标文件夹 = 参数.directory.strip('\"\'')
        输出形式 = os.path.join(目标文件夹, 输出形式)

    # 如果参数没有指定的话，设置进程数
    if 参数.cores is None:
        try:
            进程数 = multiprocessing.cpu_count()
        except NotImplementedError:
            汇报("无法确定CPU核心数，因此假定为 1")
            进程数 = 1
    else:
        进程数 = 参数.cores

    # 只收集彩色描摹需要的参数
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
