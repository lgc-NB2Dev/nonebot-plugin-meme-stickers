import math
from pathlib import Path
from typing import Optional
from typing_extensions import NotRequired, TypedDict, Unpack

import skia
from cookit import chunks
from cookit.pyd import model_copy

from ..sticker_pack.models import StickerParams, zoom_sticker
from .sticker import make_sticker_picture_from_params
from .tools import (
    DEFAULT_BACKGROUND_COLOR,
    DEFAULT_TEXT_COLOR,
    FALLBACK_SYSTEM_FONTS,
    get_black_n_white_filter_paint,
    get_resize_contain_ratio_size_offset,
    make_fill_paint,
    make_paragraph_builder,
    make_stroke_paint,
    make_text_style,
)

DEFAULT_CARD_BACKGROUND_COLOR = 0xFF404754
DEFAULT_CARD_BORDER_COLOR = 0xFF3E4452
DEFAULT_CARD_TEXT_COLOR = DEFAULT_TEXT_COLOR
DEFAULT_CARD_SUB_TEXT_COLOR = 0xFFABB2BF

DEFAULT_CARD_DISABLED_BACKGROUND_COLOR = 0xFF30333D
DEFAULT_CARD_DISABLED_BORDER_COLOR = 0xFF23252C
DEFAULT_CARD_DISABLED_TEXT_COLOR = 0xFFABB2BF
DEFAULT_CARD_DISABLED_SUB_TEXT_COLOR = 0xFF495162

DEFAULT_CARD_FONT_SIZE = 32
DEFAULT_CARD_SUB_FONT_SIZE = 28
DEFAULT_CARD_SAMPLE_PIC_SIZE = 128

DEFAULT_CARD_PADDING = 16
DEFAULT_CARD_GAP = 16
DEFAULT_CARD_BORDER_WIDTH = 1
DEFAULT_CARD_BORDER_RADIUS = 8

DEFAULT_CARD_GRID_PADDING = 16
DEFAULT_CARD_GRID_GAP = 16
DEFAULT_CARD_GRID_COLS = 2


class StickerPackCardParams(TypedDict):
    base_path: Path
    sample_sticker_params: StickerParams
    name: str
    slug: str
    description: str
    index: NotRequired[Optional[str]]
    unavailable: NotRequired[bool]
    unavailable_reason: NotRequired[Optional[str]]


def make_sticker_pack_card_picture(
    **kwargs: Unpack[StickerPackCardParams],
) -> skia.Picture:
    base_path = kwargs["base_path"]
    sample_sticker_params = kwargs["sample_sticker_params"]
    name = kwargs["name"]
    slug = kwargs["slug"]
    description = kwargs["description"]
    index = kwargs.get("index")
    unavailable = kwargs.get("unavailable", False)
    unavailable_reason = kwargs.get("unavailable_reason")

    para_style = skia.textlayout.ParagraphStyle()
    para_style.setTextAlign(skia.kLeft)

    builder = make_paragraph_builder(para_style)

    title_style = make_text_style(
        (DEFAULT_CARD_DISABLED_TEXT_COLOR if unavailable else DEFAULT_CARD_TEXT_COLOR),
        DEFAULT_CARD_FONT_SIZE,
        FALLBACK_SYSTEM_FONTS,
        skia.FontStyle.Normal(),
    )
    builder.pushStyle(title_style)
    title_parts = [name, "\n"]
    if unavailable_reason:
        title_parts.insert(0, f"[{unavailable_reason}] ")
    if index:
        title_parts.insert(0, f"{index}. ")
    builder.addText("".join(title_parts))

    desc_style = make_text_style(
        (
            DEFAULT_CARD_DISABLED_SUB_TEXT_COLOR
            if unavailable
            else DEFAULT_CARD_SUB_TEXT_COLOR
        ),
        DEFAULT_CARD_SUB_FONT_SIZE,
        FALLBACK_SYSTEM_FONTS,
        skia.FontStyle.Normal(),
    )
    builder.pushStyle(desc_style)
    desc_parts = [f"[{slug}] ", description]
    builder.addText("".join(desc_parts))

    para = builder.Build()
    para.layout(math.inf)
    para.layout(math.ceil(para.LongestLine))

    pic_w = (
        DEFAULT_CARD_PADDING * 2
        + DEFAULT_CARD_SAMPLE_PIC_SIZE
        + DEFAULT_CARD_GAP
        + round(para.LongestLine)
    )
    pic_h = DEFAULT_CARD_PADDING * 2 + max(
        DEFAULT_CARD_SAMPLE_PIC_SIZE,
        round(para.Height),
    )

    recorder = skia.PictureRecorder()
    canvas = recorder.beginRecording(pic_w, pic_h)

    sticker_ratio, _, _, sticker_x_offset, sticker_y_offset = (
        get_resize_contain_ratio_size_offset(
            sample_sticker_params.width,
            sample_sticker_params.height,
            DEFAULT_CARD_SAMPLE_PIC_SIZE,
            DEFAULT_CARD_SAMPLE_PIC_SIZE,
        )
    )
    sticker_pic = make_sticker_picture_from_params(
        base_path,
        zoom_sticker(model_copy(sample_sticker_params), sticker_ratio),
        auto_resize=True,
    )
    with skia.AutoCanvasRestore(canvas):
        canvas.translate(
            DEFAULT_CARD_PADDING + sticker_x_offset,
            sticker_y_offset + DEFAULT_CARD_PADDING,
        )
        canvas.drawPicture(
            sticker_pic,
            paint=get_black_n_white_filter_paint() if unavailable else None,
        )

    text_x_offset = (
        DEFAULT_CARD_PADDING + DEFAULT_CARD_SAMPLE_PIC_SIZE + DEFAULT_CARD_GAP
    )
    text_y_offset = (pic_h - para.Height) / 2
    with skia.AutoCanvasRestore(canvas):
        canvas.translate(text_x_offset, text_y_offset)
        para.paint(canvas, 0, 0)

    return recorder.finishRecordingAsPicture()


def draw_sticker_pack_grid(params: list[StickerPackCardParams]):
    cards = [make_sticker_pack_card_picture(**p) for p in params]
    rectangles = [x.cullRect() for x in cards]
    splitted_cards = list(
        chunks(tuple(zip(cards, rectangles, params)), DEFAULT_CARD_GRID_COLS),
    )

    card_w = max(x.width() for x in rectangles)
    card_lines_h = [max(x[1].height() for x in row) for row in splitted_cards]

    first_line_len = len(splitted_cards[0])
    surface_w = round(
        DEFAULT_CARD_GRID_PADDING * 2
        + DEFAULT_CARD_GRID_GAP * (first_line_len - 1)
        + card_w * first_line_len,
    )
    surface_h = round(
        DEFAULT_CARD_GRID_PADDING * 2
        + DEFAULT_CARD_GRID_GAP * (len(splitted_cards) - 1)
        + sum(card_lines_h),
    )
    surface = skia.Surface(surface_w, surface_h)

    reset_x_translate = (card_w + DEFAULT_CARD_GRID_GAP) * -DEFAULT_CARD_GRID_COLS
    with surface as canvas:
        canvas.drawColor(DEFAULT_BACKGROUND_COLOR)
        canvas.translate(DEFAULT_CARD_GRID_PADDING, DEFAULT_CARD_GRID_PADDING)

        for row, row_h in zip(splitted_cards, card_lines_h):
            for pic, rect, param in row:
                unavailable = param.get("unavailable", False)
                rect = skia.Rect.MakeWH(card_w, row_h)
                canvas.drawRoundRect(
                    rect,
                    DEFAULT_CARD_BORDER_RADIUS,
                    DEFAULT_CARD_BORDER_RADIUS,
                    make_fill_paint(
                        DEFAULT_CARD_DISABLED_BACKGROUND_COLOR
                        if unavailable
                        else DEFAULT_CARD_BACKGROUND_COLOR,
                    ),
                )
                canvas.drawRoundRect(
                    rect,
                    DEFAULT_CARD_BORDER_RADIUS,
                    DEFAULT_CARD_BORDER_RADIUS,
                    make_stroke_paint(
                        (
                            DEFAULT_CARD_DISABLED_BORDER_COLOR
                            if unavailable
                            else DEFAULT_CARD_BORDER_COLOR
                        ),
                        DEFAULT_CARD_BORDER_WIDTH,
                    ),
                )
                with skia.AutoCanvasRestore(canvas):
                    canvas.translate(0, (row_h - rect.height()) / 2)
                    canvas.drawPicture(pic)
                canvas.translate(card_w + DEFAULT_CARD_GRID_GAP, 0)
            canvas.translate(
                reset_x_translate,
                row_h + DEFAULT_CARD_GRID_GAP,
            )

    return surface
