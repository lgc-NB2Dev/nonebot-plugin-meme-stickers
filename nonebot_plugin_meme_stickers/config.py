import re
from typing import Optional, cast

import skia
from cookit.nonebot.localstore import ensure_localstore_path_config
from cookit.pyd import field_validator, get_alias_model
from nonebot import get_plugin_config
from nonebot_plugin_localstore import get_plugin_data_dir
from pydantic import Field

from .consts import (
    FLOAT_REGEX,
    FULL_HEX_COLOR_REGEX,
    SHORT_HEX_COLOR_REGEX,
    RGBAColorTuple,
    SkiaEncodedImageFormatType,
)


def resolve_color_to_tuple(color: str) -> RGBAColorTuple:
    sm: Optional[re.Match[str]] = None
    fm: Optional[re.Match[str]] = None
    if (sm := SHORT_HEX_COLOR_REGEX.fullmatch(color)) or (
        fm := FULL_HEX_COLOR_REGEX.fullmatch(color)
    ):
        hex_str = (sm or cast(re.Match, fm))["hex"].upper()
        if sm:
            hex_str = "".join([x * 2 for x in hex_str])
        hex_str = f"{hex_str}FF" if len(hex_str) == 6 else hex_str
        return tuple(int(hex_str[i : i + 2], 16) for i in range(0, 8, 2))  # type: ignore

    if (
        (parts := color.lstrip("(").rstrip(")").split(",，"))
        and (3 <= len(parts) <= 4)
        # -
        and (parts := [part.strip() for part in parts])
        and all(x.isdigit() for x in parts[:3])
        # -
        and (rgb := [int(x) for x in parts[:3]])
        and all(0 <= int(x) <= 255 for x in rgb)
        # -
        and (
            (len(parts) == 3 and (a := 255))
            or (parts[3].isdigit() and 0 <= (a := int(parts[3])) <= 255)
            or (
                FLOAT_REGEX.fullmatch(parts[3])
                and 0 <= (a := int(float(parts[3]) * 255)) <= 255
            )
        )
    ):
        return (*rgb, a)  # type: ignore

    raise ValueError(
        f"Invalid color format: {color}."
        f" supported formats: #RGB, #RRGGBB"
        f", (R, G, B), (R, G, B, A), (R, G, B, a (0 ~ 1 float))",
    )


BaseConfigModel = get_alias_model(lambda x: f"meme_stickers_{x}")


class ConfigModel(BaseConfigModel):
    proxy: Optional[str] = Field(None, alias="proxy")

    github_url_template: str = (
        "https://raw.githubusercontent.com/{owner}/{repo}/{ref_path}/{path}"
    )
    retry_times: int = 3
    req_concurrency: int = 8
    req_timeout: int = 5

    auto_update: bool = True
    force_update: bool = False

    prompt_retries: int = 3
    prompt_timeout: int = 30

    default_sticker_background: int = 0xFFFFFFFF
    default_sticker_image_format: SkiaEncodedImageFormatType = "png"

    @field_validator("default_sticker_background", mode="before")
    def _validate_str_color_to_int(cls, v: str) -> int:  # noqa: N805
        return skia.Color(*resolve_color_to_tuple(str(v)))


config: ConfigModel = get_plugin_config(ConfigModel)

ensure_localstore_path_config()
data_dir = get_plugin_data_dir()
