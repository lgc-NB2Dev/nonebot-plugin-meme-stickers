from contextlib import contextmanager, suppress
from textwrap import indent
from typing import Any, Optional, TypeVar, Union
from typing_extensions import Self, TypeAlias

from cookit import deep_merge
from cookit.pyd import (
    field_validator,
    model_validator,
    type_dump_python,
    type_validate_python,
)
from pydantic import BaseModel, PrivateAttr, ValidationError

from ..consts import (
    RGBAColorTuple,
    SkiaFontStyleType,
    SkiaTextAlignType,
    StickerGridGapType,
    StickerGridPaddingType,
    TRBLPaddingTuple,
    XYGapTuple,
)
from ..utils.file_source import FileSource

T = TypeVar("T")


def validate_not_falsy(cls: BaseModel, value: T) -> T:  # noqa: ARG001
    if not value:
        raise ValueError("value cannot be empty")
    return value


@contextmanager
def wrap_validation_error(msg: str):
    try:
        yield
    except ValidationError as e:
        info = indent(str(e), "    ")
        raise ValueError(f"{msg}\n{info}") from e


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


class StickerInfoOptionalParams(BaseModel):
    name: str
    category: str
    params: StickerParamsOptional

    _validate_not_falsy = field_validator("name", "category")(validate_not_falsy)


class StickerInfo(BaseModel):
    name: str
    category: str
    params: StickerParams


class StickerExternalFont(BaseModel):
    path: str


class StickerPackConfig(BaseModel):
    update_source: Optional[FileSource] = None
    disabled: bool = False
    commands: list[str] = []
    extend_commands: list[str] = []


class StickerGridParams(BaseModel):
    padding: StickerGridPaddingType = 16
    gap: StickerGridGapType = 16
    rows: Optional[int] = None
    cols: Optional[int] = 5
    background: Union[RGBAColorTuple, str] = (40, 44, 52, 255)
    sticker_size_fixed: Optional[tuple[int, int]] = None

    @model_validator(mode="after")
    def validate_rows_cols(self):
        if (self.rows and self.cols) or ((self.rows is None) and (self.cols is None)):
            raise ValueError("Either rows or cols must be None")
        return self

    @property
    def resolved_padding(self) -> TRBLPaddingTuple:
        if isinstance(self.padding, (int, float)):
            return ((p := self.padding), p, p, p)
        if len(self.padding) == 1:
            return ((p := self.padding[0]), p, p, p)
        if len(self.padding) == 2:
            x, y = self.padding
            return (x, y, x, y)
        return self.padding

    @property
    def resolved_gap(self) -> XYGapTuple:
        if isinstance(self.gap, (int, float)):
            return ((g := self.gap), g)
        if len(self.gap) == 1:
            return ((g := self.gap[0]), g)
        return self.gap


class StickerGridSetting(BaseModel):
    disable_category_select: bool = False
    default_params: StickerGridParams = StickerGridParams()
    category_override_params: StickerGridParams = StickerGridParams()
    stickers_override_params: dict[str, StickerGridParams] = {}

    _resolved_category_params: StickerGridParams = PrivateAttr(StickerGridParams())
    _resolved_stickers_params: dict[str, StickerGridParams] = PrivateAttr({})

    @property
    def resolved_category_params(self) -> StickerGridParams:
        return self._resolved_category_params

    @property
    def resolved_stickers_params(self) -> dict[str, StickerGridParams]:
        return self._resolved_stickers_params

    @model_validator(mode="after")
    def validate_resolve_overrides(self) -> Self:
        with wrap_validation_error("category_select_override_params validation failed"):
            self._resolved_category_params = type_validate_python(
                StickerGridParams,
                deep_merge(
                    type_dump_python(self.default_params, exclude_unset=True),
                    type_dump_python(
                        self.category_override_params,
                        exclude_unset=True,
                    ),
                ),
            )
        for category, params in self.stickers_override_params.items():
            with wrap_validation_error(
                f"category {category} overridden StickerGridSetting validation failed",
            ):
                self._resolved_stickers_params[category] = type_validate_python(
                    StickerGridParams,
                    deep_merge(
                        type_dump_python(self.default_params, exclude_unset=True),
                        type_dump_python(params, exclude_unset=True),
                    ),
                )
        return self


def merge_ensure_sticker_params(*params: StickerParamsOptional) -> StickerParams:
    kw: dict[str, Any] = {}
    for param in params:
        kw.update(type_dump_python(param, exclude_defaults=True))
    return StickerParams(**kw)


class StickerPackManifest(BaseModel):
    version: int
    name: str
    description: str
    default_config: StickerPackConfig = StickerPackConfig()
    default_sticker_params: StickerParamsOptional = StickerParamsOptional()
    sticker_grid: StickerGridSetting = StickerGridSetting()
    sample_sticker: Union[StickerInfoOptionalParams, str, int, None] = None
    external_fonts: list[StickerExternalFont] = []
    stickers: list[StickerInfoOptionalParams]

    _resolved_stickers: list[StickerInfo] = PrivateAttr([])
    _resolved_sample_sticker: Optional[StickerParams] = PrivateAttr(None)

    @property
    def resolved_stickers(self) -> list[StickerInfo]:
        return self._resolved_stickers

    @property
    def resolved_sample_sticker(self) -> StickerParams:
        return self._resolved_sample_sticker or self.resolved_stickers[0].params

    @property
    def resolved_stickers_by_category(self) -> dict[str, list[StickerInfo]]:
        categories = list({x.category for x in self.resolved_stickers})
        return {
            c: [x for x in self.resolved_stickers if x.category == c]
            for c in categories
        }

    def resolve_sticker_params(self, *args: StickerParamsOptional) -> StickerParams:
        return merge_ensure_sticker_params(self.default_sticker_params, *args)

    def find_sticker_by_name(self, name: str) -> Optional[StickerInfo]:
        return next(
            (x for x in self.resolved_stickers if x.name == name),
            None,
        )

    def find_sticker(self, query: Union[str, int]) -> Optional[StickerInfo]:
        if isinstance(query, str) and (not query.isdigit()):
            return self.find_sticker_by_name(query)
        with suppress(IndexError):
            return self.resolved_stickers[int(query)]
        return None

    _validate_not_falsy = field_validator("name")(validate_not_falsy)

    @model_validator(mode="after")
    def _validate_resolve_stickers(self) -> Self:
        def validate_info(sticker: StickerInfoOptionalParams) -> StickerInfo:
            return type_validate_python(
                StickerInfo,
                {
                    **type_dump_python(sticker, exclude={"params"}),
                    "params": self.resolve_sticker_params(sticker.params),
                },
            )

        resolved_stickers: list[StickerInfo] = []
        for idx, x in enumerate(self.stickers):
            with wrap_validation_error(f"Sticker {idx} validation failed"):
                resolved_stickers.append(validate_info(x))
        self._resolved_stickers = resolved_stickers

        if not self.sample_sticker:
            self._resolved_sample_sticker = self.resolved_stickers[0].params
        elif isinstance(self.sample_sticker, StickerInfoOptionalParams):
            with wrap_validation_error("Sample sticker validation failed"):
                self._resolved_sample_sticker = self.resolve_sticker_params(
                    self.sample_sticker.params,
                )
        else:
            it = self.find_sticker(self.sample_sticker)
            if it is None:
                raise ValueError(f"Sample sticker `{self.sample_sticker}` not found")
            self._resolved_sample_sticker = it.params

        return self


ChecksumDict: TypeAlias = dict[str, str]
OptionalChecksumDict: TypeAlias = dict[str, Optional[str]]


class HubStickerPackInfo(BaseModel):
    slug: str
    source: FileSource


HubManifest: TypeAlias = list[HubStickerPackInfo]


def zoom_sticker(
    params: StickerParams,
    zoom: float,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> StickerParams:
    params.width = width or round(params.width * zoom)
    params.height = height or round(params.height * zoom)
    params.text_x *= zoom
    params.text_y *= zoom
    params.font_size *= zoom
    return params
