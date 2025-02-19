import re
from typing import Literal, Union
from typing_extensions import TypeAlias

SkiaTextAlignType: TypeAlias = Literal[
    "center", "end", "justify", "left", "right", "start",
]  # fmt: skip
SkiaFontStyleType: TypeAlias = Literal["bold", "bold_italic", "italic", "normal"]
SkiaEncodedImageFormatType: TypeAlias = Literal["jpeg", "png", "webp"]
RGBAColorTuple: TypeAlias = tuple[int, int, int, int]
TRBLPaddingTuple: TypeAlias = tuple[float, float, float, float]
StickerGridPaddingType: TypeAlias = Union[
    float,  # t r b l
    tuple[float],  # (t r b l)
    tuple[float, float],  # (t b, l r)
    tuple[float, float, float, float],  # (t, r, b, l)
]
XYGapTuple: TypeAlias = tuple[float, float]
StickerGridGapType: TypeAlias = Union[
    float,  # x and y
    tuple[float],  # (x and y)
    tuple[float, float],  # (x, y)
]

NAME = "Meme Stickers"
DESCRIPTION = "一站式制作 PJSK 样式表情包"
AUTHOR = "LgCookie"

RELATIVE_INT_PARAM = r"re:\^?(\+-)?\d+"
RELATIVE_FLOAT_PARAM = r"re:\^?(\+-)?\d+(\.\d+)?"

MANIFEST_FILENAME = "manifest.json"
CHECKSUM_FILENAME = "checksum.json"
HUB_MANIFEST_FILENAME = "manifest.json"
CONFIG_FILENAME = "config.json"
UPDATING_FLAG_FILENAME = ".updating"
PREVIEW_CACHE_DIR_NAME = "_cache/preview"

SHORT_HEX_COLOR_REGEX = re.compile(r"#?(?P<hex>[0-9a-fA-F]{3,4})")
FULL_HEX_COLOR_REGEX = re.compile(r"#?(?P<hex>([0-9a-fA-F]{3,4}){2})")
FLOAT_REGEX = re.compile(r"\d+(\.\d+)?")
