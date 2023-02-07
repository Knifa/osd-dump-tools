from .utils.ro_cls import read_only_class

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

# TODO: replace with enum
OSD_TYPE_DJI = 1
OSD_TYPE_WS = 2
FW_UNKNOWN = 0
FW_INAV = 1
FW_BETAFL = 2
FW_ARDU = 3

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
