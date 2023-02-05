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

from .render import render_test_frame, render_single_frame
from .frame import Frame
from .font import Font
from .const import CONFIG_FILE_NAME, OSD_TYPE_DJI, OSD_TYPE_WS, FW_ARDU, FW_INAV, FW_BETAFL, FW_UNKNOWN
from .config import Config, ExcludeArea


MIN_START_FRAME_NO: int = 20
WS_VIDEO_FPS = 60

file_header_struct_detect = struct.Struct("<4s")
# < little-endian
# 4s string

file_header_struct_ws = struct.Struct("<4s36B")
# < little-endian
# 4s string
# 36B unsigned char

frame_header_struct_ws = struct.Struct("<L1060H")
# < little-endian
# L unsigned long
# 1060H unsigned short

file_header_struct_dji = struct.Struct("<7sH4B2HB") 
# < little-endian
# 7s string
# H unsigned short
# 4B unsigned char
# 2H unsigned short
# B unsigned char
frame_header_struct_dji = struct.Struct("<II")
# < little-endian
# I unsigned int
# I unsigned int

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
        "--verbatim", action="store_true", default=None, help="Display detailed information"
    )

    parser.add_argument(
        "--singlecore", action="store_true", default=None, help="Run on single procesor core (slow)"
    )

    parser.add_argument(
        "--ardu", action="store_true", default=None, help="Hide gps/alt for ArduPilot"
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

def get_min_frame_idx(frames: list[Frame]) -> int:
    # frames idxes are in increasing order for most of time :)

    for i in range(len(frames)):
        n1 = frames[i].idx
        n2 = frames[i+1].idx
        if n1 < n2:
            return n1

    raise ValueError("Frames are in wrong order")

def detect_system(osd_path: pathlib.Path, verbatim: bool = False) -> tuple :
    with open(osd_path, "rb") as dump_f:
        file_header_data = dump_f.read(file_header_struct_detect.size)
        file_header = file_header_struct_detect.unpack(file_header_data)

        if file_header[0] == b'MSPO':
            return OSD_TYPE_DJI, FW_UNKNOWN
        if file_header[0] == b'INAV':
            return OSD_TYPE_WS, FW_INAV
        if file_header[0] == b'BTFL':
            return OSD_TYPE_WS, FW_BETAFL
        if file_header[0] == b'ARDU':
            return OSD_TYPE_WS, FW_ARDU

        print(f"{osd_path} has an invalid file header")
        sys.exit(1)



def read_ws_osd_frames(osd_path: pathlib.Path, verbatim: bool = False) -> list[Frame]:
    frames_per_ms = (1 / WS_VIDEO_FPS) * 1000
    frames: list[Frame] = []

    with open(osd_path, "rb") as dump_f:
        file_header_data = dump_f.read(file_header_struct_ws.size)
        file_header = file_header_struct_ws.unpack(file_header_data)

        if verbatim:
            print(f"system:    {file_header[0].decode('ascii')}")

        while True:
            frame_header = dump_f.read(frame_header_struct_ws.size)
            if len(frame_header) == 0:
                break

            frame = frame_header_struct_ws.unpack(frame_header)
            osd_time = frame[0]
            frame_idx = int(osd_time // frames_per_ms)
            frame_data = frame[1:]

            if len(frames) > 0 and frames[-1].idx == frame_idx:
                print(f'Duplicate frame: {frame_idx}')
                continue

            if len(frames) > 0:
                frames[-1].next_idx = frame_idx

            frames.append(Frame(frame_idx, 0, frame_header_struct_ws.size, frame_data))

    return frames


def read_dji_osd_frames(osd_path: pathlib.Path, verbatim: bool = False) -> list[Frame]:
    frames: list[Frame] = []

    with open(osd_path, "rb") as dump_f:
        file_header_data = dump_f.read(file_header_struct_dji.size)
        file_header = file_header_struct_dji.unpack(file_header_data)

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
            frame_header = dump_f.read(frame_header_struct_dji.size)
            if len(frame_header) == 0:
                break

            frame_head = frame_header_struct_dji.unpack(frame_header)
            frame_idx, frame_size = frame_head

            frame_data_struct = struct.Struct(f"<{frame_size}H")
            frame_data = dump_f.read(frame_data_struct.size)
            frame_data = frame_data_struct.unpack(frame_data)

            if len(frames) > 0 and frames[-1].idx == frame_idx:
                print(f'Duplicate frame: {frame_idx}')
                continue

            if len(frames) > 0:
                frames[-1].next_idx = frame_idx

            frames.append(Frame(frame_idx, 0, frame_size, frame_data))

    # remove initial random frames
    start_frame = get_min_frame_idx(frames)

    if start_frame > MIN_START_FRAME_NO:
        print(f'Wrong idx of initial frame {start_frame}, abort')
        raise ValueError(f'Wrong idx of initial frame {start_frame}, abort')

    return frames[start_frame:]


def render_frames(frames: list[Frame], font: Font, tmp_dir: str, cfg: Config, osd_type: int) -> None:
    print(f"rendering {len(frames)} frames")

    renderer = partial(render_single_frame, font, tmp_dir, cfg, osd_type)

    for i in range(len(frames)-1):
        if frames[i].next_idx != frames[i+1].idx:
            print(f'incorrect frame {frames[i].next_idx}')


    if cfg.singlecore:
        for frame in tqdm(frames):
            renderer(frame)

        return

    with Pool() as pool:
        queue = pool.imap_unordered(renderer, tqdm(frames))

        for _ in queue:
            pass


def run_ffmpeg(start_number: int, bitrate: int, osd_type: int, image_dir: str, video_path: pathlib.Path, out_path: pathlib.Path):
    frame_overlay = ffmpeg.input(f"{image_dir}/%016d.png", start_number=start_number, framerate=60, thread_queue_size=2048)
    video = ffmpeg.input(str(video_path), thread_queue_size=2048)
    # TODO: video.global_args('-hwaccel')

    # TODO: this is calculated in too many places    
    if osd_type == OSD_TYPE_WS:
        out_size = {"w": 1920, "h": 1080}
    elif args.fakehd or args.hd or args.wide:
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

    print(f"verbatim:  {args.verbatim}")
    print(f"loading OSD dump from:  {osd_path}")

    osd_type, _ = detect_system(osd_path)

    if osd_type == OSD_TYPE_DJI:
        frames = read_dji_osd_frames(osd_path, args.verbatim)
    else:
        frames = read_ws_osd_frames(osd_path, args.verbatim)

    if args.testrun:
        test_path = str(video_path.with_name('test_image.png'))
        print(f"test frame created: {test_path}")
        render_test_frame(
            font=font,
            frame=frames[args.testframe],
            cfg=args, 
            osd_type=osd_type
        ).save(test_path)

        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        render_frames(frames, font, tmp_dir, args, osd_type)

        print(f"passing to ffmpeg, out as {out_path}")

        start_number = frames[0].idx
        run_ffmpeg(start_number, args.bitrate, osd_type, tmp_dir, video_path, out_path)


if __name__ == "__main__":
    cfg = ConfigParser()
    cfg.read(pathlib.PurePath(__file__).parent / CONFIG_FILE_NAME)
    cfg.read(CONFIG_FILE_NAME)

    parser = build_cmd_line_parser()

    args = Config(cfg)
    args.merge_cfg(parser.parse_args())

    if os.name == 'nt':
        # TODO: try to create symlink and set nolinks flag
        import ctypes
        adm = ctypes.windll.shell32.IsUserAnAdmin()
        if not adm and not args.nolinks and not args.testrun:
            print('To run you need priviledged shell. Check --nolinks option. Terminating.')
            sys.exit(1)

    main(args)
