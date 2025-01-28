from textwrap import indent
from typing import Literal, Optional
from typing_extensions import Self, TypeAlias

from cookit.pyd import model_validator, type_dump_python
from pydantic import BaseModel, ValidationError

SkiaTextAlignType: TypeAlias = Literal[
    "center", "end", "justify", "left", "right", "start"  # noqa: COM812
]
SkiaFontStyleType: TypeAlias = Literal["bold", "bold_italic", "italic", "normal"]
RGBAColorTuple: TypeAlias = tuple[int, int, int, int]


class StickerParams(BaseModel):
    width: int
    height: int
    base_image: str
    text: str
    text_x: float
    text_y: float
    text_align: SkiaTextAlignType
    text_rotate_degrees: float
    text_color: RGBAColorTuple
    stroke_color: RGBAColorTuple
    stroke_width_factor: float
    font_size: float
    font_style: SkiaFontStyleType
    font_families: list[str]


class StickerParamsOptional(BaseModel):
    width: Optional[int] = None
    height: Optional[int] = None
    base_image: Optional[str] = None
    text: Optional[str] = None
    text_x: Optional[float] = None
    text_y: Optional[float] = None
    text_align: Optional[SkiaTextAlignType] = None
    text_rotate_degrees: Optional[float] = None
    text_color: Optional[RGBAColorTuple] = None
    stroke_color: Optional[RGBAColorTuple] = None
    stroke_width_factor: Optional[float] = None
    font_size: Optional[float] = None
    font_style: Optional[SkiaFontStyleType] = None
    font_families: Optional[list[str]] = None


class StickerExternalFont(BaseModel):
    path: str


class StickerPackManifest(BaseModel):
    version: int
    commands: list[str]
    external_fonts: list[StickerExternalFont] = []
    default_sticker_params: StickerParamsOptional = StickerParamsOptional()
    characters: dict[str, list[StickerParamsOptional]]
    files_sha256: dict[str, str] = {}

    @model_validator(mode="after")
    def validate_stickers(self) -> Self:
        for character, stickers in self.characters.items():
            for idx, sticker in enumerate(stickers):
                try:
                    kw = {
                        **type_dump_python(
                            sticker,
                            exclude_defaults=True,
                        ),
                        **type_dump_python(
                            self.default_sticker_params,
                            exclude_defaults=True,
                        ),
                    }
                    StickerParams(**kw)
                except ValidationError as e:
                    raise ValueError(
                        f"Character {character} sticker {idx} validation failed"
                        f"\n{indent(str(e), '    ')}",
                    ) from e
        return self


MANIFEST_FILENAME = "manifest.json"


class StickerPackConfig(BaseModel):
    update_url: Optional[str] = None
    command_alias: list[str] = []


STICKERS_HUB_MANIFEST_URL = (
    "https://raw.githubusercontent.com/lgc-NB2Dev/meme-stickers-hub"
    "/refs/heads/main/hub_manifest.json"
)


class HubStickerPackInfo(BaseModel):
    name: str
    description: str
    manifest_url: str


HubManifest: TypeAlias = list[HubStickerPackInfo]
