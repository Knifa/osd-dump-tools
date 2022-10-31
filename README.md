# osd-dump tools

Overlays msp-osd recordings over video files.
### Requirements

- Windows as describe below or [use WSL](https://learn.microsoft.com/en-us/windows/wsl/install).
- Python 3.8+ is required.
- ffmpeg is required.

  ```shell
  # Debian and friends
  $ sudo apt install ffmpeg

  # macOS
  $ brew install ffmpeg
  ```

  # Windows
  Download ffmpeg from https://github.com/BtbN/FFmpeg-Builds/releases
  Extract to any folder on disk (i.e. c:\ffmpeg), add this folder to environment variable 'path'
  To use tool you have to run priviledged cmd. Start-> search for cmd -> right click -> run as admin.
  If you don't like to use elevated shell other solution is to use WSL.
### Setup

```shell
# Setting up a virtual environment is recommended, but not required.
python -m venv venv
source ./venv/bin/activate

# Install dependencies.
$ pip install -r requirements.txt
```

### Usage

- Place font files and video files in this directory.

```shell
# Check out the options.
$ python -m osd --help

  usage: __main__.py [-h] [--font FONT] [--wide] [--hd] video

  positional arguments:
    video        video file e.g. DJIG0007.mp4

  options:
    -h, --help    show this help message and exit
    --font FONT   font basename e.g. "font"
    --wide        is this a 16:9 video?
    --hd          is this an HD OSD recording?
    --fakehd      are you using fakehd?
    -- bitrate    output bitrate, default is 25mbps
    --ignore_area very useful option to hide GPS coords or altitude, can be repeated, parameters are top,left,right,bottom

# Convert your recording!
$ python -m osd --font font_inav --hd --wide DJIG0001.mp4

  INFO:__main__:loading OSD dump from DJIG0001.osd
  INFO:__main__:rendering 168 frames
  INFO:__main__:passing to ffmpeg, out as DJIG0001_with_osd.mp4
  ... etc ...
```
