from __future__ import annotations

from functools import partial
from multiprocessing import Pool
import argparse
import os
import pathlib
import struct
import sys
import tempfile
from configparser import ConfigParser

import ffmpeg

from tqdm import tqdm

from .render import draw_frame, render_single_frame
from .frame import Frame
from .font import Font
from .const import CONFIG_FILE_NAME
from .config import Config, ExcludeArea


file_header_struct = struct.Struct("<7sH4B2HB")
frame_header_struct = struct.Struct("<II")


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
        "--hide_gps", action="store_true", default=None, help="Don't render GPS coords. Works on iNav."
    )

    parser.add_argument(
        "--hide_alt", action="store_true", default=None, help="Don't render GPS coords. Works on iNav."
    )

    parser.add_argument(
        "--testrun", action="store_true", default=False, help="Create overlay with osd data in video location and ends"
    )

    parser.add_argument(
        "--testframe", type=int, default=-1, help="Osd data frame for testrun"
    )

    parser.add_argument(
        "--verbatim", action="store_true", default=False, help="Display detailed information"
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


def read_osd_frames(osd_path: pathlib.Path, verbatim: bool = False) -> list[Frame]:
    frames: list[Frame] = []

    with open(osd_path, "rb") as dump_f:
        file_header_data = dump_f.read(file_header_struct.size)
        file_header = file_header_struct.unpack(file_header_data)

        if file_header[0] != b"MSPOSD\x00":
            print(f"{osd_path} has an invalid file header")
            sys.exit(1)

        if verbatim:
            print(f"file header:    {file_header[0].decode('ascii')}")
            print(f"file version:   {file_header[1]}")
            print(f"char width:     {file_header[2]}")
            print(f"char height:    {file_header[3]}")
            print(f"font widtht:    {file_header[4]}")
            print(f"font height:    {file_header[5]}")
            print(f"x offset:       {file_header[6]}")
            print(f"y offset:       {file_header[7]}")
            print(f"font variant:   {file_header[8]}")

        while True:
            frame_header = dump_f.read(frame_header_struct.size)
            if len(frame_header) == 0:
                break

            frame_head = frame_header_struct.unpack(frame_header)
            frame_idx, frame_size = frame_head

            frame_data_struct = struct.Struct(f"<{frame_size}H")
            frame_data = dump_f.read(frame_data_struct.size)
            frame_data = frame_data_struct.unpack(frame_data)

            if len(frames) > 0:
                frames[-1].next_idx = frame_idx

            frames.append(Frame(frame_idx, 0, frame_size, frame_data))

    return frames


def render_frames(frames: list[Frame], font: Font, tmp_dir: str, cfg: Config) -> None:
    print(f"rendering {len(frames)} frames")

    renderer = partial(render_single_frame, font, tmp_dir, cfg)

    with Pool() as pool:
        queue = pool.imap_unordered(renderer, tqdm(frames))

        for _ in queue:
            pass


def run_ffmpeg(start_number: int, bitrate: int, image_dir: str, video_path: pathlib.Path, out_path: pathlib.Path):
    frame_overlay = ffmpeg.input(f"{image_dir}/%016d.png", start_number=start_number, framerate=60, thread_queue_size=1024)
    video = ffmpeg.input(str(video_path), thread_queue_size=2048)

    if args.fakehd or args.hd or args.wide:
        out_size = {"w": 1280, "h": 720}
    else:
        out_size = {"w": 960, "h": 720}

    output_params = {
        'video_bitrate': f"{bitrate}M",
    }

    # from https://ffmpeg.org/faq.html#Which-are-good-parameters-for-encoding-high-quality-MPEG_002d4_003f
    hq_output = {
        'mbd': 'rd',
        'flags': '+mv4+aic',
        'trellis': 2,
        'cmp': 2,
        'subcmp': 2,
        'g': 300,
        'bf': 2,
    }

    if args.hq:
        output_params.update(hq_output)

    (
        video.filter("scale", **out_size, force_original_aspect_ratio=1)
        .filter("pad", **out_size, x=-1, y=-1, color="black")
        .overlay(frame_overlay, x=0, y=0)
        .output(str(out_path), **output_params)
        .global_args('-loglevel', 'info' if args.verbatim else 'error')
        .global_args('-stats')
        .global_args('-hide_banner')
        .run(overwrite_output=True)
    )


def main(args: Config):
    print(f"loading fonts from: {args.font}")

    if args.hd or args.fakehd:
        font = Font(f"{args.font}_hd", is_hd=True)
    else:
        font = Font(args.font, is_hd=False)

    video_path = pathlib.Path(args.video)
    video_stem = video_path.stem
    osd_path = video_path.with_suffix('.osd')
    out_path = video_path.with_name(video_stem + "_with_osd.mp4")

    print(f"loading OSD dump from:  {osd_path}")

    frames = read_osd_frames(osd_path, args.verbatim)

    if args.testrun:
        test_path = str(video_path.with_name('test_image.png'))
        draw_frame(
            font=font,
            frame=frames[args.testframe],
            cfg=args
        ).save(test_path)

        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        render_frames(frames, font, tmp_dir, args)

        print(f"passing to ffmpeg, out as {out_path}")

        start_number = frames[0].idx
        run_ffmpeg(start_number, args.bitrate, tmp_dir, video_path, out_path)


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
            print('To run you need priviledged shell. Check --nolinks option. Terminating.')
            sys.exit(1)

    main(args)
