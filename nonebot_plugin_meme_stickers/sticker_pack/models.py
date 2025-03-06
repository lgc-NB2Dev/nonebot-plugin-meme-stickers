from asyncio import InvalidStateError
from contextlib import contextmanager, suppress
from textwrap import indent
from typing import Any, Optional, TypeVar, Union
from typing_extensions import TypeAlias

from cookit import deep_merge
from cookit.pyd import (
    field_validator,
    model_validator,
    type_dump_python,
    type_validate_python,
)
from pydantic import BaseModel, ValidationError

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


def validate_not_falsy(v: T) -> T:  # noqa: ARG001
    if not v:
        raise ValueError("value cannot be empty")
    return v


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

    @field_validator("name", "category")
    @classmethod
    def _validate_not_falsy(cls, v: str) -> str:
        return validate_not_falsy(v)


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
    def _validate_rows_cols(cls, values: dict[str, Any]) -> dict[str, Any]:  # noqa: N805
        rows_exists = "rows" in values
        cols_exists = "cols" in values
        if rows_exists and not cols_exists:
            values["cols"] = None
        rows_have_no_val: Optional[int] = values.get("rows") is None
        cols_have_no_val: Optional[int] = values.get("cols", 5) is None
        if (rows_have_no_val and cols_have_no_val) or (
            (not rows_have_no_val) and (not cols_have_no_val)
        ):
            raise ValueError(
                "Either the 'rows' or the 'cols' parameter must be specified"
                ", but not both.",
            )
        return values

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

    resolved_category_params: StickerGridParams = StickerGridParams()
    resolved_stickers_params: dict[str, StickerGridParams] = {}

    @model_validator(mode="after")
    def _validate_resolve_overrides(cls, values: dict[str, Any]) -> dict[str, Any]:  # noqa: N805
        default_params: StickerGridParams = (
            values.get("default_params") or StickerGridParams()
        )
        category_override_params: StickerGridParams = (
            values.get("category_override_params") or StickerGridParams()
        )
        stickers_override_params: dict[str, StickerGridParams] = (
            values.get("stickers_override_params") or {}
        )

        with wrap_validation_error(
            "category_select_override_params validation failed",
        ):
            values["resolved_category_params"] = type_validate_python(
                StickerGridParams,
                deep_merge(
                    type_dump_python(default_params, exclude_unset=True),
                    type_dump_python(
                        category_override_params,
                        exclude_unset=True,
                    ),
                ),
            )

        resolved_stickers_params: dict[str, StickerGridParams] = {}
        for category, params in stickers_override_params.items():
            with wrap_validation_error(
                f"category {category} overridden StickerGridSetting validation failed",
            ):
                resolved_stickers_params[category] = type_validate_python(
                    StickerGridParams,
                    deep_merge(
                        type_dump_python(default_params, exclude_unset=True),
                        type_dump_python(params, exclude_unset=True),
                    ),
                )
        values["resolved_stickers_params"] = resolved_stickers_params

        return values


def merge_ensure_sticker_params(*params: StickerParamsOptional) -> StickerParams:
    kw: dict[str, Any] = {}
    for param in params:
        kw.update(type_dump_python(param, exclude_defaults=True))
    return StickerParams(**kw)


def find_sticker_by_name(
    stickers: list[StickerInfo],
    name: str,
) -> Optional[StickerInfo]:
    return next((x for x in stickers if x.name == name), None)


def find_sticker(
    stickers: list[StickerInfo],
    query: Union[str, int],
) -> Optional[StickerInfo]:
    if isinstance(query, str) and (not query.isdigit()):
        return find_sticker_by_name(stickers, query)
    with suppress(IndexError):
        return stickers[int(query)]
    return None


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

    resolved_stickers: list[StickerInfo] = []
    resolved_sample_sticker_placeholder: Optional[StickerParams] = None

    @property
    def resolved_sample_sticker(self) -> StickerParams:
        if self.resolved_sample_sticker_placeholder is None:
            raise InvalidStateError
        return self.resolved_sample_sticker_placeholder

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
        return find_sticker_by_name(self.resolved_stickers, name)

    def find_sticker(self, query: Union[str, int]) -> Optional[StickerInfo]:
        return find_sticker(self.resolved_stickers, query)

    @field_validator("name")
    def _validate_not_falsy(cls, v: str) -> str:  # noqa: N805
        return validate_not_falsy(v)

    @model_validator(mode="after")
    def _validate_resolve_stickers(cls, values: dict[str, Any]) -> dict[str, Any]:  # noqa: N805
        stickers: Optional[list[StickerInfoOptionalParams]] = values.get("stickers")
        if not stickers:
            raise ValueError("Stickers cannot be empty")

        default_sticker_params: StickerParamsOptional = (
            values.get("default_sticker_params") or StickerParamsOptional()
        )

        def validate_info(sticker: StickerInfoOptionalParams) -> StickerInfo:
            return type_validate_python(
                StickerInfo,
                {
                    **type_dump_python(sticker, exclude={"params"}),
                    "params": merge_ensure_sticker_params(
                        default_sticker_params,
                        sticker.params,
                    ),
                },
            )

        resolved_stickers: list[StickerInfo] = []
        for idx, x in enumerate(stickers):
            with wrap_validation_error(f"Sticker {idx} validation failed"):
                resolved_stickers.append(validate_info(x))
        values["resolved_stickers"] = resolved_stickers

        sample_sticker: Union[StickerInfoOptionalParams, str, int, None] = values.get(
            "sample_sticker",
        )
        if not sample_sticker:
            resolved_sample_sticker = resolved_stickers[0].params
        elif isinstance(sample_sticker, StickerInfoOptionalParams):
            with wrap_validation_error("Sample sticker validation failed"):
                resolved_sample_sticker = merge_ensure_sticker_params(
                    default_sticker_params,
                    sample_sticker.params,
                )
        else:
            it = find_sticker(resolved_stickers, sample_sticker)
            if it is None:
                raise ValueError(f"Sample sticker `{sample_sticker}` not found")
            resolved_sample_sticker = it.params
        values["resolved_sample_sticker_placeholder"] = resolved_sample_sticker

        return values


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
