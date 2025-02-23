import math
from pathlib import Path
from typing import Callable, Optional, Union

import skia

from ..consts import SkiaEncodedImageFormatType, SkiaFontStyleType, SkiaTextAlignType

font_mgr = skia.FontMgr()
font_collection = skia.textlayout.FontCollection()
font_collection.setDefaultFontManager(font_mgr)

SYSTEM_MONOSPACE_FONTS = [
    "JetBrains Mono",
    "Fira Code",
    "Cascadia Code",
    "Consolas",
    "Lucida Console",
    "Menlo",
    "Monaco",
    "Source Code Pro",
    "Ubuntu Mono",
]
FALLBACK_SYSTEM_FONTS = [
    "Arial",
    "Tahoma",
    "Helvetica Neue",
    "Segoe UI",
    "PingFang SC",
    "Hiragino Sans GB",
    "Microsoft YaHei",
    "Source Han Sans SC",
    "Noto Sans SC",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "Apple Color Emoji",
    "Noto Color Emoji",
    "Segoe UI Emoji",
    "Segoe UI Symbol",
]

DEFAULT_BACKGROUND_COLOR = 0xFF282C34
DEFAULT_TEXT_COLOR = 0xFFD7DAE0

TEXT_ALIGN_MAP: dict[SkiaTextAlignType, skia.textlayout_TextAlign] = {
    "center": skia.textlayout_TextAlign.kCenter,
    "end": skia.textlayout_TextAlign.kEnd,
    "justify": skia.textlayout_TextAlign.kJustify,
    "left": skia.textlayout_TextAlign.kLeft,
    "right": skia.textlayout_TextAlign.kRight,
    "start": skia.textlayout_TextAlign.kStart,
}
FONT_STYLE_FUNC_MAP: dict[SkiaFontStyleType, Callable[[], skia.FontStyle]] = {
    "bold": skia.FontStyle.Bold,
    "bold_italic": skia.FontStyle.BoldItalic,
    "italic": skia.FontStyle.Italic,
    "normal": skia.FontStyle.Normal,
}
IMAGE_FORMAT_MAP: dict[SkiaEncodedImageFormatType, skia.EncodedImageFormat] = {
    "jpeg": skia.EncodedImageFormat.kJPEG,
    "png": skia.EncodedImageFormat.kPNG,
    "webp": skia.EncodedImageFormat.kWEBP,
}


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
    layout: bool = True,
):
    builder = make_paragraph_builder(paragraph_style)
    builder.pushStyle(text_style)
    builder.addText(text)
    p = builder.Build()
    p.layout(math.inf)
    if layout:
        p.layout(math.ceil(p.LongestLine))
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


def get_resize_contain_ratio_size_offset(
    original_w: float,
    original_h: float,
    target_w: float,
    target_h: float,
) -> tuple[float, float, float, float, float]:
    """Returns: (ratio, resized_w, resized_h, offset_x, offset_y)"""

    ratio = min(target_w / original_w, target_h / original_h)
    resized_w = original_w * ratio
    resized_h = original_h * ratio
    offset_x = (target_w - resized_w) / 2
    offset_y = (target_h - resized_h) / 2
    return ratio, resized_w, resized_h, offset_x, offset_y


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


def make_fill_paint(color: int) -> skia.Paint:
    paint = skia.Paint()
    paint.setAntiAlias(True)
    paint.setStyle(skia.Paint.kFill_Style)
    paint.setColor(color)
    return paint


def make_stroke_paint(color: int, width: float) -> skia.Paint:
    paint = skia.Paint()
    paint.setAntiAlias(True)
    paint.setStyle(skia.Paint.kStroke_Style)
    paint.setStrokeWidth(width)
    paint.setColor(color)
    return paint


def read_file_to_skia_image(path: Union[Path, str]) -> skia.Image:
    if isinstance(path, Path):
        path = str(path)
    return skia.Image.MakeFromEncoded(skia.Data.MakeFromFileName(path))


def make_surface_for_picture(
    picture: skia.Picture,
    background: Optional[int] = None,
) -> skia.Surface:
    bounds = picture.cullRect()
    s = skia.Surface(math.floor(bounds.width()), math.floor(bounds.height()))
    with s as canvas:
        if background is not None:
            canvas.drawColor(background)
        canvas.drawPicture(picture)
    return s


def get_black_n_white_filter_paint() -> skia.Paint:
    color_filter = skia.ColorFilters.Matrix([
        0.2126, 0.7152, 0.0722, 0, 0,
        0.2126, 0.7152, 0.0722, 0, 0,
        0.2126, 0.7152, 0.0722, 0, 0,
        0,      0,      0,      1, 0,
    ])  # fmt: skip
    paint = skia.Paint()
    paint.setColorFilter(color_filter)
    return paint


def save_image(
    surface: skia.Surface,
    image_type: Union[skia.EncodedImageFormat, SkiaEncodedImageFormatType],
    quality: int = 95,
    background: Optional[int] = None,
):
    image_type = (
        IMAGE_FORMAT_MAP[image_type] if isinstance(image_type, str) else image_type
    )

    if image_type == skia.kJPEG:
        new_surface = skia.Surface(surface.width(), surface.height())
        with new_surface as canvas:
            if background is not None:
                canvas.drawColor(background)
            canvas.drawImage(surface.makeImageSnapshot(), 0, 0)
        surface = new_surface

    return surface.makeImageSnapshot().encodeToData(image_type, quality).bytes()


def text_to_picture(
    text: str,
    padding: int = 32,
    font_size: int = 32,
    font_families: Optional[list[str]] = None,
    font_style: Optional[skia.FontStyle] = None,
    text_align: skia.textlayout_TextAlign = skia.textlayout_TextAlign.kLeft,
    background: int = DEFAULT_BACKGROUND_COLOR,
    foreground: int = DEFAULT_TEXT_COLOR,
) -> skia.Picture:
    para_style = skia.textlayout.ParagraphStyle()
    para_style.setTextAlign(text_align)
    text_style = make_text_style(
        foreground,
        font_size,
        font_families or SYSTEM_MONOSPACE_FONTS,
        font_style or skia.FontStyle.Normal(),
    )
    para = make_simple_paragraph(para_style, text_style, text, layout=True)

    width = math.ceil(para.LongestLine) + padding * 2
    height = math.ceil(para.Height) + padding * 2

    recorder = skia.PictureRecorder()
    canvas = recorder.beginRecording(width, height)

    canvas.clear(background)
    canvas.translate(padding, padding)
    para.paint(canvas, 0, 0)

    return recorder.finishRecordingAsPicture()
