from textwrap import indent
from typing import Any, Literal, Optional, Union
from typing_extensions import Self, TypeAlias

from cookit.pyd import field_validator, model_validator, type_dump_python
from pydantic import BaseModel, ValidationError

SkiaTextAlignType: TypeAlias = Literal[
    "center", "end", "justify", "left", "right", "start"  # noqa: COM812
]
SkiaFontStyleType: TypeAlias = Literal["bold", "bold_italic", "italic", "normal"]
RGBAColorTuple: TypeAlias = tuple[int, int, int, int]

MANIFEST_FILENAME = "manifest.json"
CHECKSUM_FILENAME = "checksum.json"
HUB_MANIFEST_FILENAME = "manifest.json"
CONFIG_FILENAME = "config.json"


class FileSourceGitHubBase(BaseModel):
    type: Literal["github"] = "github"
    owner: str
    repo: str
    path: Optional[str] = None


class FileSourceGitHubBranch(FileSourceGitHubBase):
    branch: str


class FileSourceGitHubTag(FileSourceGitHubBase):
    tag: str


FileSourceGitHub: TypeAlias = Union[FileSourceGitHubBranch, FileSourceGitHubTag]


class FileSourceURL(BaseModel):
    type: Literal["url"] = "url"
    url: str


FileSource: TypeAlias = Union[
    FileSourceGitHubBranch,
    FileSourceGitHubTag,
    FileSourceURL,
]


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


class StickerInfo(BaseModel):
    name: str
    category: str
    params: StickerParamsOptional


class StickerExternalFont(BaseModel):
    path: str


class StickerPackConfig(BaseModel):
    update_source: Optional[FileSource] = None
    commands: Optional[list[str]] = None
    extend_commands: list[str] = []
    disable_category_select: Optional[bool] = None


class StickerPackConfigMerged(BaseModel):
    update_source: Optional[FileSource] = None
    commands: list[str] = []
    extend_commands: list[str] = []
    disable_category_select: bool = False


def merge_ensure_sticker_params(*params: StickerParamsOptional) -> StickerParams:
    kw: dict[str, Any] = {}
    for param in params:
        kw.update(type_dump_python(param, exclude_defaults=True))
    return StickerParams(**kw)


class StickerPackManifest(BaseModel):
    version: int
    name: str
    description: str
    external_fonts: list[StickerExternalFont] = []
    default_config: StickerPackConfig = StickerPackConfig()
    default_sticker_params: StickerParamsOptional = StickerParamsOptional()
    stickers: list[StickerInfo]

    @field_validator("name")
    def validate_name(cls, value: str) -> str:  # noqa: N805
        if not value:
            raise ValueError("Name must not be empty")
        return value

    @model_validator(mode="after")
    def validate_stickers(self) -> Self:
        for idx, sticker in enumerate(self.stickers):
            try:
                merge_ensure_sticker_params(self.default_sticker_params, sticker.params)
            except ValidationError as e:
                info = indent(str(e), "    ")
                raise ValueError(f"Sticker {idx} validation failed\n{info}") from e
        return self


ChecksumDict: TypeAlias = dict[str, str]
OptionalChecksumDict: TypeAlias = dict[str, Optional[str]]

StickersHubFileSource = FileSourceGitHubBranch(
    owner="lgc-NB2Dev",
    repo="meme-stickers-hub",
    branch="main",
    path=HUB_MANIFEST_FILENAME,
)


class HubStickerPackInfo(BaseModel):
    slug: str
    source: FileSource


HubManifest: TypeAlias = list[HubStickerPackInfo]
