import struct
import logging
from PIL import Image, ImageDraw

TILE_WIDTH = 12 * 3
TILE_HEIGHT = 18 * 3

MAX_DISPLAY_X = 50
MAX_DISPLAY_Y = 18
FRAME_SIZE = MAX_DISPLAY_X * MAX_DISPLAY_Y

frame_struct = struct.Struct(f"<QB{FRAME_SIZE}B")
logger = logging.getLogger(__name__)


def get_tile_from_font(font: Image.Image, char):
    return font.crop(
        (
            0,
            char * TILE_HEIGHT,
            TILE_WIDTH,
            char * TILE_HEIGHT + TILE_HEIGHT,
        )
    )


def draw_frame(font, frame, frame_index) -> Image.Image:
    timestamp = frame[0]
    is_hd = frame[1]
    frame_data = frame[2:]

    display_width = 31 if is_hd else 30
    display_height = 18 if is_hd else 15

    img = Image.new("RGBA", (display_width * TILE_WIDTH, display_height * TILE_HEIGHT))

    for y in range(display_height):
        for x in range(display_width):
            char = frame_data[y * MAX_DISPLAY_X + x]
            tile = get_tile_from_font(font, char)
            img.paste(tile, (x * TILE_WIDTH, y * TILE_HEIGHT))

    info_str = f"{frame_index}:{timestamp / 1000}"
    for i, char in enumerate(info_str):
        img.paste(get_tile_from_font(font, ord(char)), (i * TILE_WIDTH, 0))

    return img


def main():
    logging.basicConfig(level=logging.DEBUG)

    font = Image.open("font.png")
    still = Image.open("still.png")

    frames = []
    with open("osd_dump_20220923T002554.bin", "rb") as dump_f:
        while frame := dump_f.read(frame_struct.size):
            try:
                frame = frame_struct.unpack(frame)
                frames.append(frame)
            except struct.error as e:
                logger.error("%s at byte %d", e, dump_f.tell())

    logger.info("Loaded %d frames", len(frames))
    for i, frame in enumerate(frames):
        print(i, frame[0])

    imgs = []
    for i, frame in enumerate(frames):
        osd_img = draw_frame(font, frame, i)
        still_img = still.copy()
        still_img.paste(osd_img, (0, 0), osd_img)
        imgs.append(still_img)

    durations = []
    for i in range(len(imgs) - 1):
        durations.append(frames[i + 1][0] - frames[i][0])

    imgs[0].save(
        "msp-osd.gif",
        save_all=True,
        append_images=imgs[1:],
        duration=[0] + durations,
    )


if __name__ == "__main__":
    main()
