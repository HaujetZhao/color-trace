#!/usr/bin/env python
"""trace multiple color images with potrace"""

# color_trace_multi
# Written by ukurereh
# May 20, 2012

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


# External program commands. Replace with paths to external programs as needed.
PNGQUANT_PATH               = 'pngquant'
PNGNQ_PATH                  = 'pngnq'
IMAGEMAGICK_CONVERT_PATH    = 'convert'
IMAGEMAGICK_IDENTIFY_PATH   = 'identify'
POTRACE_PATH                = 'potrace'

POTRACE_DPI = 90.0 # potrace docs say it's 72, but this seems to work best
COMMAND_LEN_NEAR_MAX = 1900 # a low approximate (but not maximum) limit for
                            # very large command-line commands
VERBOSITY_LEVEL = 0 # not just a constant, also affected by -v/--verbose option

VERSION = '1.00'

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


def verbose(*args, level=1):
    if VERBOSITY_LEVEL >= level:
        print(*args)


def process_command(command, stdinput=None, stdout_=False, stderr_=False):
    """run command in invisible shell, return stdout and/or stderr as specified

    Returns stdout, stderr, or a tuple (stdout, stderr) depending on which of
    stdout_ and stderr_ is True. Raises an exception if the command encounters
    an error.

    command: command with arguments to send to command line
    stdinput: data (bytes) to send to command's stdin, or None
    stdout_: True to receive command's stdout in the return value
    stderr_: True to receive command's stderr in the return value
"""
    verbose(command)
    stdin_pipe   = (subprocess.PIPE if stdinput  is not None else None)
    stdout_pipe  = (subprocess.PIPE if stdout_ is True else None)
    stderr_pipe  = subprocess.PIPE

    #process = subprocess.Popen(command, stdin=stdin_pipe, stderr=stderr_pipe, stdout=stdout_pipe,
        #shell=True, creationflags=subprocess.SW_HIDE)
    process = subprocess.Popen(command, stdin=stdin_pipe, stderr=stderr_pipe, stdout=stdout_pipe,
        shell=True)

    stdoutput, stderror = process.communicate(stdinput)
    #print(stderror)
    returncode = process.wait()
    if returncode != 0:
        Exception(stderror.decode())
    if stdout_ and not stderr_:
        return stdoutput
    elif stderr_ and not stdout_:
        return stderr
    elif stdout_ and stderr_:
        return (stdoutput, stderror)
    elif not stdout_ and not stderr_:
        return None


def rescale(src, destscale, scale, filter='lanczos'):
    """rescale src image to scale, save to destscale

    full list of filters is available from ImageMagick's documentation.
"""
    if scale == 1.0: #just copy it over
        shutil.copyfile(src, destscale)
    else:
        command = '"{convert}" "{src}" -filter {filter} -resize {resize}% "{dest}"'.format(
            convert=IMAGEMAGICK_CONVERT_PATH, src=src, filter=filter, resize=scale*100,
            dest=destscale)
        process_command(command)


def quantize(src, destquant, colors, algorithm='mc', dither=None):

    """quantize src image to colors, save to destquant

    Uses chosen algorithm to quantize src image.
    src: path of source image, must be png
    destquant: path to save output quantized png image
    colors: number of colors to quantize to, 0 for no quantization
    algorithm: color quantization algorithm to use:
        - 'mc' = median-cut (default, for few colors, uses pngquant)
        - 'as' = adaptive spatial subdivision (uses imagemagick, may result in fewer colors)
        - 'nq' = neuquant (for lots of colors, uses pngnq)
    dither: dithering algorithm to use when quantizing.
        None: the default, performs no dithering
        'floydsteinberg': available with 'mc', 'as', and 'nq'
        'riemersma': only available with 'as'
    """
    # build and execute shell command for quantizing an image file

    if colors == 0:
        #skip quantization, just copy directly to destquant
        shutil.copyfile(src, destquant)

    elif algorithm == 'mc': #median-cut
        if dither is None:
            ditheropt = '-nofs '
        elif dither == 'floydsteinberg':
            ditheropt = ''
        else:
            raise ValueError("Invalid dither type '{0}' for 'mc' quantization".format(dither))
        #using stdin/stdout to file since pngquant can't save to a custom output path
        command = '"{pngquant}" {dither}-force {colors}'.format(
            pngquant=PNGQUANT_PATH, dither=ditheropt, colors=colors)
        with open(src, 'rb') as srcfile:
            stdinput = srcfile.read()
        stdoutput = process_command(command, stdinput=stdinput, stdout_=True)
        with open(destquant, 'wb') as destfile:
            destfile.write(stdoutput)

    elif algorithm == 'as': #adaptive spatial subdivision
        if dither is None:
            ditheropt = 'None'
        elif dither in ('floydsteinberg', 'riemersma'):
            ditheropt = dither
        else:
            raise ValueError("Invalid dither type '{0}' for 'as' quantization".format(dither))
        command = '"{convert}" "{src}" -dither {dither} -colors {colors} "{dest}"'.format(
            convert=IMAGEMAGICK_CONVERT_PATH, src=src, dither=ditheropt, colors=colors, dest=destquant)
        process_command(command)

    elif algorithm == 'nq': #neuquant
        ext = "~quant.png"
        destdir = os.path.dirname(destquant)
        if dither is None:
            ditheropt = ''
        elif dither == 'floydsteinberg':
            ditheropt = '-Q f '
        else:
            raise ValueError("Invalid dither type '{0}' for 'nq' quantization".format(dither))
        command = '"{pngnq}" -f {dither}-d "{destdir}" -n {colors} -e {ext} "{src}"'.format(
            pngnq = PNGNQ_PATH, dither=ditheropt, destdir=destdir, colors=colors, ext=ext, src=src)
        process_command(command)
        #rename output file to destquant (because pngnq can't save to a custom path)
        old_dest = os.path.join(destdir, os.path.splitext(os.path.basename(src))[0] + ext)
        os.rename(old_dest, destquant)
    else:
        #argparse should have caught this before it even reaches here
        raise NotImplementedError('Unknown quantization algorithm "{0}"'.format(algorithm))


def palette_remap(src, destremap, paletteimg, dither=None):
    """remap src to paletteimage's colors, save to destremap

    src: path of source image
    destremap: path to save output remapped image
    paletteimg: path of an image; it contains the colors to which src will be remapped
    dither: dithering algorithm to use when remapping.
        Options are None, 'floydsteinberg', and 'riemersma'
"""

    if not os.path.exists(paletteimg): #because imagemagick doesn't check
        raise IOError("Remapping palette image {0} not found".format(paletteimg))

    if dither is None:
        ditheropt = 'None'
    elif dither in ('floydsteinberg', 'riemersma'):
        ditheropt = dither
    else:
        raise ValueError("Invalid dither type '{0}' for remapping".format(dither))
    command = '"{convert}" "{src}" -dither {dither} -remap "{paletteimg}" "{dest}"'.format(
        convert=IMAGEMAGICK_CONVERT_PATH, src=src, dither=ditheropt, paletteimg=paletteimg, dest=destremap)
    process_command(command)


def make_palette(srcimage):
    """get unique colors from srcimage, return #rrggbb hex color strings"""

    command = '"{convert}" "{srcimage}" -unique-colors -compress none ppm:-'.format(
        convert = IMAGEMAGICK_CONVERT_PATH, srcimage=srcimage)
    stdoutput = process_command(command, stdout_=True)

    # separate stdout ppm image into its colors
    ppm_lines = stdoutput.decode().splitlines()[3:]
    del stdoutput #free up a little memory in advance
    colorvals = tuple()
    for line in ppm_lines:
        colorvals += tuple(int(s) for s in line.split())

    #create i:j ranges that get every 3 values in colorvals
    irange = range(0, len(colorvals), 3)
    jrange = range(3, len(colorvals)+1, 3)
    hex_colors = []
    for i,j in zip(irange,jrange):
        rgb = colorvals[i:j]
        hex_colors.append("#{0:02x}{1:02x}{2:02x}".format(*rgb))
    hex_colors.reverse() #so it will generally go from light bg to dark fg
    return hex_colors


def get_nonpalette_color(palette, start_black=True, additional=None):
    """return a color hex string not listed in palette

    start_black: start searching for colors starting at black, else white
    additional: if specified, a list of additional colors to avoid returning
"""
    if additional is None:
        palette_ = tuple(palette)
    else:
        palette_ = tuple(palette) + tuple(additional)
    if start_black:
        color_range = range(int('ffffff', 16))
    else:
        color_range = range(int('ffffff', 16), 0, -1)
    for i in color_range:
        color = "#{0:06x}".format(i)
        if color not in palette_:
            return color
    #will fail in the case that palette+additional includes all colors #000000-#ffffff
    raise Exception("All colors exhausted, could not find a nonpalette color")


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


def isolate_color(src,target_tmp ,destlayer, target_color, palette, stack=False): #new version
    """fills the specified color of src with black, all else is white

    src: source image path, must match palette's colors
    destlayer: path to save output image
    target_color: the color to isolate (from palette)
    palette: list of "#010101" etc. (output from make_palette)
    stack: if True, colors before coloridx are white, colors after are black
"""
    coloridx = palette.index(target_color)

    # to avoid problems when the palette contains black or white, background and
    # foreground colors are chosen that are not in the palette (nor black or white)
    bg_white = "#FFFFFF"
    fg_black = "#000000"
    bg_almost_white = get_nonpalette_color(palette, False, (bg_white, fg_black))
    fg_almost_black = get_nonpalette_color(palette, True, (bg_almost_white, bg_white, fg_black))

    # start off the piping of stdin/stdout
    with open(src, 'rb') as srcfile:
        stdinput = srcfile.read()

    # build a large combined command, execute it once it reaches sufficient length
    # (because executing each fill command separately is very slow)
    last_iteration = len(palette)-1 #new
    # command_pre  = '"{convert}" - '.format(convert = IMAGEMAGICK_CONVERT_PATH)
    # command_post = ' -'
    # command_mid = ''
    command_pre  = '"{convert}" "{src}" '.format(convert = IMAGEMAGICK_CONVERT_PATH,src=src)
    command_post = ' "{target}"'.format(target=  target_tmp)
    command_mid = ''

    for i, col in enumerate(palette):
        # fill this color with background or foreground?
        if i == coloridx:
            fill = fg_almost_black
        elif i > coloridx and stack:
            fill = fg_almost_black
        else:
            fill = bg_almost_white


        command_mid += ' -fill "{fill}" -opaque "{color}"'.format(fill=fill, color=col)
        if len(command_mid) >= COMMAND_LEN_NEAR_MAX or (i == last_iteration and command_mid):
            command = command_pre + command_mid + command_post

            stdoutput = process_command(command, stdinput=stdinput, stdout_=True)
            stdinput = stdoutput
            command_mid = '' #reset

    # now color the foreground black and background white
    command = '"{convert}" "{src}" -fill "{fillbg}" -opaque "{colorbg}" -fill "{fillfg}" -opaque "{colorfg}" "{dest}"'.format(
        convert = IMAGEMAGICK_CONVERT_PATH,src=target_tmp, fillbg=bg_white, colorbg=bg_almost_white,
        fillfg=fg_black, colorfg=fg_almost_black, dest=destlayer)
    process_command(command, stdinput=stdinput)



def get_width(src):
    """return width of src image in pixels"""
    command = '"{identify}" -ping -format "%w" "{src}"'.format(
        identify=IMAGEMAGICK_IDENTIFY_PATH, src=src)
    stdoutput = process_command(command, stdout_=True)
    width = int(stdoutput)
    return width


def trace(src, desttrace, outcolor, despeckle=2, smoothcorners=1.0, optimizepaths=0.2, width=None):
    """runs potrace with specified color and options

    src: source image to trace
    desttrace: destination to which output svg is saved
    outcolor: fill color of traced path
    despeckle: supress speckles of this many pixels
        (same as potrace --turdsize)
    smoothcorners: corner smoothing: 0 for no smoothing, 1.334 for max
        (same as potrace --alphamax)
    optimizepaths: Bezier curve optimization: 0 for least, 5 for most
        (same as potrace --opttolerance)
    width: width of output svg in pixels, None for default. Keeps aspect ratio.
"""


    if width is not None:
        width = width/POTRACE_DPI
    command = ('"{potrace}" --svg -o "{dest}" -C "{outcolor}" -t {despeckle} '
        '-a {smoothcorners} -O {optimizepaths} {W}{width} "{src}"').format(
        potrace = POTRACE_PATH, dest=desttrace, outcolor=outcolor,
        despeckle=despeckle, smoothcorners=smoothcorners, optimizepaths=optimizepaths,
        W=('-W ' if width is not None else ''), width=(width if width is not None else ''),
        src=src)


    process_command(command)

def check_range(min, max, typefunc, typename, strval):
    """for argparse type functions, checks the range of a value

    min: minimum acceptable value, also appears in error messages
    max: maximum acceptable value (or None for no maximum), also appears in
        error messages
    typefunc: function to convert strval to the desired value, e.g. float, int
    typename: name of the converted data type, e.g. "an integer", appears in
        error messages
    strval: string containing the desired value
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


def get_args(cmdargs=None):
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
        type=functools.partial(check_range, 0, None, int, "an integer"),
        help="number of cores to use for image processing. "
             "Ignored if processing a single file with 1 color "
             "(default tries to use all cores)")
    # color trace options
    #make colors & palette mutually exclusive
    color_palette_group = parser.add_mutually_exclusive_group(required=True)
    color_palette_group.add_argument('-c',
        '--colors', metavar='N',
        type=functools.partial(check_range, 0, 256, int, "an integer"),
        help="[required unless -p is used instead] "
             "number of colors to reduce each image to before tracing, up to 256. "
             "Value of 0 skips color reduction (not recommended unless images "
             "are already color-reduced)")
    parser.add_argument('-q',
        '--quantization', metavar='algorithm',
        choices=('mc','as','nq'), default='mc',
        help="color quantization algorithm: mc, as, or nq. "
            "'mc' (Median-Cut, default); "
            "'as' (Adaptive Spatial Subdivision, may result in fewer colors); "
            "'nq' (NeuQuant, for hundreds of colors). Disabled if --colors 0")
    #make --floydsteinberg and --riemersma dithering mutually exclusive
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
        type=functools.partial(check_range, 0, None, float, "a floating-point number"), default=2,
        help="scale image this much before tracing for greater detail (default: 2). "
            "The image's output size is not changed. (2 is recommended, or 3 for smaller "
            "details.)")
    # potrace options
    parser.add_argument('-D',
        '--despeckle', metavar='size',
        type=functools.partial(check_range, 0, None, int, "an integer"), default=2,
        help='supress speckles of this many pixels (default: 2)')
    parser.add_argument('-S',
        '--smoothcorners', metavar='threshold',
        type=functools.partial(check_range, 0, 1.334, float, "a floating-point number"), default=1.0,
        help="set corner smoothing: 0 for no smoothing, 1.334 for max "
            "(default: 1.0)")
    parser.add_argument('-O',
        '--optimizepaths', metavar='tolerance',
        type=functools.partial(check_range, 0, 5, float, "a floating-point number"), default=0.2,
        help="set Bezier curve optimization: 0 for least, 5 for most "
              "(default: 0.2)")
    # other options
    parser.add_argument('-v',
        '--verbose', action='store_true',
        help="print details about commands executed by this script")
    parser.add_argument('--version', action='version',
        version='%(prog)s {ver}'.format(ver=VERSION))

    if cmdargs is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(cmdargs)

    # with multiple inputs, --output must use at least one * wildcard
    multi_inputs = False
    for i, input_ in enumerate(get_inputs_outputs(args.input)):
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


def escape_brackets(string):
    '''replace [ with [[], ] with []] (i.e. escapes [ and ] for globbing)'''
    letters = list(string)
    for i, letter in enumerate(letters[:]):
        if letter == '[':
            letters[i] = '[[]'
        elif letter == ']':
            letters[i] = '[]]'
    return ''.join(letters)


def get_inputs_outputs(arg_inputs, output_pattern="{0}.svg", ignore_duplicates=True):
    """returns an iterator of (input, matching output) with *? shell expansion

    arg_inputs: command-line-given inputs, can include *? wildcards
    output_pattern: pattern to rename output file, with {0} for input's base
        name without extension e.g. pic.png + {0}.svg = pic.svg
    ignore_duplicates: don't process or return inputs that have been returned already.
        Warning: this stores all previous inputs, so can be slow given many inputs
"""
    old_inputs = set()
    for arg_input in arg_inputs:
        if '*' in arg_input or '?' in arg_input:
        #preventing [] expansion here because glob has problems with legal [] filenames
        #([] expansion still works in a Unix shell, it happens before Python even executes)
            if '[' in arg_input or ']' in arg_input:
                arg_input = escape_brackets(arg_input)
            inputs_ = tuple(iglob(os.path.abspath(arg_input)))
        else:
        #ensures non-existing file paths are included so they are reported as such
        #(glob silently skips over non-existing files, but we want to know about them)
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


def q1_job(q2, total, layers, settings, findex, input, output):
    """ Initializes files, rescales, and performs color reduction

    q2: the second job queue (isolation + tracing)
    total: a value to measure the total number of q2 tasks
    layers: an ordered list of traced layers as SVGFiles
    settings: a dictionary that must contain the following keys:
        colors, quantization, dither, remap, prescale, tmp
        See color_trace_multi for details of the values
    findex: an integer index for input file
    input: the input path, source png file
    output: the output path, dest svg file
"""
    # create destination directory if it doesn't exist
    destdir = os.path.dirname(os.path.abspath(output))

    if not os.path.exists(destdir):
        os.makedirs(destdir)


    # temporary files will reside next to the respective output file
    this_scaled = os.path.abspath(os.path.join(settings['tmp'], '{0}~scaled.png'.format(findex)))
    this_reduced = os.path.abspath(os.path.join(settings['tmp'], '{0}~reduced.png'.format(findex)))

    try:
        # when quantization is skipped, must use a scaling method that
        # doesn't increase the number of colors
        if settings['colors'] == 0:
            filter_ = 'point'
        else:
            filter_ = 'lanczos'
        rescale(input, this_scaled, settings['prescale'], filter=filter_)


        if settings['colors'] is not None:
            quantize(this_scaled, this_reduced, settings['colors'], algorithm=settings['quantization'], dither=settings['dither'])
        elif settings['remap'] is not None:
            palette_remap(this_scaled, this_reduced, settings['remap'], dither=settings['dither'])
        else:
            #argparse should have caught this
            raise Exception("One of the arguments 'colors' or 'remap' must be specified")
        palette = make_palette(this_reduced)

        # update total based on the number of colors in palette
        total.value -= settings['colors'] - len(palette)

        # initialize layers for the file at findex
        layers[findex] += [False] * len(palette)

        # add jobs to the second job queue
        for i, color in enumerate(palette):
            q2.put({ 'width': get_width(input), 'color': color, 'palette': palette, 'reduced': this_reduced, 'output': output, 'findex': findex, 'cindex': i })

    except (Exception, KeyboardInterrupt) as e:
        # delete temporary files on exception...
        remfiles(this_scaled, this_reduced)
        raise e
    else:
        #...or after tracing
        remfiles(this_scaled)


def q2_job(layers, layers_lock, settings, width, color, palette, findex, cindex, reduced, output):
    """ Isolates a color and traces it

    layers: an ordered list of traced layers as SVGFiles
    layers_lock: a lock that must be acquired for reading and writing the layers object
    settings: a dictionary that must contain the following keys:
        stack, despeckle, smoothcorners, optimizepaths, tmp
        See color_trace_multi for details of the values
    width: the width of the input image
    color: the color to isolate
    findex: an integer index for input file
    cindex: an integer index for color
    reduced: the color-reduced input image
    output: the output path, dest svg file
"""
    # temporary files will reside next to the respective output file
    this_isolated = os.path.abspath(os.path.join(settings['tmp'], '{0}-{1}~isolated.png'.format(findex, cindex)))
    this_layer = os.path.abspath(os.path.join(settings['tmp'], '{0}-{1}~layer.ppm'.format(findex, cindex)))
    trace_format = '{0}-{1}~trace.svg'
    this_trace = os.path.abspath(os.path.join(settings['tmp'], trace_format.format(findex, cindex)))

    try:
        # isolate & trace for this color, add to svg stack
        isolate_color(reduced, this_isolated, this_layer, color, palette, stack=settings['stack'])
        trace(this_layer, this_trace, color, settings['despeckle'], settings['smoothcorners'], settings['optimizepaths'], width)
    except (Exception, KeyboardInterrupt) as e:
        # delete temporary files on exception...
        remfiles(reduced, this_isolated, this_layer, this_trace)
        raise e
    else:
        #...or after tracing
        remfiles(this_isolated, this_layer)

    layers_lock.acquire()
    try:
        # add layer
        layers[findex][cindex] = True

        # check if all layers of this file have been traced
        is_last = False not in layers[findex]
    finally:
        layers_lock.release()

    # save the svg document if it is ready
    if is_last:
        # start the svg stack
        layout = svg_stack.CBoxLayout()

        layer_traces = [os.path.abspath(os.path.join(settings['tmp'], trace_format.format(findex, l))) for l in range(len(layers[findex]))]

        # add layers to svg
        for t in layer_traces:
            layout.addSVG(t)

        # save stacked output svg
        doc = svg_stack.Document()
        doc.setLayout(layout)
        with open(output, 'w') as file:
            doc.save(file)

        remfiles(reduced, *layer_traces)


def process_worker(q1, q2, progress, total, layers, layers_lock, settings):
    """ Function for handling process jobs

    q1: the first job queue (scaling + color reduction)
    q2: the second job queue (isolation + tracing)
    progress: a value to measure the number of completed q2 tasks
    total: a value to measure the total number of q2 tasks
    layers: a nested list. layers[file_index][color_index] is a boolean that
        indicates if the layer for the file at file_index with the color
        at color_index has been traced
    layers_lock: a lock that must be acquired for reading and writing the layers object in q2 jobs
    settings: a dictionary that must contain the following keys:
        quantization, dither, remap, stack, prescale, despeckle, smoothcorners,
        optimizepaths, colors, tmp
        See color_trace_multi for details of the values
"""
    while True:
        # try and get a job from q2 before q1 to reduce the total number of
        # temporary files and memory
        while not q2.empty():
            try:
                job_args = q2.get(block=False)
                q2_job(layers, layers_lock, settings, **job_args)
                q2.task_done()
                progress.value += 1
            except queue.Empty:
                break

        # get a job from q1 since q2 is empty
        try:
            job_args = q1.get(block=False)

            q1_job(q2, total, layers, settings, **job_args)
            q1.task_done()
        except queue.Empty:
            time.sleep(.01)

def color_trace_multi(inputs, outputs, colors, processcount, quantization='mc', dither=None,
    remap=None, stack=False, prescale=2, despeckle=2, smoothcorners=1.0, optimizepaths=0.2):
    """color trace input images with specified options

    inputs: list of input paths, source png files
    outputs: list of output paths, dest svg files
    colors: number of colors to quantize to, 0 for no quantization
    processcount: number of process to launch for image processing
    quantization: color quantization algorithm to use:
        - 'mc' = median-cut (default, for few colors, uses pngquant)
        - 'as' = adaptive spatial subdivision (uses imagemagick, may result in fewer colors)
        - 'nq' = neuquant (for lots of colors, uses pngnq)
    dither: dithering algorithm to use. (Remember, final output is affected by despeckle.)
        None: the default, performs no dithering
        'floydsteinberg': available with 'mc', 'as', and 'nq'
        'riemersma': only available with 'as'
    palette: source of custom palette image for color reduction (overrides
        colors and quantization)
    stack: whether to stack color traces (recommended for more accurate output)
    despeckle: supress speckles of this many pixels
    smoothcorners: corner smoothing: 0 for no smoothing, 1.334 for max
    optimizepaths: Bezier curve optimization: 0 for least, 5 for most
"""
    tmp = tempfile.mkdtemp()

    # create a two job queues
    # q1 = scaling + color reduction
    q1 = multiprocessing.JoinableQueue()
    # q2 = isolation + tracing
    q2 = multiprocessing.JoinableQueue()

    # create a manager to share the layers between processes
    manager = multiprocessing.Manager()
    layers = []
    for i in range(min(len(inputs), len(outputs))):
        layers.append(manager.list())
    # and make a lock for reading and modifying layers
    layers_lock = multiprocessing.Lock()

    # create a shared memory counter of completed and total tasks for measuring progress
    progress = multiprocessing.Value('i', 0)
    # this is only an estimate because quantization can result in less colors
    # than in the "colors" variable. This value is corrected by q1 tasks to converge
    # on the real total.
    total = multiprocessing.Value('i', len(layers) * colors)

    # create and start processes
    processes = []
    for i in range(processcount):
        p = multiprocessing.Process(target=process_worker, args=(q1, q2, progress, total, layers, layers_lock, locals()))
        p.name = "color_trace worker #" + str(i)
        p.start()
        processes.append(p)

    try:
        # so for each input and (dir-appended) output...
        for index, (i, o) in enumerate(zip(inputs, outputs)):
            verbose(i, ' -> ', o)

            # add a job to the first job queue
            q1.put({ 'input': i, 'output': o, 'findex': index })


        # show progress until all jobs have been completed
        while progress.value < total.value:
            sys.stdout.write("\r%.1f%%" % (progress.value / total.value * 100))
            sys.stdout.flush()
            time.sleep(0.25)

        sys.stdout.write("\rTracing complete!\n")

        # join the queues just in case progress is wrong
        q1.join()
        q2.join()
    except (Exception, KeyboardInterrupt) as e:
        # shut down subproesses
        for p in processes:
            p.terminate()
        shutil.rmtree(tmp)
        raise e

    # close all processes
    for p in processes:
        p.terminate()
    shutil.rmtree(tmp)


def remfiles(*filepaths):
    """remove file paths if they exist"""
    for f in filepaths:
        if os.path.exists(f):
            os.remove(f)


def main(args=None):
    """main function to collect arguments and run color_trace_multi

    args: if specified, a Namespace of arguments (see argparse) to use instead
        of those supplied to this script at the command line
"""
    if args is None:
        args = get_args()

    #set verbosity level
    if args.verbose:
        global VERBOSITY_LEVEL
        VERBOSITY_LEVEL = 1

    # set output filename pattern depending on --output argument
    if args.output is None:
        output_pattern = "{0}.svg"
    elif '*' in args.output:
        output_pattern = args.output.replace('*', "{0}")
    else:
        output_pattern = args.output

    # --directory: add dir to output paths
    if args.directory is not None:
        destdir = args.directory.strip('\"\'')
        output_pattern = os.path.join(destdir, output_pattern)

    # set processcount if not defined
    if args.cores is None:
        try:
            processcount = multiprocessing.cpu_count()
        except NotImplementedError:
            verbose("Could not determine total number of cores, assuming 1")
            processcount = 1
    else:
        processcount = args.cores

    # collect only those arguments needed for color_trace_multi
    inputs_outputs = zip(*get_inputs_outputs(args.input, output_pattern))
    try:
        inputs, outputs = inputs_outputs
    except ValueError: #nothing to unpack
        inputs, outputs = [], []
    if args.floydsteinberg:
        dither = 'floydsteinberg'
    elif args.riemersma:
        dither = 'riemersma'
    else:
        dither = None
    colors = args.colors
    color_trace_kwargs = vars(args)
    for k in ('colors', 'directory', 'input', 'output', 'cores', 'floydsteinberg', 'riemersma', 'verbose'):
        color_trace_kwargs.pop(k)

##    color_trace_multi(inputs, outputs, colors, dither=dither, **color_trace_kwargs)
    try:
        color_trace_multi(inputs, outputs, colors, processcount, dither=dither, **color_trace_kwargs)
    except BaseException as e:
        print(e, file=sys.stderr)
        sys.exit(1)



if __name__ == '__main__':
    main()
