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
from .sticker_pack import StickerPack

font_mgr = skia.FontMgr()
font_collection = skia.textlayout.FontCollection()
font_collection.setDefaultFontManager(font_mgr)

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

DEFAULT_CARD_BACKGROUND_COLOR = 0xFF404754
DEFAULT_CARD_BORDER_COLOR = 0xFF3E4452
DEFAULT_CARD_TEXT_COLOR = 0xFFD7DAE0
DEFAULT_CARD_SUB_TEXT_COLOR = 0xFFABB2BF
DEFAULT_CARD_FONT_SIZE = 32
DEFAULT_CARD_SUB_FONT_SIZE = 28
DEFAULT_CARD_PADDING = 16
DEFAULT_CARD_GAP = 16
DEFAULT_CARD_SAMPLE_PIC_SIZE = 128
DEFAULT_CARD_BORDER_RADIUS = 8

DEFAULT_CARD_GRID_PADDING = 16
DEFAULT_CARD_GRID_GAP = 16
DEFAULT_CARD_GRID_COLS = 2


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
            canvas.drawRect(
                image_rect,
                make_stroke_paint(0xFF0000FF, 2),
            )
        canvas.drawImageRect(
            base_image,
            image_rect,
            skia.SamplingOptions(skia.FilterMode.kLinear),
        )

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
        "jpeg": skia.EncodedImageFormat.kJPEG,
        "png": skia.EncodedImageFormat.kPNG,
        "webp": skia.EncodedImageFormat.kWEBP,
    }[image_type]


def read_file_to_skia_image(path: Union[Path, str]) -> skia.Image:
    if isinstance(path, Path):
        path = str(path)
    return skia.Image.MakeFromEncoded(skia.Data.MakeFromFileName(path))


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
        text_align=transform_text_align(params.text_align),
        text_rotate_degrees=params.text_rotate_degrees,
        text_color=skia.Color(*params.text_color),
        stroke_color=skia.Color(*params.stroke_color),
        stroke_width_factor=params.stroke_width_factor,
        font_size=params.font_size,
        font_style=transform_font_style(params.font_style),
        font_families=params.font_families,
        auto_resize=auto_resize,
        debug=debug,
    )


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


def draw_sticker_grid(
    base_path: Path,
    stickers: list[StickerParams],
    padding: TRBLPaddingTuple = (16, 16, 16, 16),
    gap: XYGapTuple = (16, 16),
    rows: Optional[int] = None,
    cols: Optional[int] = 5,
    background: Union[skia.Image, int] = DEFAULT_BACKGROUND_COLOR,
    sticker_size_fixed: Optional[tuple[int, int]] = None,
    debug: bool = False,
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

        def draw_one(p: StickerParams):
            if debug:
                # sticker taken space (magenta)
                canvas.drawRect(
                    skia.Rect.MakeWH(max_w, max_h),
                    make_stroke_paint(0xFFFF00FF, 2),
                )

            ratio, rw, rh, x_offset, y_offset = get_resize_contain_ratio_size_offset(
                p.width,
                p.height,
                max_w,
                max_h,
            )

            p = zoom_sticker(model_copy(p), ratio)
            picture = make_sticker_picture_from_params(
                base_path,
                p,
                auto_resize=True,
                debug=debug,
            )

            with skia.AutoCanvasRestore(canvas):
                canvas.translate(x_offset, y_offset)
                if debug:
                    # sticker actual space (yellow)
                    canvas.drawRect(
                        skia.Rect.MakeWH(rw, rh),
                        make_stroke_paint(0xFFFFFF00, 2),
                    )
                canvas.drawPicture(picture)

        reset_x_translate = (max_w + gap_x) * -cols
        canvas.translate(pad_l, pad_t)
        for row in splitted_stickers:
            for param in row:
                draw_one(param)
                canvas.translate(max_w + gap_x, 0)
            canvas.translate(reset_x_translate, max_h + gap_y)

    return surface


def draw_sticker_grid_from_params(
    params: StickerGridParams,
    stickers: list[StickerParams],
    base_path: Path,
    debug: bool = False,
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
        debug=debug,
    )


def make_sticker_pack_card_picture(
    base_path: Path,
    sample_sticker_params: StickerParams,
    slug: str,
    name: str,
    description: str,
) -> tuple[skia.Picture, int, int]:
    """Returns: (picture, width, height)"""

    para_style = skia.textlayout.ParagraphStyle()
    para_style.setTextAlign(skia.kLeft)

    builder = make_paragraph_builder(para_style)

    title_style = make_text_style(
        DEFAULT_CARD_TEXT_COLOR,
        DEFAULT_CARD_FONT_SIZE,
        FALLBACK_SYSTEM_FONTS,
        skia.FontStyle.Normal(),
    )
    builder.pushStyle(title_style)
    builder.addText(f"[{slug}] {name}\n")

    desc_style = make_text_style(
        DEFAULT_CARD_SUB_TEXT_COLOR,
        DEFAULT_CARD_SUB_FONT_SIZE,
        FALLBACK_SYSTEM_FONTS,
        skia.FontStyle.Normal(),
    )
    builder.pushStyle(desc_style)
    builder.addText(description)

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
        zoom_sticker(sample_sticker_params, sticker_ratio),
        auto_resize=True,
    )
    with skia.AutoCanvasRestore(canvas):
        canvas.translate(
            DEFAULT_CARD_PADDING + sticker_x_offset,
            sticker_y_offset + DEFAULT_CARD_PADDING,
        )
        canvas.drawPicture(sticker_pic)

    text_x_offset = (
        DEFAULT_CARD_PADDING + DEFAULT_CARD_SAMPLE_PIC_SIZE + DEFAULT_CARD_GAP
    )
    text_y_offset = (pic_h - para.Height) / 2
    with skia.AutoCanvasRestore(canvas):
        canvas.translate(text_x_offset, text_y_offset)
        para.paint(canvas, 0, 0)

    pic = recorder.finishRecordingAsPicture()
    return pic, pic_w, pic_h


def draw_sticker_pack_list(packs: dict[str, StickerPack]):
    cards = [
        make_sticker_pack_card_picture(
            p.base_path,
            p.manifest.resolved_sample_sticker,
            slug,
            p.manifest.name,
            p.manifest.description,
        )
        for slug, p in packs.items()
    ]
    splitted_cards = list(chunks(cards, DEFAULT_CARD_GRID_COLS))

    card_w = max(x[1] for x in cards)
    card_lines_h = [max(x[2] for x in row) for row in splitted_cards]

    surface_w = (
        DEFAULT_CARD_GRID_PADDING * 2
        + DEFAULT_CARD_GRID_GAP * (DEFAULT_CARD_GRID_COLS - 1)
        + card_w * DEFAULT_CARD_GRID_COLS
    )
    surface_h = (
        DEFAULT_CARD_GRID_PADDING * 2
        + DEFAULT_CARD_GRID_GAP * (len(splitted_cards) - 1)
        + sum(card_lines_h)
    )
    surface = skia.Surface(surface_w, surface_h)

    reset_x_translate = (card_w + DEFAULT_CARD_GRID_GAP) * -DEFAULT_CARD_GRID_COLS
    with surface as canvas:
        canvas.drawColor(DEFAULT_BACKGROUND_COLOR)
        canvas.translate(DEFAULT_CARD_GRID_PADDING, DEFAULT_CARD_GRID_PADDING)

        for row, row_h in zip(splitted_cards, card_lines_h):
            for pic, _, content_h in row:
                rect = skia.Rect.MakeWH(card_w, row_h)
                canvas.drawRoundRect(
                    rect,
                    DEFAULT_CARD_BORDER_RADIUS,
                    DEFAULT_CARD_BORDER_RADIUS,
                    make_fill_paint(DEFAULT_CARD_BACKGROUND_COLOR),
                )
                canvas.drawRoundRect(
                    rect,
                    DEFAULT_CARD_BORDER_RADIUS,
                    DEFAULT_CARD_BORDER_RADIUS,
                    make_stroke_paint(DEFAULT_CARD_BORDER_COLOR, 1),
                )
                with skia.AutoCanvasRestore(canvas):
                    canvas.translate(0, (row_h - content_h) / 2)
                    canvas.drawPicture(pic)
                canvas.translate(card_w + DEFAULT_CARD_GRID_GAP, 0)
            canvas.translate(
                reset_x_translate,
                row_h + DEFAULT_CARD_GRID_GAP,
            )

    return surface


def save_image(
    surface: skia.Surface,
    image_type: SkiaEncodedImageFormatType,
    quality: int = 95,
):
    return (
        surface.makeImageSnapshot()
        .encodeToData(transform_image_type(image_type), quality)
        .bytes()
    )
