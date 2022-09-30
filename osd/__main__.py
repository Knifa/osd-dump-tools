from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import struct
import tempfile
from typing import cast
import pathlib

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


def draw_frame(
    font: Font, frame, frame_index: int, is_hd: bool, wide: bool
) -> Image.Image:
    internal_width = 60
    internal_height = 22

    if is_hd:
        display_width = 50
        display_height = 18
    else:
        display_width = 30
        display_height = 15

    img = Image.new(
        "RGBA",
        (
            display_width * (HD_TILE_WIDTH if is_hd else SD_TILE_WIDTH),
            display_height * (HD_TILE_HEIGHT if is_hd else SD_TILE_HEIGHT),
        ),
    )

    for y in range(internal_height):
        for x in range(internal_width):
            char = frame.data[y + x * internal_height]
            tile = font[char]
            img.paste(
                tile,
                (
                    x * (HD_TILE_WIDTH if is_hd else SD_TILE_WIDTH),
                    y * (HD_TILE_HEIGHT if is_hd else SD_TILE_HEIGHT),
                ),
            )

    # info_str = f"{frame_index}i:{frame.idx}f"
    # for i, char in enumerate(info_str):
    #     img.paste(get_tile_from_font(font, ord(char)), (i * SD_TILE_WIDTH, 0))

    img = img.resize((1280, 720) if wide else (960, 720), Image.Resampling.BICUBIC)

    return img


def main(args: Args):
    logging.basicConfig(level=logging.DEBUG)

    if args.hd:
        font = Font(f"{args.font}_hd", is_hd=True)
    else:
        font = Font(args.font, is_hd=False)

    video_path = pathlib.PurePath(args.video)
    video_stem = video_path.stem
    osd_path = video_stem + ".osd"
    out_path = video_stem + "_with_osd.mp4"

    logger.info("loading OSD dump from %s", osd_path)

    frames = []
    with open(osd_path, "rb") as dump_f:
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        logger.info("rendering %d frames", len(frames))

        for i, frame in enumerate(frames):
            osd_img = draw_frame(font, frame, i, args.hd, args.wide)

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
        video = ffmpeg.input(video_path)
        (
            video.overlay(frame_overlay, x=0, y=0)
            .output(out_path)
            .run(overwrite_output=True)
        )


class Args(argparse.Namespace):
    font: str
    hd: bool
    wide: bool
    video: str


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--font", type=str, default="font", help='font basename e.g. "font"'
    )
    parser.add_argument(
        "--wide", action="store_true", default=False, help="is this a 16:9 video?"
    )
    parser.add_argument(
        "--hd", action="store_true", default=False, help="is this an HD OSD recording?"
    )
    parser.add_argument("video", type=str, help="video file e.g. DJIG0007.mp4")
    args = cast(Args, parser.parse_args())

    main(args)
