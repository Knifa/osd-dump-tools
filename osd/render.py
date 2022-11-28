from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from .const import HD_TILE_WIDTH, SD_TILE_WIDTH, HD_TILE_HEIGHT, SD_TILE_HEIGHT
from .font import Font
from .frame import Frame
from .config import Config

LAT_CHAR_CODE = 3
LON_CHAR_CODE = 4
ALT_CHAR_CODE = 118

ALT_LEN = 4
GPS_LEN = 9


def draw_frame(font: Font, frame: Frame, cfg: Config) -> Image.Image:
    internal_width = 60
    internal_height = 22

    if cfg.fakehd:
        display_width = 60
        display_height = 22
    elif cfg.hd:
        display_width = 50
        display_height = 18
    else:
        display_width = 30
        display_height = 15

    img = Image.new(
        "RGBA",
        (
            display_width * (HD_TILE_WIDTH if cfg.hd or cfg.fakehd else SD_TILE_WIDTH),
            display_height
            * (HD_TILE_HEIGHT if cfg.hd or cfg.fakehd else SD_TILE_HEIGHT),
        ),
    )

    gps_lat: tuple[int, int] | None = None
    gps_lon: tuple[int, int] | None = None
    alt: tuple[int, int] | None = None
    tile_width = (HD_TILE_WIDTH if cfg.hd or cfg.fakehd else SD_TILE_WIDTH)
    tile_height = (HD_TILE_HEIGHT if cfg.hd or cfg.fakehd else SD_TILE_HEIGHT)

    for y in range(internal_height):
        for x in range(internal_width):
            char = frame.data[y + x * internal_height]
            tile = font[char]

            if cfg.exclude_area.is_excluded(x, y):
                font_no = ord(' ')
                if cfg.testrun:
                    font_no = ord('X')

                tile = font[font_no]

            if cfg.hide_gps:
                if char == LAT_CHAR_CODE:
                    gps_lat = (x, y)
                elif char == LON_CHAR_CODE:
                    gps_lon = (x, y)

            if cfg.hide_alt and char == ALT_CHAR_CODE:
                alt = (x, y)

            img.paste(tile, (x * tile_width, y * tile_height,), )

    # hide gps/alt data
    if gps_lat and gps_lon:
        tile = font[0]
        for i in range(GPS_LEN + 1):
            x = (gps_lat[0] + i) * tile_width
            y = gps_lat[1] * tile_height
            img.paste(tile, (x , y,), )
            x = (gps_lon[0] + i) * tile_width
            y = gps_lon[1] * tile_height
            img.paste(tile, (x , y,), )

    if alt:
        tile = font[0]
        for i in range(ALT_LEN + 1):
            x = (alt[0] - i) * tile_width
            y = alt[1] * tile_height
            img.paste(tile, (x , y,), )

    if cfg.fakehd or cfg.hd or cfg.wide:
        img_size = (1280, 720)
    else:
        img_size = (960, 720)

    img = img.resize(img_size, Image.Resampling.BICUBIC)

    return img


def render_single_frame(font: Font, tmp_dir: str, cfg: Config, frame: Frame) -> None:
    osd_img = draw_frame(
        font=font,
        frame=frame,
        cfg=cfg
    )

    fname = f"{tmp_dir}/{frame.idx:016}.png"
    osd_img.save(fname)

    next_frame_idx = frame.next_idx

    if next_frame_idx != 0:
        for j in range(frame.idx + 1, next_frame_idx):
            lfname = f"{tmp_dir}/{j:016}.png"
            if Path(lfname).is_file and cfg.verbatim:
                print(f'File already exists: {lfname}, skipped')
                continue

            if cfg.nolinks:
                osd_img.save(lfname)
            else:
                os.symlink(fname, lfname)
