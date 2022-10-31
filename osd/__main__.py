from __future__ import annotations

import argparse
import dataclasses
import logging
from operator import truediv
import os
import pathlib
import struct
import sys
import tempfile
from typing import Sequence, cast, Optional

import ffmpeg
from PIL import Image

SD_TILE_WIDTH = 12 * 3
SD_TILE_HEIGHT = 18 * 3

HD_TILE_WIDTH = 12 * 2
HD_TILE_HEIGHT = 18 * 2

TILES_PER_PAGE = 256

MAX_DISPLAY_X = 60
MAX_DISPLAY_Y = 22

FRAME_SIZE = MAX_DISPLAY_X * MAX_DISPLAY_Y

file_header_struct = struct.Struct("<7sH4B2HB")
frame_header_struct = struct.Struct(f"<II")
logger = logging.getLogger(__name__)


@dataclasses.dataclass
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
    excluded_areas = []

    def __init__(self, s: str):
        a = ExcludeArea(s)
        self.excluded_areas.append(a)

    def is_excluded(self, x: int, y: int) -> bool:
        for area in self.excluded_areas:
            if area.is_excluded(x, y):
                return True

        return False
    


def draw_frame(
    font: Font,
    frame: Sequence[int],
    is_hd: bool,
    is_wide: bool,
    is_fake_hd: bool,
    ignore_area: MultiExcludedAreas,
) -> Image.Image:
    internal_width = 60
    internal_height = 22

    if is_fake_hd:
        display_width = 60
        display_height = 22
    elif is_hd:
        display_width = 50
        display_height = 18
    else:
        display_width = 30
        display_height = 15

    img = Image.new(
        "RGBA",
        (
            display_width * (HD_TILE_WIDTH if is_hd or is_fake_hd else SD_TILE_WIDTH),
            display_height
            * (HD_TILE_HEIGHT if is_hd or is_fake_hd else SD_TILE_HEIGHT),
        ),
    )

    for y in range(internal_height):
        for x in range(internal_width):
            if ignore_area.is_excluded(x, y):
                continue

            char = frame.data[y + x * internal_height]
            tile = font[char]
            img.paste(
                tile,
                (
                    x * (HD_TILE_WIDTH if is_hd or is_fake_hd else SD_TILE_WIDTH),
                    y * (HD_TILE_HEIGHT if is_hd or is_fake_hd else SD_TILE_HEIGHT),
                ),
            )

    if is_fake_hd or is_hd or is_wide:
        img_size = (1280, 720)
    else:
        img_size = (960, 720)

    img = img.resize(img_size, Image.Resampling.BICUBIC)

    return img


def main(args: Args):
    logging.basicConfig(level=logging.DEBUG)

    if args.hd or args.fakehd:
        font = Font(f"{args.font}_hd", is_hd=True)
    else:
        font = Font(args.font, is_hd=False)

    video_path = pathlib.PurePath(args.video)
    video_stem = video_path.stem
    #TODO: there is probably better way to do this
    osd_path = str(video_path.parent) + '/' + video_stem + ".osd"
    out_path = video_stem + "_with_osd.mp4"

    logger.info("loading OSD dump from %s", osd_path)

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

            frame_header = frame_header_struct.unpack(frame_header)
            frame_idx, frame_size = frame_header

            frame_data_struct = struct.Struct(f"<{frame_size}H")
            frame_data = dump_f.read(frame_data_struct.size)
            frame_data = frame_data_struct.unpack(frame_data)

            frames.append(Frame(frame_idx, frame_size, frame_data))

    draw_frame(
        font=font,
        frame=frames[-1],
        is_hd=args.hd,
        is_wide=args.wide,
        is_fake_hd=args.fakehd,
        ignore_area=args.ignore_area
    ).save("test.png")

    with tempfile.TemporaryDirectory() as tmp_dir:
        logger.info("rendering %d frames", len(frames))

        for i, frame in enumerate(frames):
            osd_img = draw_frame(
                font=font,
                frame=frame,
                is_hd=args.hd,
                is_wide=args.wide,
                is_fake_hd=args.fakehd,
                ignore_area=args.ignore_area
            )

            osd_img.save(f"{tmp_dir}/{frame.idx:016}.png")
            if i < len(frames) - 1:
                next_frame = frames[i + 1]
                for j in range(frame.idx + 1, next_frame.idx):
                    os.symlink(
                        f"{tmp_dir}/{frame.idx:016}.png", f"{tmp_dir}/{j:016}.png"
                    )

        logger.info("passing to ffmpeg, out as %s", out_path)

        # Overlay on top of the video (DJIG0007.mp4)
        frame_overlay = ffmpeg.input(
            f"{tmp_dir}/*.png", pattern_type="glob", framerate=60
        )
        video = ffmpeg.input(str(video_path))

        if args.fakehd or args.hd or args.wide:
            out_size = {"w": 1280, "h": 720}
        else:
            out_size = {"w": 960, "h": 720}

        (
            video.filter("scale", **out_size, force_original_aspect_ratio=1)
            .filter("pad", **out_size, x=-1, y=-1, color="black")
            .overlay(frame_overlay, x=0, y=0)
            .output(out_path, video_bitrate=f"{args.bitrate}M")
            .run(overwrite_output=True)
        )

class Args(argparse.Namespace):
    font: str
    hd: bool
    wide: bool
    video: str
    fakehd: bool
    bitrate: int
    ignore_area: MultiExcludedAreas


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=str, help="video file e.g. DJIG0007.mp4")
    parser.add_argument(
        "--font", type=str, default="font", help='font basename e.g. "font"'
    )
    parser.add_argument(
        "--wide", action="store_true", default=False, help="is this a 16:9 video?"
    )

    hdivity = parser.add_mutually_exclusive_group()
    hdivity.add_argument(
        "--hd", action="store_true", default=False, help="is this an HD OSD recording?"
    )
    hdivity.add_argument(
        "--fakehd",
        "--fullhd",
        action="store_true",
        default=False,
        help="are you using full-hd or fake-hd in this recording?",
    )
    parser.add_argument(
        "--bitrate", type=int, default="25", help='output bitrate, default 25mpbs'
    )
    parser.add_argument(
        "--ignore_area", type=MultiExcludedAreas, default="-1, -1, 0, 0", help="don't display area (in fonts, x1,y1,x2,y2), i.e. 10,10,15,15, can be repeated"
    )

    args = cast(Args, parser.parse_args())

    main(args)
