import math
from pathlib import Path
from typing import Optional, Union

import skia
from cookit import chunks
from cookit.pyd import model_copy

from ..consts import TRBLPaddingTuple, XYGapTuple
from ..sticker_pack.models import StickerGridParams, StickerParams, zoom_sticker
from ..sticker_pack.pack import StickerPack
from .pack_list import StickerPackCardParams, draw_sticker_pack_grid
from .sticker import make_sticker_picture_from_params
from .tools import (
    DEFAULT_BACKGROUND_COLOR,
    get_resize_contain_ratio_size_offset,
    get_resize_cover_ratio_and_offset,
    make_stroke_paint,
    read_file_to_skia_image,
)


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

    stickers_len = len(stickers)
    if rows:
        rows = min(rows, stickers_len)
        cols = math.ceil(stickers_len / rows)
    else:
        assert cols
        cols = min(cols, stickers_len)
        rows = math.ceil(stickers_len / cols)

    splitted_stickers = chunks(stickers, cols)

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


def draw_sticker_grid_from_packs(packs: list[StickerPack]):
    params = [
        StickerPackCardParams(
            base_path=p.base_path,
            sample_sticker_params=p.manifest.resolved_sample_sticker,
            name=p.manifest.name,
            slug=p.slug,
            description=p.manifest.description,
            index=str(i),
            unavailable=p.unavailable,
            unavailable_reason=p.unavailable_reason,
        )
        for (i, p) in enumerate(packs, 1)
    ]
    return draw_sticker_pack_grid(params)
