from __future__ import annotations

from dataclasses import dataclass
import argparse
import logging
import os
import pathlib
import struct
import sys
import tempfile
from configparser import ConfigParser

import ffmpeg
from PIL import Image

from tqdm import tqdm

DEFAULT_SECTION = 'DEFAULT'

SD_TILE_WIDTH = 12 * 3
SD_TILE_HEIGHT = 18 * 3

HD_TILE_WIDTH = 12 * 2
HD_TILE_HEIGHT = 18 * 2

TILES_PER_PAGE = 256

MAX_DISPLAY_X = 60
MAX_DISPLAY_Y = 22

FRAME_SIZE = MAX_DISPLAY_X * MAX_DISPLAY_Y

CONFIG_FILE_NAME = 'osd-dump-tools.ini'

file_header_struct = struct.Struct("<7sH4B2HB")
frame_header_struct = struct.Struct("<II")
logger = logging.getLogger(__name__)


@dataclass
class Frame:
    idx: int
    size: int
    data: bytes


class Font:
    def __init__(self, basename: str, is_hd: bool):
        self.basename = basename
        self.is_hd = is_hd

        self.img = self._load_pair(basename)

    def _load_raw(self, path: str) -> Image.Image:
        with open(path, "rb") as f:
            data = f.read()
            img = Image.frombytes(
                "RGBA",
                (
                    HD_TILE_WIDTH if self.is_hd else SD_TILE_WIDTH,
                    (HD_TILE_HEIGHT if self.is_hd else SD_TILE_HEIGHT) * TILES_PER_PAGE,
                ),
                data,
            )

        return img

    def _load_pair(self, basename: str) -> Image.Image:
        font_1 = self._load_raw(f"{basename}.bin")
        font_2 = self._load_raw(f"{basename}_2.bin")

        font = Image.new("RGBA", (font_1.width, font_1.height + font_2.height))
        font.paste(font_1, (0, 0))
        font.paste(font_2, (0, font_1.height))

        return font

    def __getitem__(self, key: int) -> Image.Image:
        return self.img.crop(
            (
                0,
                key * (HD_TILE_HEIGHT if self.is_hd else SD_TILE_HEIGHT),
                HD_TILE_WIDTH if self.is_hd else SD_TILE_WIDTH,
                key * ((HD_TILE_HEIGHT if self.is_hd else SD_TILE_HEIGHT))
                + (HD_TILE_HEIGHT if self.is_hd else SD_TILE_HEIGHT),
            )
        )


class ExcludeArea:
    def __init__(self, s: str):

        nums = s.split(',')
        if len(nums) != 4:
            raise Exception('Incorrect no of region parameters, should be 4, received {len(nums)}.')

        self.x1 = int(nums[0])
        self.y1 = int(nums[1])
        self.x2 = int(nums[2])
        self.y2 = int(nums[3])

    def is_excluded(self, x: int, y: int) -> bool:
        return self.x1 <= x < self.x2 and self.y1 <= y < self.y2


class MultiExcludedAreas:
    def __init__(self):
        self.excluded_areas = []

    def is_excluded(self, x: int, y: int) -> bool:
        for area in self.excluded_areas:
            if area.is_excluded(x, y):
                return True

        return False

    def merge(self, params: ExcludeArea | list[ExcludeArea]) -> None :
        try:
            for area in params:
                self.excluded_areas.append(area)
        except TypeError:
            self.excluded_areas.append(params)


class Config:
    params: tuple[tuple[str, type]] = (
        ('font', str), ('hd', bool), ('wide', bool), ('fakehd', bool), ('bitrate', int),
        ('nolinks', bool), ('testrun', bool), ('testframe', int), ('hq', bool),
    )

    def __init__(self, cfg: ConfigParser):
        super().__init__()

        self.font : str = ''
        self.wide: bool = False
        self.fakehd: bool = False
        self.bitrate: int = 25
        self.nolinks: bool = False
        self.testrun: bool = False
        self.testframe: int = -1
        self.hd: bool = False
        self.hq: bool = False

        self.exclude_area = MultiExcludedAreas()

        self.update_cfg(cfg[DEFAULT_SECTION])

    def set_value_from_cfg(self, cfg: ConfigParser, name: str, t: type) -> None:
        try:
            v = cfg[name]
            setattr(self, name, t(v))
        except KeyError:
            pass

    def update_cfg(self, cfg) -> None:
        for name, typ in self.params:
            self.set_value_from_cfg(cfg, name, typ)

        # update regions
        for i in range(1, 100):
            try:
                val = cfg[f'ignore_area_{i}']
                self.exclude_area.merge(ExcludeArea(val))
            except KeyError:
                break

    def merge_cfg(self, args: argparse.Namespace) -> None:
        for name, typ in self.params:
            v = getattr(args, name, None)
            if v is not None:
                setattr(self, name, v)

        # this is special case
        self.video = args.video

        # merge regions
        self.exclude_area.merge(args.ignore_area)


def build_cmd_line_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("video", type=str, help="video file e.g. DJIG0007.mp4")
    parser.add_argument(
        "--font", type=str, default=None, help='font basename e.g. "font"'
    )
    parser.add_argument(
        "--wide", action="store_true", default=None, help="is this a 16:9 video?"
    )

    parser.add_argument(
        "--bitrate", type=int, default=None, help='output bitrate'
    )
    parser.add_argument(
        "--ignore_area", type=ExcludeArea, nargs='*', default="-1, -1, 0, 0", help="don't display area (in fonts, x1,y1,x2,y2), i.e. 10,10,15,15, can be repeated"
    )
    parser.add_argument(
        "--nolinks", action="store_true", default=None, help="Copy frames instead of linking (windows without priviledged shell)"
    )

    parser.add_argument(
        "--hq", action="store_true", default=None, help="render with high quality profile (slower)"
    )

    parser.add_argument(
        "--testrun", action="store_true", default=False, help="Create overlay with osd data in video location and ends"
    )

    parser.add_argument(
        "--testframe", type=int, default=-1, help="Osd data frame for testrun"
    )

    hdivity = parser.add_mutually_exclusive_group()
    hdivity.add_argument(
        "--hd", action="store_true", default=None, help="is this an HD OSD recording?"
    )
    hdivity.add_argument(
        "--fakehd",
        "--fullhd",
        action="store_true",
        default=None,
        help="are you using full-hd or fake-hd in this recording?",
    )

    return parser


def draw_frame(
    font: Font,
    frame: Frame,
    args: Config
) -> Image.Image:
    internal_width = 60
    internal_height = 22

    if args.fakehd:
        display_width = 60
        display_height = 22
    elif args.hd:
        display_width = 50
        display_height = 18
    else:
        display_width = 30
        display_height = 15

    img = Image.new(
        "RGBA",
        (
            display_width * (HD_TILE_WIDTH if args.hd or args.fakehd else SD_TILE_WIDTH),
            display_height
            * (HD_TILE_HEIGHT if args.hd or args.fakehd else SD_TILE_HEIGHT),
        ),
    )

    for y in range(internal_height):
        for x in range(internal_width):
            char = frame.data[y + x * internal_height]
            tile = font[char]

            if args.exclude_area.is_excluded(x, y):
                font_no = ord(' ')
                if args.testrun:
                    font_no = ord('X')

                tile = font[font_no]

            # tile = font[char]
            img.paste(
                tile,
                (
                    x * (HD_TILE_WIDTH if args.hd or args.fakehd else SD_TILE_WIDTH),
                    y * (HD_TILE_HEIGHT if args.hd or args.fakehd else SD_TILE_HEIGHT),
                ),
            )

    if args.fakehd or args.hd or args.wide:
        img_size = (1280, 720)
    else:
        img_size = (960, 720)

    img = img.resize(img_size, Image.Resampling.BICUBIC)

    return img


def read_osd_frames(osd_path: pathlib.PurePath) -> list[Frame]:
    frames = []

    with open(osd_path, "rb") as dump_f:
        file_header_data = dump_f.read(file_header_struct.size)
        file_header = file_header_struct.unpack(file_header_data)

        if file_header[0] != b"MSPOSD\x00":
            logger.critical("%s has an invalid file header", osd_path)
            sys.exit(1)

        logger.info("file header: %s", file_header[0].decode("ascii"))
        logger.info("file version: %d", file_header[1])
        logger.info("char width: %d", file_header[2])
        logger.info("char height: %d", file_header[3])
        logger.info("font widtht: %d", file_header[4])
        logger.info("font height: %d", file_header[5])
        logger.info("x offset: %d", file_header[6])
        logger.info("y offset: %d", file_header[7])
        logger.info("font variant: %d", file_header[8])

        while True:
            frame_header = dump_f.read(frame_header_struct.size)
            if len(frame_header) == 0:
                break

            frame_head = frame_header_struct.unpack(frame_header)
            frame_idx, frame_size = frame_head

            frame_data_struct = struct.Struct(f"<{frame_size}H")
            frame_data = dump_f.read(frame_data_struct.size)
            frame_data = frame_data_struct.unpack(frame_data)

            frames.append(Frame(frame_idx, frame_size, frame_data))

    return frames


def main(args: Config):
    logging.basicConfig(level=logging.DEBUG)

    logger.info(f"loading fonts from {args.font}")

    if args.hd or args.fakehd:
        font = Font(f"{args.font}_hd", is_hd=True)
    else:
        font = Font(args.font, is_hd=False)

    video_path = pathlib.PurePath(args.video)
    video_stem = video_path.stem
    osd_path = video_path.with_suffix('.osd')
    out_path = video_path.with_name(video_stem + "_with_osd.mp4")


    logger.info("loading OSD dump from %s", osd_path)

    frames = read_osd_frames(osd_path)

    if args.testrun:
        test_path = str(video_path.with_name('test_image.png'))
        draw_frame(
            font=font,
            frame=frames[args.testframe],
            args=args
        ).save(test_path)

        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        logger.info("rendering %d frames", len(frames))

        start_number = frames[0].idx

        for i, frame in enumerate(tqdm(frames)):
            osd_img = draw_frame(
                font=font,
                frame=frame,
                args=args
            )

            fname = f"{tmp_dir}/{frame.idx:016}.png"
            osd_img.save(fname)
            if i < len(frames) - 1:
                next_frame = frames[i + 1]
                for j in range(frame.idx + 1, next_frame.idx):
                    lfname = f"{tmp_dir}/{j:016}.png"
                    if args.nolinks:
                        osd_img.save(lfname)
                    else:
                        os.symlink(fname, lfname)

        logger.info("passing to ffmpeg, out as %s", out_path)

        # Overlay on top of the video (DJIG0007.mp4)
        # frame_overlay = ffmpeg.input(
        #     f"{tmp_dir}/*.png", pattern_type="glob", framerate=60
        # )
        frame_overlay = ffmpeg.input(f"{tmp_dir}/%016d.png", start_number=start_number, framerate=60, thread_queue_size=1024)
        video = ffmpeg.input(str(video_path), thread_queue_size=1024)

        if args.fakehd or args.hd or args.wide:
            out_size = {"w": 1280, "h": 720}
        else:
            out_size = {"w": 960, "h": 720}

        output_params = {
            'video_bitrate': f"{args.bitrate}M",
        }

        hq_output = {
            'mbd': 'rd',
            'flags': '+mv4+aic',
            'trellis': 2,
            'cmp': 2,
            'subcmp': 2,
            'g': 300,
            'pass': '1/2',
        }

        if args.hq:
            output_params.update(hq_output)

        (
            video.filter("scale", **out_size, force_original_aspect_ratio=1)
            .filter("pad", **out_size, x=-1, y=-1, color="black")
            .overlay(frame_overlay, x=0, y=0)
            # mbd='rd' -flags +mv4+aic -trellis 2 -cmp 2 -subcmp 2 -g 300 -pass 1/2’
            # preset='slow', crf=12, tune='film'
            .output(str(out_path), **output_params)
            .run(overwrite_output=True)
        )


if __name__ == "__main__":
    cfg = ConfigParser()
    cfg.read(pathlib.PurePath(__file__).parent / CONFIG_FILE_NAME)
    cfg.read(CONFIG_FILE_NAME)

    parser = build_cmd_line_parser()

    args = Config(cfg)
    args.merge_cfg(parser.parse_args())

    if os.name == 'nt':
        import ctypes
        adm = ctypes.windll.shell32.IsUserAnAdmin()
        if not adm and not args.nolinks and not args.testrun:
            logger.error('To run you need priviledged shell. Check --nolinks option. Terminating.')
            sys.exit(1)

    main(args)
