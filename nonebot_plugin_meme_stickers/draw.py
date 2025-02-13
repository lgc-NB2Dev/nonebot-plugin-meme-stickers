# ruff: noqa: INP001

import math
from pathlib import Path
from typing import Optional, Union

import skia
from cookit import chunks
from cookit.pyd import model_copy

from .models import (
    SkiaEncodedImageFormatType,
    SkiaFontStyleType,
    SkiaTextAlignType,
    StickerGridParams,
    StickerParams,
    TRBLPaddingTuple,
    XYGapTuple,
)

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


def get_resize_contain_ratio_and_size(
    original_w: float,
    original_h: float,
    target_w: float,
    target_h: float,
) -> tuple[float, float, float]:
    """Returns: (ratio, resized_w, resized_h)"""

    ratio = min(target_w / original_w, target_h / original_h)
    resized_w = original_w * ratio
    resized_h = original_h * ratio
    return ratio, resized_w, resized_h


def get_resize_cover_ratio_and_offset(
    original_w: float,
    original_h: float,
    target_w: float,
    target_h: float,
) -> tuple[float, float, float]:
    """Returns: (ratio, offset_x, offset_y)"""

    ratio = max(target_w / original_w, target_h / original_h)
    resized_w = original_w * ratio
    resized_h = original_h * ratio
    offset_x = (target_w - resized_w) / 2
    offset_y = (target_h - resized_h) / 2
    return ratio, offset_x, offset_y


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
        (ratio, resized_width, resized_height) = get_resize_contain_ratio_and_size(
            base_image.width(),
            base_image.height(),
            width,
            height,
        )
        top_left_offset_x = (width - resized_width) / 2
        top_left_offset_y = (height - resized_height) / 2

        with skia.AutoCanvasRestore(canvas):
            canvas.drawImageRect(
                base_image,
                skia.Rect.MakeXYWH(
                    x + top_left_offset_x,
                    y + top_left_offset_y,
                    resized_width,
                    resized_height,
                ),
                skia.SamplingOptions(skia.FilterMode.kLinear),
            )

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


def transform_image_type(
    image_type: SkiaEncodedImageFormatType,
) -> skia.EncodedImageFormat:
    return {
        "astc": skia.EncodedImageFormat.kASTC,
        "bmp": skia.EncodedImageFormat.kBMP,
        "dng": skia.EncodedImageFormat.kDNG,
        "gif": skia.EncodedImageFormat.kGIF,
        "heif": skia.EncodedImageFormat.kHEIF,
        "ico": skia.EncodedImageFormat.kICO,
        "jpeg": skia.EncodedImageFormat.kJPEG,
        "ktx": skia.EncodedImageFormat.kKTX,
        "pkm": skia.EncodedImageFormat.kPKM,
        "png": skia.EncodedImageFormat.kPNG,
        "wbmp": skia.EncodedImageFormat.kWBMP,
        "webp": skia.EncodedImageFormat.kWEBP,
    }[image_type]


def read_file_to_skia_image(path: Union[Path, str]) -> skia.Image:
    if isinstance(path, Path):
        path = str(path)
    return skia.Image.MakeFromEncoded(skia.Data.MakeFromFileName(path))


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
        surface=surface,
        x=x,
        y=y,
        width=params.width,
        height=params.height,
        base_image=read_file_to_skia_image(base_path / params.base_image),
        text=params.text,
        text_x=params.text_x,
        text_y=params.text_y,
        text_align=transform_text_align(params.text_align),
        text_rotate_degrees=params.text_rotate_degrees,
        text_color=skia.Color(*params.text_color),
        stroke_color=skia.Color(*params.stroke_color),
        stroke_width_factor=params.stroke_width_factor,
        font_size=params.font_size,
        font_style=transform_font_style(params.font_style),
        font_families=params.font_families,
        auto_resize=auto_resize,
        debug_bounding_box=debug_bounding_box,
    )


def zoom_sticker(params: StickerParams, zoom: float) -> StickerParams:
    params.text_x *= zoom
    params.text_y *= zoom
    params.font_size *= zoom
    params.stroke_width_factor *= zoom
    return params


def draw_sticker_grid(
    base_path: Path,
    stickers: list[StickerParams],
    padding: TRBLPaddingTuple = (16, 16, 16, 16),
    gap: XYGapTuple = (16, 16),
    rows: Optional[int] = None,
    cols: Optional[int] = 5,
    background: Union[skia.Image, int] = 0xFF282C34,
    sticker_size_fixed: Optional[tuple[int, int]] = None,
) -> skia.Surface:
    if (rows and cols) or ((rows is None) and (cols is None)):
        raise ValueError("Either rows or cols must be None")

    pad_t, pad_r, pad_b, pad_l = padding
    gap_x, gap_y = gap

    if rows:
        cols = math.ceil(len(stickers) / rows)
        splitted_stickers = chunks(stickers, cols)
    else:
        assert cols
        splitted_stickers = chunks(stickers, cols)
        rows = math.ceil(len(stickers) / cols)

    if sticker_size_fixed:
        max_w, max_h = sticker_size_fixed
    else:
        max_w = max(p.width for p in stickers)
        max_h = max(p.height for p in stickers)

    surface_w = round(cols * max_w + (cols - 1) * gap_x + pad_l + pad_r)
    surface_h = round(rows * max_h + (rows - 1) * gap_y + pad_t + pad_b)

    surface = skia.Surface(surface_w, surface_h)

    with surface as canvas:
        if isinstance(background, skia.Image):
            bw = background.width()
            bh = background.height()
            ratio, ox, oy = get_resize_cover_ratio_and_offset(
                bw,
                bh,
                surface_w,
                surface_h,
            )
            canvas.drawImageRect(
                background,
                skia.Rect.MakeXYWH(ox, oy, bw * ratio, bh * ratio),
                skia.SamplingOptions(skia.FilterMode.kLinear),
            )
        else:
            canvas.drawColor(background)

    grid_y_offset = pad_t
    for row in splitted_stickers:
        grid_x_offset = pad_l
        for param in row:
            ratio, rw, rh = get_resize_contain_ratio_and_size(
                param.width,
                param.height,
                max_w,
                max_h,
            )
            param = zoom_sticker(model_copy(param), ratio)
            x_offset = (max_w - rw) / 2
            y_offset = (max_h - rh) / 2
            draw_sticker_from_params(
                surface,
                grid_x_offset + x_offset,
                grid_y_offset + y_offset,
                base_path,
                param,
            )
            grid_x_offset += max_w + gap_x
        grid_y_offset += max_h + gap_y

    return surface


def draw_sticker_grid_from_params(
    params: StickerGridParams,
    stickers: list[StickerParams],
    base_path: Path,
) -> skia.Surface:
    return draw_sticker_grid(
        base_path=base_path,
        stickers=stickers,
        padding=params.resolved_padding,
        gap=params.resolved_gap,
        rows=params.rows,
        cols=params.cols,
        background=(
            read_file_to_skia_image(base_path / params.background)
            if isinstance(params.background, str)
            else skia.Color(*params.background)
        ),
        sticker_size_fixed=params.sticker_size_fixed,
    )
