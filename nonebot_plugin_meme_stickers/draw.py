# ruff: noqa: INP001

import math
from pathlib import Path

import skia

from .models import SkiaFontStyleType, SkiaTextAlignType, StickerParams

font_mgr = skia.FontMgr()
font_collection = skia.textlayout.FontCollection()
font_collection.setDefaultFontManager(font_mgr)


def make_paragraph_builder(style: skia.textlayout_ParagraphStyle):
    return skia.textlayout.ParagraphBuilder.make(
        style,
        font_collection,
        skia.Unicodes.ICU.Make(),
    )


def make_simple_paragraph(
    paragraph_style: skia.textlayout_ParagraphStyle,
    text_style: skia.textlayout_TextStyle,
    text: str,
):
    builder = make_paragraph_builder(paragraph_style)
    builder.pushStyle(text_style)
    builder.addText(text)
    p = builder.Build()
    p.layout(math.inf)
    return p


def make_text_style(
    color: int,
    font_size: float,
    font_families: list[str],
    font_style: skia.FontStyle,
    stroke_width_factor: float = 0,
) -> skia.textlayout_TextStyle:
    paint = skia.Paint()
    paint.setColor(color)
    paint.setAntiAlias(True)

    if stroke_width_factor > 0:
        paint.setStyle(skia.Paint.kStroke_Style)
        paint.setStrokeJoin(skia.Paint.kRound_Join)
        paint.setStrokeWidth(font_size * stroke_width_factor)

    style = skia.textlayout.TextStyle()
    style.setFontSize(font_size)
    style.setForegroundPaint(paint)
    style.setFontFamilies(font_families)
    style.setFontStyle(font_style)
    style.setLocale("en")

    return style


def rotate_point(
    x: float,
    y: float,
    cx: float,
    cy: float,
    degrees: float,
) -> tuple[float, float]:
    angle_rad = math.radians(degrees)
    rx = (x - cx) * math.cos(angle_rad) - (y - cy) * math.sin(angle_rad) + cx
    ry = (x - cx) * math.sin(angle_rad) + (y - cy) * math.cos(angle_rad) + cy
    return rx, ry


def calc_rotated_bounding_box_xywh(
    text_xywh: tuple[float, float, float, float],
    rotate_center: tuple[float, float],
    rotate_degrees: float,
) -> tuple[float, float, float, float]:
    x, y, w, h = text_xywh

    # 计算原始矩形的四个顶点
    points = [
        (x, y),  # 左上角
        (x + w, y),  # 右上角
        (x + w, y + h),  # 右下角
        (x, y + h),  # 左下角
    ]

    # 旋转顶点
    cx, cy = rotate_center
    rotated_points = [rotate_point(*p, cx, cy, rotate_degrees) for p in points]

    # 计算旋转后边界框的边界
    x_values = [rx for rx, ry in rotated_points]
    y_values = [ry for rx, ry in rotated_points]

    min_x = min(x_values)
    max_x = max(x_values)
    min_y = min(y_values)
    max_y = max(y_values)

    # 计算旋转后边界框的 (x, y, w, h)
    rotated_x = min_x
    rotated_y = min_y
    rotated_w = max_x - min_x
    rotated_h = max_y - min_y

    return rotated_x, rotated_y, rotated_w, rotated_h


def draw_sticker(
    surface: skia.Surface,
    x: float,
    y: float,
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
    debug_bounding_box: bool = False,
) -> skia.Surface:
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

    with surface as canvas:
        ratio = min(width / base_image.width(), height / base_image.height())
        resized_width = base_image.width() * ratio
        resized_height = base_image.height() * ratio
        top_left_offset_x = (width - resized_width) / 2
        top_left_offset_y = (height - resized_height) / 2

        img = base_image.resize(
            round(resized_width),
            round(resized_height),
            skia.SamplingOptions(skia.FilterMode.kLinear),
        )
        with skia.AutoCanvasRestore(canvas):
            canvas.drawImage(img, x + top_left_offset_x, y + top_left_offset_y)

        if debug_bounding_box:
            box_paint = skia.Paint()
            box_paint.setAntiAlias(True)
            box_paint.setStyle(skia.Paint.kStroke_Style)
            box_paint.setStrokeWidth(2)

            # image box (blue)
            with skia.AutoCanvasRestore(canvas):
                rect = skia.Rect.MakeXYWH(x, y, width, height)
                paint = skia.Paint(box_paint)
                paint.setColor(0xFF0000FF)
                canvas.drawRect(rect, paint)

            # bounding box (red)
            with skia.AutoCanvasRestore(canvas):
                bx, by, bw, bh = calc_text_rotated_xywh()
                rect = skia.Rect.MakeXYWH(bx + x, by + y, bw, bh)
                paint = skia.Paint(box_paint)
                paint.setColor(0xFFFF0000)
                canvas.drawRect(rect, paint)

            # text box (green)
            with skia.AutoCanvasRestore(canvas):
                canvas.translate(x + text_x, y + text_y)
                canvas.rotate(text_rotate_degrees)

                _, _, w, h = get_text_original_xywh()
                offset_x, offset_y = get_text_draw_offset()
                stroke_w = font_size * stroke_width_factor
                rect = skia.Rect.MakeXYWH(
                    -offset_x - stroke_w,
                    -offset_y - stroke_w,
                    w,
                    h,
                )
                paint = skia.Paint(box_paint)
                paint.setColor(0xFF00FF00)
                canvas.drawRect(rect, paint)

        with skia.AutoCanvasRestore(canvas):
            canvas.translate(x + text_x, y + text_y)
            canvas.rotate(text_rotate_degrees)

            offset_x, offset_y = get_text_draw_offset()
            canvas.translate(-offset_x, -offset_y)
            if stroke_paragraph:
                stroke_paragraph.paint(canvas, 0, 0)
            fg_paragraph.paint(canvas, 0, 0)

    return surface


def transform_text_align(text_align: SkiaTextAlignType) -> skia.textlayout_TextAlign:
    return {
        "center": skia.textlayout_TextAlign.kCenter,
        "end": skia.textlayout_TextAlign.kEnd,
        "justify": skia.textlayout_TextAlign.kJustify,
        "left": skia.textlayout_TextAlign.kLeft,
        "right": skia.textlayout_TextAlign.kRight,
        "start": skia.textlayout_TextAlign.kStart,
    }[text_align]


def transform_font_style(font_style: SkiaFontStyleType) -> skia.FontStyle:
    return {
        "bold": skia.FontStyle.Bold,
        "bold_italic": skia.FontStyle.BoldItalic,
        "italic": skia.FontStyle.Italic,
        "normal": skia.FontStyle.Normal,
    }[font_style]()


def draw_sticker_from_params(
    surface: skia.Surface,
    x: float,
    y: float,
    base_path: Path,
    params: StickerParams,
    auto_resize: bool = False,
    debug_bounding_box: bool = False,
) -> skia.Surface:
    return draw_sticker(
        surface,
        x,
        y,
        params.width,
        params.height,
        skia.Image.MakeFromEncoded(
            skia.Data.MakeFromFileName(str(base_path / params.base_image)),
        ),
        params.text,
        params.text_x,
        params.text_y,
        transform_text_align(params.text_align),
        params.text_rotate_degrees,
        skia.Color(*params.text_color),
        skia.Color(*params.stroke_color),
        params.stroke_width_factor,
        params.font_size,
        transform_font_style(params.font_style),
        params.font_families,
        auto_resize=auto_resize,
        debug_bounding_box=debug_bounding_box,
    )
