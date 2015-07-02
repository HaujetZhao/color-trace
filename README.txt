color_trace_multi.py
v1.00 Windows exe-bundled version - Copyright (c) 2012 ukurereh

Traces multiple color images using potrace. This is similar to Inkscape's Trace Bitmap function.

Requires Python 3.2 (or later) and the lxml library for Python 3.2 (or later).

Also, several programs must be installed for coor_trace.py to function: pngquant, pngnq, ImageMagick's convert and identify, and Potrace. Their executables must be accessible from the environment path, or the location of the executables must be entered into color_trace.py (variables PNGQUANT_PATH, PNGNQ_PATH, IMAGEMAGICK_CONVERT_PATH, IMAGEMAGICK_IDENTIFY_PATH, and POTRACE_PATH).

----------------

USAGE:
color_trace_multi.py [-h] -i src [src ...] [-o dest] [-d destdir]
                     [-c N] [-q algorithm] [-fs | -ri]
                     [-r paletteimg] [-s] [-p size] [-D size]
                     [-S threshold] [-O tolerance] [-v] [--version]

trace a color image with potrace, output color SVG file

optional arguments:
  -h, --help, /?        show this help message and exit
  -i src [src ...], --input src [src ...]
                        path of input image(s) to trace, supports * and ?
                        wildcards
  -o dest, --output dest
                        path of output image to save to, supports * wildcard
  -d destdir, --directory destdir
                        outputs to destdir
  -c N, --colors N      [required unless -p is used instead] number of colors
                        to reduce each image to before tracing, up to 256.
                        Value of 0 skips color reduction (not recommended
                        unless images are already color-reduced)
  -q algorithm, --quantization algorithm
                        color quantization algorithm: mc, as, or nq. 'mc'
                        (Median-Cut, default); 'as' (Adaptive Spatial
                        Subdivision, may result in fewer colors); 'nq'
                        (NeuQuant, for hundreds of colors). Disabled if
                        --colors 0
  -fs, --floydsteinberg
                        enable Floyd-Steinberg dithering (for any quantization
                        or -p/--palette). Warning: any dithering will greatly
                        increase output svg's size and complexity.
  -ri, --riemersma      enable Rimersa dithering (only for Adaptive Spatial
                        Subdivision quantization or -p/--palette)
  -r paletteimg, --remap paletteimg
                        use a custom palette image for color reduction
                        [overrides -c and -q]
  -s, --stack           stack color traces (recommended for more accurate
                        output)
  -p size, --prescale size
                        scale image this much before tracing for greater
                        detail (default: 2). The image's output size is not
                        changed. (2 is recommended, or 3 for smaller details.)
  -D size, --despeckle size
                        supress speckles of this many pixels (default: 2)
  -S threshold, --smoothcorners threshold
                        set corner smoothing: 0 for no smoothing, 1.334 for
                        max (default: 1.0)
  -O tolerance, --optimizepaths tolerance
                        set Bezier curve optimization: 0 for least, 5 for most
                        (default: 0.2)
  -v, --verbose         print details about commands executed by this script
  --version             show program's version number and exit

----------------

LICENSE: (see also LICENSE.txt)

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

----------------

ATTRIBUTION:
color_trace.py imports from:
- svg_stack.py (modified version), Copyright (c) 2009 Andrew D. Straw
