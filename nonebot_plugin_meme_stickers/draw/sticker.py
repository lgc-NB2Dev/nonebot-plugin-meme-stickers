import math
from pathlib import Path

import skia

from ..sticker_pack.models import StickerParams
from .tools import (
    FALLBACK_SYSTEM_FONTS,
    FONT_STYLE_FUNC_MAP,
    TEXT_ALIGN_MAP,
    calc_rotated_bounding_box_xywh,
    get_resize_contain_ratio_size_offset,
    make_simple_paragraph,
    make_stroke_paint,
    make_text_style,
    read_file_to_skia_image,
)


def make_sticker_picture(
    width: int,
    height: int,
    base_image: skia.Image,
    text: str,
    text_x: float,
    text_y: float,
    text_align: skia.textlayout_TextAlign,
    text_rotate_degrees: float,
    text_color: int,
    stroke_color: int,
    stroke_width_factor: float,
    font_size: float,
    font_style: skia.FontStyle,
    font_families: list[str],
    # line_height: float = 1,  # 有点麻烦，要手动分行处理，不想做了
    auto_resize: bool = False,
    debug: bool = False,
) -> skia.Picture:
    pic_recorder = skia.PictureRecorder()
    canvas = pic_recorder.beginRecording(width, height)

    image_w = base_image.width()
    image_h = base_image.height()
    ratio, resized_width, resized_height, top_left_offset_x, top_left_offset_y = (
        get_resize_contain_ratio_size_offset(
            image_w,
            image_h,
            width,
            height,
        )
    )

    with skia.AutoCanvasRestore(canvas):
        image_rect = skia.Rect.MakeXYWH(
            top_left_offset_x,
            top_left_offset_y,
            resized_width,
            resized_height,
        )
        if debug:
            # base image (blue)
            canvas.drawRect(image_rect, make_stroke_paint(0xFF0000FF, 2))
        canvas.drawImageRect(
            base_image,
            image_rect,
            skia.SamplingOptions(skia.FilterMode.kLinear),
        )

    if not text:
        return pic_recorder.finishRecordingAsPicture()

    font_families = [*font_families, *FALLBACK_SYSTEM_FONTS]

    para_style = skia.textlayout.ParagraphStyle()
    para_style.setTextAlign(text_align)

    def make_fg_paragraph():
        return make_simple_paragraph(
            para_style,
            make_text_style(text_color, font_size, font_families, font_style),
            text,
        )

    def make_stroke_paragraph():
        return make_simple_paragraph(
            para_style,
            make_text_style(
                stroke_color,
                font_size,
                font_families,
                font_style,
                stroke_width_factor,
            ),
            text,
            layout=False,
        )

    fg_paragraph = make_fg_paragraph()

    def get_text_draw_offset() -> tuple[float, float]:
        return fg_paragraph.LongestLine / 2, fg_paragraph.AlphabeticBaseline

    def get_text_original_xywh() -> tuple[float, float, float, float]:
        stroke_width = font_size * stroke_width_factor
        stroke_width_2_times = stroke_width * 2
        offset_x, offset_y = get_text_draw_offset()
        return (
            text_x - offset_x - stroke_width,
            text_y - offset_y - stroke_width,
            fg_paragraph.LongestLine + stroke_width_2_times,
            fg_paragraph.Height + stroke_width_2_times,
        )

    def calc_text_rotated_xywh():
        return calc_rotated_bounding_box_xywh(
            get_text_original_xywh(),
            (text_x, text_y),
            text_rotate_degrees,
        )

    if auto_resize:
        bx, by, bw, bh = calc_text_rotated_xywh()

        # resize
        if bw > width or bh > height:
            ratio = min(width / bw, height / bh)
            font_size = font_size * ratio
            fg_paragraph = make_fg_paragraph()
            bx, by, bw, bh = calc_text_rotated_xywh()

        # prevent overflow
        if bx < 0:
            text_x += -bx
        if by < 0:
            text_y += -by
        if bx + bw > width:
            text_x -= bx + bw - width
        if by + bh > height:
            text_y -= by + bh - height

    fg_paragraph.layout(math.ceil(fg_paragraph.LongestLine))
    if stroke_width_factor > 0:
        stroke_paragraph = make_stroke_paragraph()
        stroke_paragraph.layout(math.ceil(stroke_paragraph.LongestLine))
    else:
        stroke_paragraph = None

    if debug:
        # bounding box (red)
        with skia.AutoCanvasRestore(canvas):
            canvas.drawRect(
                skia.Rect.MakeXYWH(*calc_text_rotated_xywh()),
                make_stroke_paint(0xFFFF0000, 2),
            )

        # text box (green)
        with skia.AutoCanvasRestore(canvas):
            canvas.translate(text_x, text_y)
            canvas.rotate(text_rotate_degrees)

            _, _, w, h = get_text_original_xywh()
            offset_x, offset_y = get_text_draw_offset()
            stroke_w = font_size * stroke_width_factor
            canvas.drawRect(
                skia.Rect.MakeXYWH(-offset_x - stroke_w, -offset_y - stroke_w, w, h),
                make_stroke_paint(0xFF00FF00, 2),
            )

    with skia.AutoCanvasRestore(canvas):
        canvas.translate(text_x, text_y)
        canvas.rotate(text_rotate_degrees)

        offset_x, offset_y = get_text_draw_offset()
        canvas.translate(-offset_x, -offset_y)
        if stroke_paragraph:
            stroke_paragraph.paint(canvas, 0, 0)
        fg_paragraph.paint(canvas, 0, 0)

    return pic_recorder.finishRecordingAsPicture()


def make_sticker_picture_from_params(
    base_path: Path,
    params: StickerParams,
    auto_resize: bool = False,
    debug: bool = False,
) -> skia.Picture:
    return make_sticker_picture(
        width=params.width,
        height=params.height,
        base_image=read_file_to_skia_image(base_path / params.base_image),
        text=params.text,
        text_x=params.text_x,
        text_y=params.text_y,
        text_align=TEXT_ALIGN_MAP[params.text_align],
        text_rotate_degrees=params.text_rotate_degrees,
        text_color=skia.Color(*params.text_color),
        stroke_color=skia.Color(*params.stroke_color),
        stroke_width_factor=params.stroke_width_factor,
        font_size=params.font_size,
        font_style=FONT_STYLE_FUNC_MAP[params.font_style](),
        font_families=params.font_families,
        auto_resize=auto_resize,
        debug=debug,
    )
