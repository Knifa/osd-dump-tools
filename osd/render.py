#from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path

from PIL import Image

from .const import HD_TILE_WIDTH, SD_TILE_WIDTH, HD_TILE_HEIGHT, SD_TILE_HEIGHT, OSD_TYPE_DJI
from .font import Font
from .frame import Frame
from .config import Config
from .utils.ro_cls import read_only_class


@read_only_class
class ArduParams:
    LAT_CHAR_CODE: int = 167
    LON_CHAR_CODE: int = 166
    ALT_CHAR_CODE: int = 177
    HOME_CHAR_CODE: int = 191

    ALT_LEN: int = 4
    GPS_LEN: int = 12
    HOME_LEN: int = 6

@read_only_class
class InavParams:
    LAT_CHAR_CODE: int = 3
    LON_CHAR_CODE: int = 4
    ALT_CHAR_CODE: int = 118
    HOME_CHAR_CODE: int = 16

    ALT_LEN: int = 4
    GPS_LEN: int = 9
    HOME_LEN: int = 5


INTERNAL_W_H_DJI = (60, 22)
INTERNAL_W_H_WS = (53, 20)


def _get_display_dims(cfg: Config, osd_type: int) -> tuple[int, int]:
    if cfg.fakehd:
        return (60, 22)

    if cfg.hd:
        return (50, 18)

    return (30, 15)


@dataclass
class HiddenItemsCache():
    gps_lat: tuple[int, int] | None = None
    gps_lon: tuple[int, int] | None = None
    alt: tuple[int, int] | None = None
    dist: tuple[int, int] | None = None

_items_cache = HiddenItemsCache() 

def hide_items(img: Image, font: Font, exclusions, masking_tile, tile_width, tile_height) -> None:
    if _items_cache.gps_lat:
        for i in range(exclusions.GPS_LEN + 1):
            x = (_items_cache.gps_lat[0] + i) * tile_width
            y = _items_cache.gps_lat[1] * tile_height
            img.paste(masking_tile, (x , y,), )

    if _items_cache.gps_lon:
        for i in range(exclusions.GPS_LEN + 1):
            x = (_items_cache.gps_lon[0] + i) * tile_width
            y = _items_cache.gps_lon[1] * tile_height
            img.paste(masking_tile, (x , y,), )

    if _items_cache.alt:
        for i in range(exclusions.ALT_LEN + 1):
            x = (_items_cache.alt[0] - i) * tile_width
            y = _items_cache.alt[1] * tile_height
            img.paste(masking_tile, (x , y,), )

    if _items_cache.dist:
        for i in range(exclusions.HOME_LEN + 1):
            x = (_items_cache.dist[0] + i) * tile_width
            y = _items_cache.dist[1] * tile_height
            img.paste(masking_tile, (x , y,), )


def draw_frame(font: Font, frame: Frame, cfg: Config, osd_type, exclusions) -> Image.Image:
    if osd_type == OSD_TYPE_DJI:
        internal_width, internal_height = INTERNAL_W_H_DJI
        char_reader = lambda x, y: frame.data[y + x * internal_height]
        display_width, display_height = _get_display_dims(cfg, osd_type)

    else:
        internal_width, internal_height = INTERNAL_W_H_WS
        display_width, display_height = INTERNAL_W_H_WS
        char_reader = lambda x, y: frame.data[x + y * internal_width]

    tile_width = (HD_TILE_WIDTH if cfg.hd or cfg.fakehd else SD_TILE_WIDTH)
    tile_height = (HD_TILE_HEIGHT if cfg.hd or cfg.fakehd else SD_TILE_HEIGHT)

    img = Image.new(
        "RGBA",
        (
            display_width  * tile_width,
            display_height * tile_height,
        ),
    )

    gps_lat: tuple[int, int] | None = None
    gps_lon: tuple[int, int] | None = None
    alt: tuple[int, int] | None = None

    masking_font_no = ord(' ')
    if cfg.testrun:
        masking_font_no = ord('X')

    masking_tile = font[masking_font_no]

    for y in range(internal_height):
        for x in range(internal_width):
            char = char_reader(x, y)
            tile = font[char]

            if cfg.exclude_area.is_excluded(x, y):
                tile = masking_tile

            if cfg.hide_gps:
                if char == exclusions.LAT_CHAR_CODE:
                    gps_lat = (x, y)
                    _items_cache.gps_lat = (x, y)
                    
                elif char == exclusions.LON_CHAR_CODE:
                    gps_lon = (x, y)
                    _items_cache.gps_lon = (x, y)

            if cfg.hide_alt and char == exclusions.ALT_CHAR_CODE:
                alt = (x, y)
                _items_cache.alt = (x, y)

            if cfg.hide_dist and char == exclusions.HOME_CHAR_CODE:
                alt = (x, y)
                _items_cache.dist = (x, y)

            img.paste(tile, (x * tile_width, y * tile_height,), )

    # hide gps/alt data
    # if any of items was present on frame we will use cache to be sure that all are deleted
    if gps_lat or gps_lon or alt:
        hide_items(img, font, exclusions, masking_tile, tile_width, tile_height)

    if osd_type != OSD_TYPE_DJI:
        img_size = (1920, 1080)
    elif cfg.fakehd or cfg.hd or cfg.wide:
        img_size = (1280, 720)
    else:
        img_size = (960, 720)

    img = img.resize(img_size, Image.Resampling.LANCZOS)

    return img

def render_single_frame(font: Font, tmp_dir: str, cfg: Config, osd_type, frame: Frame) -> None:
    exclusions = InavParams
    if cfg.ardu:
        exclusions = ArduParams

    osd_img = draw_frame(
        font=font,
        frame=frame,
        cfg=cfg,
        osd_type=osd_type,
        exclusions=exclusions,
    )

    fname = f"{tmp_dir}/{frame.idx:016}.png"
    osd_img.save(fname)

    next_frame_idx = frame.next_idx

    if next_frame_idx != 0:
        for j in range(frame.idx + 1, next_frame_idx):
            lfname = f"{tmp_dir}/{j:016}.png"
            if Path(lfname).is_file() and cfg.verbatim:
                print(f'File already exists: {lfname}, skipped')
                continue

            if cfg.nolinks:
                osd_img.save(lfname)
            else:
                os.symlink(fname, lfname)


def render_test_frame(font: Font, frame: Frame, cfg: Config, osd_type) -> None:
    exclusions = InavParams
    if cfg.ardu:
        exclusions = ArduParams

    osd_img = draw_frame(
        font=font,
        frame=frame,
        cfg=cfg,
        osd_type=osd_type,
        exclusions=exclusions,
    )

    return osd_img

