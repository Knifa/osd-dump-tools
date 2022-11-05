import os
from PIL import Image

from .const import *
from .font import Font
from .frame import Frame
from .config import Config

def draw_frame(font: Font, frame: Frame, args: Config) -> Image.Image:
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

            # if char == 3:
            #     tile = font[ord('Y')]
            # if char == 4:
            #     tile = font[ord('Z')]
            # if char == 118:
            #     tile = font[ord('A')]
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

def render_single_frame(font: Font, tmp_dir: str, cfg: Config, frame: Frame) -> None:
    #print(f'dir {tmp_dir}, frame idx: {frame.idx}', flush=True)

    osd_img = draw_frame(
        font=font,
        frame=frame,
        args=cfg
    )

    fname = f"{tmp_dir}/{frame.idx:016}.png"
    osd_img.save(fname)

    next_frame_idx = frame.next_idx

    if next_frame_idx != 0:
        for j in range(frame.idx + 1, next_frame_idx):
            lfname = f"{tmp_dir}/{j:016}.png"
            if cfg.nolinks:
                osd_img.save(lfname)
            else:
                os.symlink(fname, lfname)

    return frame.idx

def f_test(n, frame):
    print(f'frame idx: {frame.idx} n={n}', flush=True)
    return f'frame idx: {frame.idx}'
