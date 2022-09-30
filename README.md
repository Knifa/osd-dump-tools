# osd-dump tools

Overlays msp-osd recordings over video files.

## Usage

- Python 3.10+ and Poetry are required.
- Place font files and video files in this directory.

```bash
$ poetry install
$ poetry run python -m osd --help

usage: __main__.py [-h] [--font FONT] [--wide] [--hd] video

positional arguments:
  video        video file e.g. DJIG0007.mp4

options:
  -h, --help   show this help message and exit
  --font FONT  font basename e.g. "font"
  --wide       is this a 16:9 video?
  --hd         is this an HD OSD recording?

$ poetry run python -m osd --font font_inav --hd --wide DJIG0001.mp4

INFO:__main__:loading OSD dump from DJIG0001.osd
INFO:__main__:rendering 168 frames
INFO:__main__:passing to ffmpeg, out as DJIG0001_with_osd.mp4
```
