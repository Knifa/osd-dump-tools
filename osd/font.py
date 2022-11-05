from PIL import Image
from .const import *

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

