# Third-party material

## Bootstrap Icons 1.11.3 (examples/icon_dataset/png)

The 2050 bitmaps in `examples/icon_dataset/png` are renderings of the SVG
glyphs of Bootstrap Icons 1.11.3 (https://github.com/twbs/icons), produced by
`examples/prepare_icon_dataset.cjs`. `examples/icon_dataset/manifest.json`
records the archive hash and a SHA-256 digest of every bitmap. Bootstrap Icons
is distributed under the MIT License:

    The MIT License (MIT)

    Copyright (c) 2019-2024 The Bootstrap Authors

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
    THE SOFTWARE.

## Font Awesome Free 6.7.2 (examples/complex_inputs/png/fa_snowflake.png)

One test fixture is a rendering of the "snowflake" icon of Font Awesome Free
6.7.2 by Fonticons, Inc. (https://fontawesome.com), whose icons are licensed
under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

## Material that is referenced but not redistributed

* **MPEG-7 CE-Shape-1 silhouettes** used during development. One test reads
  `examples/complex_inputs/png/mpeg7_deer.png` and is skipped when the file is
  absent; the redistribution terms of that dataset are not stated, so it is
  not included.

* **Scanned documents** used by `examples/real_scans.py` (a 1902 USGS
  topographic sheet, the drawing of U.S. patent 223,898 held by the U.S.
  National Archives, and a Historic American Engineering Record floor plan).
  They are works of U.S. federal agencies. Their URLs on Wikimedia Commons and
  their SHA-256 digests are in `examples/real_scans/results/sources.json`;
  download them into `examples/real_scans/download/` to rerun the experiment.
  The small crops written next to the results are excerpts of these scans.
* **Published results of other methods** audited by
  `examples/audit_published_results.py`: `additional_results.pdf` from the
  PolyFit project page (Dominici et al., SIGGRAPH 2020),
  https://www.cs.ubc.ca/labs/imager/tr/2020/ClipArtVectorization/. Only our
  measurements are included here.
* **Potrace 1.16** (GPL), used unmodified as an external program by
  `examples/compare_potrace.py` and `examples/certify_potrace.py`; obtain it
  from https://potrace.sourceforge.net/.
