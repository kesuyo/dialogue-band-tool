#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dialogue band batch composer v1.1.

Usage:
    python3 add_dialogue_band.py SRC_DIR SCRIPT.csv OUT_DIR [options]

Script CSV (no header, UTF-8 / UTF-8-SIG): number,speaker,line
    001,彼女,……ねえ、今日はもう少しだけ、そばにいて？
    002,,（地の文・ナレーションは話者を空に）
Images whose number has no line are copied unchanged (or padded with --uniform-height).
"""

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import budoux

    _BUDOUX = budoux.load_default_japanese_parser()
except Exception:
    _BUDOUX = None

FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    # Windows (static fonts; avoid -VF.ttf which Pillow loads as Thin)
    "C:/Windows/Fonts/BIZ-UDGothicR.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/YuGothR.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/NotoSansCJKjp-Regular.otf",
]

SERIF_CANDIDATES = [
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-mincho/ipam.ttf",
    # Windows
    "C:/Windows/Fonts/BIZ-UDMinchoM.ttc",
    "C:/Windows/Fonts/yumindb.ttf",
    "C:/Windows/Fonts/yumin.ttf",
    "C:/Windows/Fonts/msmincho.ttc",
    # macOS
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/Library/Fonts/NotoSerifCJKjp-Regular.otf",
]

BOLD_CANDIDATES = [
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    # Windows
    "C:/Windows/Fonts/BIZ-UDGothicB.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/Library/Fonts/NotoSansCJKjp-Bold.otf",
]

SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".webp")
MAIN_SPEAKER_COLOR = (255, 158, 199)
DEFAULT_BAND_COLOR = (12, 12, 14)
DEFAULT_TEXT_COLOR = (255, 255, 255)
DEFAULT_NARRATION_COLOR = (234, 237, 245)
PALETTE = [
    (255, 158, 199),
    (150, 200, 255),
    (170, 235, 170),
    (255, 215, 140),
    (210, 170, 255),
    (255, 170, 150),
]

# Kinsoku (line-breaking rules) written as unicode escapes for encoding safety.
NO_START = set(
    "\u3001\u3002\uff0e\uff0c\uff1f\uff01\uff1a\uff1b\u30fb\u2026\u2025\u301c\uff5e\u30fc\u2014\u2015"
    "\u3063\u3083\u3085\u3087\u308e\u3041\u3043\u3045\u3047\u3049\u3095\u3096"
    "\u30a1\u30a3\u30a5\u30a7\u30a9\u30c3\u30e3\u30e5\u30e7\u30ee\u30f5\u30f6"
    "\u309d\u309e\u30fd\u30fe\u3005"
    "\uff09\u3015\uff3d\uff5d\u3009\u300b\u300d\u300f\u3011\u201d\u2019"
    "!?,.:;)]}%"
    "\uff05"
)
NO_END = set("\uff08\u3014\uff3b\uff5b\u3008\u300a\u300c\u300e\u3010\u201c\u2018([{")
WORD_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
DIGITS = set("0123456789")
INSEPARABLE_PAIRS = set("\u2026\u2025\u2014\u2015")
EXCL_QUEST = set("!?！？")
STRONG_END = set("\u3002\uff1f\uff01?!")
PAUSE_CHARS = set("\u3001\uff0c,\u30fb\uff1a\uff1b:;")
CLOSING_BRACKETS = set("\u300d\u300f\uff09\u3011\u300b\u3009\u3015\uff3d\uff5d\u201d\u2019")
SOKUON = set("\u3063\u30c3")


def pick(candidates, override=None, fallback=None):
    """Return the first valid font path from override, candidates, or fallback."""
    if override:
        if not Path(override).exists():
            raise FileNotFoundError(f"Font file not found: {override}")
        return str(override)
    for c in candidates:
        if Path(c).exists():
            return c
    if fallback:
        return fallback
    raise FileNotFoundError("Japanese font not found; pass --font PATH")


def resolve_fonts(
    font_opt=None,
    font_serif_opt=None,
    font_bold_opt=None,
    font_candidates=FONT_CANDIDATES,
    serif_candidates=SERIF_CANDIDATES,
    bold_candidates=BOLD_CANDIDATES,
):
    """Resolve regular, serif, and bold fonts with safe fallbacks."""
    body_font = pick(font_candidates, override=font_opt)
    serif_font = pick(serif_candidates, override=font_serif_opt, fallback=body_font)
    bold_font = pick(bold_candidates, override=font_bold_opt, fallback=body_font)
    return {"font": body_font, "serif": serif_font, "bold": bold_font}


def parse_color(val, default):
    """Parse an RGB tuple/list or '#RRGGBB' / '#RGB' hex color string."""
    if val is None:
        return default
    if isinstance(val, (list, tuple)) and len(val) == 3:
        return tuple(max(0, min(255, int(c))) for c in val)
    if isinstance(val, str):
        s = val.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    raise ValueError(f"Invalid RGB/hex color: {val!r}")


def _is_hiragana(ch):
    return "\u3040" <= ch <= "\u309f"


def _is_katakana(ch):
    return "\u30a0" <= ch <= "\u30ff"


def _is_kanji(ch):
    return "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" or ch == "\u3005"


def can_break(text, i):
    """Return True if breaking `text` between index `i-1` and `i` satisfies kinsoku rules."""
    if i <= 0 or i >= len(text):
        return True
    prv, nxt = text[i - 1], text[i]
    if nxt in NO_START:
        return False
    if prv in NO_END:
        return False
    if prv in WORD_CHARS and nxt in WORD_CHARS:
        return False
    if prv in DIGITS and nxt in ".%\uff05":
        return False
    if prv == "." and nxt in DIGITS and i >= 2 and text[i - 2] in DIGITS:
        return False
    if prv == nxt and prv in INSEPARABLE_PAIRS:
        return False
    if prv in EXCL_QUEST and nxt in EXCL_QUEST:
        return False
    return True


def get_budoux_cuts(text):
    """Return character indices where BudouX suggests chunk boundaries, if available."""
    if _BUDOUX is None or not text:
        return set()
    cuts = set()
    pos = 0
    for chunk in _BUDOUX.parse(text):
        pos += len(chunk)
        if 0 < pos < len(text):
            cuts.add(pos)
    return cuts


def break_penalty(text, i, budoux_cuts=None):
    """Score a line break position `i` in `text` (lower is more natural)."""
    if i <= 0 or i >= len(text):
        return 0
    prv, nxt = text[i - 1], text[i]
    score = 0

    if prv in STRONG_END or prv in CLOSING_BRACKETS or (prv in "\u2026\u2025" and nxt not in "\u2026\u2025"):
        score -= 100
    elif prv in PAUSE_CHARS or prv.isspace():
        score -= 65

    if nxt in NO_END:
        score -= 40

    if budoux_cuts and i in budoux_cuts:
        score -= 50

    if prv in SOKUON:
        score += 85
    elif _is_hiragana(prv) and (_is_kanji(nxt) or _is_katakana(nxt)):
        score -= 18
    elif (_is_kanji(prv) or _is_katakana(prv)) and _is_hiragana(nxt):
        score += 28
    elif (_is_kanji(prv) and _is_kanji(nxt)) or (_is_katakana(prv) and _is_katakana(nxt)):
        score += 18

    return score


def wrap_text(draw, text, font, max_w):
    """Greedy kinsoku-aware line wrapping fallback."""
    out = []
    for para in text.split("\n"):
        if para == "":
            out.append("")
            continue
        rest = para
        while rest:
            i = 0
            while i < len(rest) and draw.textlength(rest[: i + 1], font=font) <= max_w:
                i += 1
            if i == 0:
                i = 1
            if i >= len(rest):
                out.append(rest)
                break
            cut = i
            while cut > 1 and not can_break(rest, cut):
                cut -= 1
            if cut == 1 and not can_break(rest, 1):
                cut = i
            out.append(rest[:cut])
            rest = rest[cut:]
    return out


def rebalance(draw, lines, font, max_w, budoux_cuts=None):
    """Rebalance a 2-line paragraph when the second line is too short (< 25% of total)."""
    if len(lines) != 2:
        return lines
    joined = lines[0] + lines[1]
    total = draw.textlength(joined, font=font)
    if total == 0 or draw.textlength(lines[1], font=font) >= total * 0.25:
        return lines
    if budoux_cuts is None:
        budoux_cuts = get_budoux_cuts(joined)

    best = None
    best_cost = None
    for i in range(1, len(joined)):
        if not can_break(joined, i):
            continue
        w1 = draw.textlength(joined[:i], font=font)
        if w1 > max_w:
            break
        w2 = draw.textlength(joined[i:], font=font)
        if w2 > max_w:
            continue
        bal = abs(w1 - w2) / max(1.0, max_w) * 40.0
        cost = break_penalty(joined, i, budoux_cuts) + bal
        if w2 < total * 0.25:
            cost += 55.0
        if best_cost is None or cost < best_cost:
            best = (joined[:i], joined[i:])
            best_cost = cost
    return list(best) if best else lines


def wrap_paragraph_optimal(draw, para, font, max_w, max_lines):
    """Wrap a single paragraph cleanly using DP with kinsoku and break penalties."""
    if para == "":
        return [""]
    total_w = draw.textlength(para, font=font)
    if total_w <= max_w:
        return [para]
    if max_lines < 2:
        return wrap_text(draw, para, font, max_w)

    n = len(para)
    budoux_cuts = get_budoux_cuts(para)
    seg_w_cache = {}

    def seg_width(s, e):
        key = (s, e)
        w = seg_w_cache.get(key)
        if w is None:
            w = draw.textlength(para[s:e], font=font)
            seg_w_cache[key] = w
        return w

    # Try smallest line count k from 2..max_lines that admits a valid break;
    # compare across k using a modest per-line cost so clean clause breaks still win.
    best_lines = None
    best_total_cost = None
    char_pad = max(12.0, font.size * 0.6) if hasattr(font, "size") else 20.0

    for target_k in range(2, max_lines + 1):
        avg_w = total_w / target_k
        # dp[(lines_used, pos)] = (cost, prev_pos)
        dp = {(0, 0): (0.0, -1)}

        for step in range(target_k):
            is_last_line = step == target_k - 1
            for s in range(n):
                state = dp.get((step, s))
                if state is None:
                    continue
                base_cost, _ = state

                if is_last_line:
                    w = seg_width(s, n)
                    if w <= max_w:
                        line_cost = ((w - avg_w) / max(1.0, max_w)) ** 2 * 60.0
                        if w < total_w * 0.15:
                            line_cost += 90.0
                        elif w < total_w * 0.25 and target_k == 2:
                            line_cost += 55.0
                        elif w < avg_w * 0.45:
                            line_cost += 45.0
                        cand = base_cost + line_cost
                        nxt_state = dp.get((target_k, n))
                        if nxt_state is None or cand < nxt_state[0]:
                            dp[(target_k, n)] = (cand, s)
                    continue

                for e in range(s + 1, n):
                    w = seg_width(s, e)
                    if w > max_w + char_pad:
                        break
                    if w > max_w:
                        continue
                    if not can_break(para, e):
                        continue
                    line_cost = ((w - avg_w) / max(1.0, max_w)) ** 2 * 60.0
                    if w < avg_w * 0.45:
                        line_cost += 55.0
                    pen = break_penalty(para, e, budoux_cuts)
                    cand = base_cost + line_cost + pen
                    nxt_state = dp.get((step + 1, e))
                    if nxt_state is None or cand < nxt_state[0]:
                        dp[(step + 1, e)] = (cand, s)

        end_state = dp.get((target_k, n))
        if end_state is not None:
            total_cost = end_state[0] + (target_k - 2) * 40.0
            if best_total_cost is None or total_cost < best_total_cost:
                cuts = []
                cur_pos = n
                for step in range(target_k, 0, -1):
                    prev_pos = dp[(step, cur_pos)][1]
                    cuts.append(para[prev_pos:cur_pos])
                    cur_pos = prev_pos
                cuts.reverse()
                best_lines = cuts
                best_total_cost = total_cost

    if best_lines is not None:
        return best_lines
    return wrap_text(draw, para, font, max_w)


def _wrap_all_paragraphs(draw, text, font, max_w, max_lines):
    paragraphs = text.split("\n")
    num_p = len(paragraphs)
    lines = []
    for idx, para in enumerate(paragraphs):
        remaining_paras = num_p - idx - 1
        budget = max(1, max_lines - len(lines) - remaining_paras)
        lines.extend(wrap_paragraph_optimal(draw, para, font, max_w, budget))
    return lines


def fit_text(draw, text, max_w, max_h, font_path, max_lines, start_size=44, min_size=20, step=2):
    """Find the largest font size that fits text inside max_w x max_h within max_lines."""
    step = max(1, step)
    start_size = max(min_size, start_size)
    sizes = list(range(start_size, min_size - 1, -step))
    if sizes[-1] != min_size:
        sizes.append(min_size)

    for size in sizes:
        font = ImageFont.truetype(font_path, size)
        lines = _wrap_all_paragraphs(draw, text, font, max_w, max_lines)
        line_h = max(1, int(round(size * 1.45)))
        all_fit_w = all(draw.textlength(ln, font=font) <= max_w for ln in lines)
        if len(lines) <= max_lines and line_h * len(lines) <= max_h and all_fit_w:
            return font, lines, line_h, {
                "size": size,
                "shrunk": size < start_size,
                "overflow": False,
            }

    font = ImageFont.truetype(font_path, min_size)
    raw_lines = _wrap_all_paragraphs(draw, text, font, max_w, max_lines)
    line_h = max(1, int(round(min_size * 1.45)))
    cap = max(1, min(max_lines, max(1, max_h // line_h)))
    overflow = len(raw_lines) > cap or any(draw.textlength(ln, font=font) > max_w for ln in raw_lines[:cap])
    return font, raw_lines[:cap], line_h, {
        "size": min_size,
        "shrunk": min_size < start_size,
        "overflow": overflow,
    }


def _load_rgb_image(img_path, bg_color):
    with Image.open(img_path) as raw:
        im = ImageOps.exif_transpose(raw)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (*bg_color, 255))
            return Image.alpha_composite(bg, rgba).convert("RGB")
        return im.convert("RGB")


def save_image(im, out_path, fmt="keep", quality=92):
    """Save image with quality settings, optionally converting output format."""
    target = Path(out_path)
    chosen = fmt.lower()
    if chosen != "keep":
        ext = ".jpg" if chosen in ("jpg", "jpeg") else f".{chosen}"
        target = target.with_suffix(ext)

    ext_lower = target.suffix.lower()
    if ext_lower in (".jpg", ".jpeg"):
        im.save(target, format="JPEG", quality=quality, subsampling=0, optimize=True)
    elif ext_lower == ".webp":
        im.save(target, format="WEBP", quality=quality)
    else:
        im.save(target, format="PNG", optimize=True)
    return target


def _draw_extend_band(w, h, band_h, band_color, im):
    canvas = Image.new("RGB", (w, h + band_h), band_color)
    canvas.paste(im, (0, 0))
    border_h = max(1, w // 600)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, h, w - 1, h + border_h - 1], fill=(48, 48, 56))
    return canvas


def _build_overlay_canvas(im, w, h, band_h, band_color, overlay_opacity):
    top = h - band_h
    fade_h = min(top, int(round(band_h * 0.30)))
    target_alpha = max(0, min(255, int(round(255 * overlay_opacity))))

    strip_h = fade_h + band_h
    grad = Image.new("RGBA", (1, strip_h), (0, 0, 0, 0))
    gpix = grad.load()
    for row in range(fade_h):
        t = (row + 1) / max(1, fade_h)
        alpha = int(round(target_alpha * (t * t)))
        gpix[0, row] = (*band_color, alpha)
    for row in range(fade_h, strip_h):
        gpix[0, row] = (*band_color, target_alpha)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    stretched = grad.resize((w, strip_h), Image.Resampling.NEAREST)
    overlay.paste(stretched, (0, top - fade_h))
    return Image.alpha_composite(im.convert("RGBA"), overlay)


def process_blank_band(img_path, out_path, cfg):
    """Append an empty band (extend mode) to match dialogue-page aspect ratio."""
    band_color = cfg["band_color"]
    im = _load_rgb_image(img_path, band_color)
    w, h = im.size
    band_h = max(1, int(round(w * cfg["band"])))
    canvas = _draw_extend_band(w, h, band_h, band_color, im)
    return save_image(canvas, out_path, fmt=cfg["format"], quality=cfg["quality"])


def _compute_layout(w, h, speaker, text, cfg, draw):
    band_h = max(1, int(round(w * cfg["band"])))
    scale = cfg["font_scale"]
    pad = max(8, int(round(w * 0.045)))
    v_pad = max(4, int(round(band_h * 0.10)))
    name_size = max(12, int(round(w * 0.036 * scale)))
    start_size = max(14, int(round(w * 0.053 * scale)))
    min_size = max(10, int(round(w * 0.024 * scale)))
    step = max(1, int(round(w * 0.0024)))

    name_block_h = 0
    f_name = None
    nb = (0, 0, 0, 0)
    name_h = 0
    name_gap = 0
    if speaker:
        f_name = ImageFont.truetype(cfg["bold"], name_size)
        nb = draw.textbbox((0, 0), speaker, font=f_name)
        name_h = max(nb[3] - nb[1], int(round(name_size * 0.85)))
        name_gap = max(4, int(round(name_size * 0.45)))
        name_block_h = name_h + name_gap

    avail_h = max(1, band_h - v_pad * 2 - name_block_h)
    body_path = cfg["font"] if speaker else cfg["serif"]
    font, lines, line_h, fit_meta = fit_text(
        draw,
        text,
        max(1, w - pad * 2),
        avail_h,
        body_path,
        cfg["max_lines"],
        start_size=start_size,
        min_size=min_size,
        step=step,
    )
    return {
        "band_h": band_h,
        "pad": pad,
        "v_pad": v_pad,
        "name_size": name_size,
        "f_name": f_name,
        "nb": nb,
        "name_h": name_h,
        "name_gap": name_gap,
        "name_block_h": name_block_h,
        "font": font,
        "lines": lines,
        "line_h": line_h,
        "fit_meta": fit_meta,
    }


def check_layout_only(img_path, speaker, text, cfg):
    """Compute text layout for dry-run verification without saving files."""
    with Image.open(img_path) as raw:
        im = ImageOps.exif_transpose(raw)
        w, h = im.size
    dummy = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dummy)
    layout = _compute_layout(w, h, speaker, text, cfg, d)
    return layout["fit_meta"]


def process(img_path, speaker, text, out_path, cfg):
    """Render a dialogue band onto `img_path` and write the output image."""
    band_color = cfg["band_color"]
    im = _load_rgb_image(img_path, band_color)
    w, h = im.size

    if cfg["mode"] == "extend":
        band_h = max(1, int(round(w * cfg["band"])))
        canvas = _draw_extend_band(w, h, band_h, band_color, im)
        top = h
        draw_target = ImageDraw.Draw(canvas)
    else:
        band_h = max(1, int(round(w * cfg["band"])))
        base = _build_overlay_canvas(im, w, h, band_h, band_color, cfg["overlay_opacity"])
        top = h - band_h
        txt_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_target = ImageDraw.Draw(txt_layer)

    layout = _compute_layout(w, h, speaker, text, cfg, draw_target)
    pad = layout["pad"]
    v_pad = layout["v_pad"]
    font = layout["font"]
    lines = layout["lines"]
    line_h = layout["line_h"]
    body_size = layout["fit_meta"]["size"]

    ref_b = draw_target.textbbox((0, 0), "\u3042\u6f22g", font=font)
    glyph_h = max(1, ref_b[3] - ref_b[1])
    total_block_h = layout["name_block_h"] + max(0, len(lines) - 1) * line_h + glyph_h
    block_top = top + max(v_pad, (band_h - total_block_h) // 2)

    is_overlay = cfg["mode"] == "overlay"
    shadow_color = (0, 0, 0, 190)

    if speaker:
        accent_w = max(3, w // 220)
        accent_gap = max(6, int(round(layout["name_size"] * 0.3)))
        speaker_color = cfg["colors"].get(speaker, MAIN_SPEAKER_COLOR)
        bar_box = [pad, block_top, pad + accent_w - 1, block_top + layout["name_h"]]
        name_x = pad + accent_w + accent_gap
        name_y = block_top - layout["nb"][1]
        if is_overlay:
            s_off = max(1, layout["name_size"] // 22)
            draw_target.rectangle(
                [bar_box[0] + s_off, bar_box[1] + s_off, bar_box[2] + s_off, bar_box[3] + s_off],
                fill=shadow_color,
            )
            draw_target.text((name_x + s_off, name_y + s_off), speaker, font=layout["f_name"], fill=shadow_color)
            draw_target.rectangle(bar_box, fill=(*speaker_color, 255))
            draw_target.text((name_x, name_y), speaker, font=layout["f_name"], fill=(*speaker_color, 255))
        else:
            draw_target.rectangle(bar_box, fill=speaker_color)
            draw_target.text((name_x, name_y), speaker, font=layout["f_name"], fill=speaker_color)
        body_y = block_top + layout["name_h"] + layout["name_gap"] - ref_b[1]
    else:
        body_y = block_top - ref_b[1]

    body_rgb = cfg["text_color"] if speaker else cfg["narration_color"]
    b_off = max(1, body_size // 22)
    for ln in lines:
        if is_overlay:
            draw_target.text((pad + b_off, body_y + b_off), ln, font=font, fill=shadow_color)
            draw_target.text((pad, body_y), ln, font=font, fill=(*body_rgb, 255))
        else:
            draw_target.text((pad, body_y), ln, font=font, fill=body_rgb)
        body_y += line_h

    if is_overlay:
        canvas = Image.alpha_composite(base, txt_layer).convert("RGB")

    saved = save_image(canvas, out_path, fmt=cfg["format"], quality=cfg["quality"])
    return layout["fit_meta"], saved


def load_script(path):
    """Load script CSV (no header, UTF-8/UTF-8-SIG, supports multiline quoted cells)."""
    script = {}
    warnings = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for lineno, row in enumerate(reader, 1):
            if not row or all(not cell.strip() for cell in row):
                continue
            if row[0].lstrip().startswith("#"):
                continue
            if len(row) < 3:
                warnings.append(f"line {lineno} skipped (too few columns)")
                continue
            key = row[0].strip()
            if key.lower() in ("id", "no") or key == "\u756a\u53f7":
                continue
            if key in script:
                warnings.append(f"line {lineno}: duplicate script key '{key}' (overwriting previous)")
            speaker = row[1].strip()
            text = (
                row[2]
                .strip()
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .replace("\\n", "\n")
            )
            script[key] = (speaker, text)
    return script, warnings


def key_of(filename):
    """Extract leading key before the earliest '_', '-', or ' ' separator."""
    stem = Path(filename).stem
    return re.split(r"[_ \-]", stem, maxsplit=1)[0]


def load_config(path):
    """Load JSON configuration file."""
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Config JSON must be an object")
    return data


def build_cfg(args, file_cfg):
    """Merge defaults < config.json < CLI arguments into a single config dict."""
    def pick_opt(cli_val, cfg_key, default):
        if cli_val is not None:
            return cli_val
        if cfg_key in file_cfg and file_cfg[cfg_key] is not None:
            return file_cfg[cfg_key]
        return default

    fonts = resolve_fonts(
        font_opt=pick_opt(args.font, "font", None),
        font_serif_opt=pick_opt(args.font_serif, "font_serif", None),
        font_bold_opt=pick_opt(args.font_bold, "font_bold", None),
    )

    colors = {}
    raw_colors = file_cfg.get("speaker_colors") or {}
    if isinstance(raw_colors, dict):
        for sp, col in raw_colors.items():
            colors[sp] = parse_color(col, MAIN_SPEAKER_COLOR)

    return {
        "mode": pick_opt(args.mode, "mode", "extend"),
        "band": float(pick_opt(args.band, "band", 0.24)),
        "max_lines": int(pick_opt(args.max_lines, "max_lines", 2)),
        "font_scale": float(pick_opt(args.font_scale, "font_scale", 1.0)),
        "uniform_height": bool(args.uniform_height or file_cfg.get("uniform_height", False)),
        "format": str(pick_opt(args.format, "format", "keep")).lower(),
        "quality": int(pick_opt(args.quality, "quality", 92)),
        "band_color": parse_color(file_cfg.get("band_color"), DEFAULT_BAND_COLOR),
        "text_color": parse_color(file_cfg.get("text_color"), DEFAULT_TEXT_COLOR),
        "narration_color": parse_color(file_cfg.get("narration_color"), DEFAULT_NARRATION_COLOR),
        "overlay_opacity": float(file_cfg.get("overlay_opacity", 0.76)),
        "auto_speaker_colors": bool(args.speaker_colors or file_cfg.get("auto_speaker_colors", False)),
        "colors": colors,
        **fonts,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dialogue band batch composer v1.1")
    ap.add_argument("src")
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--mode", choices=["extend", "overlay"], default=None)
    ap.add_argument("--band", type=float, default=None)
    ap.add_argument("--max-lines", type=int, default=None)
    ap.add_argument("--font", default=None)
    ap.add_argument("--font-serif", default=None)
    ap.add_argument("--font-bold", default=None)
    ap.add_argument("--font-scale", type=float, default=None)
    ap.add_argument("--speaker-colors", action="store_true")
    ap.add_argument("--config", default=None)
    ap.add_argument("--uniform-height", action="store_true")
    ap.add_argument("--format", choices=["keep", "png", "jpg", "jpeg", "webp"], default=None)
    ap.add_argument("--quality", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--only", default=None, help="Comma-separated keys to process (e.g. 001,003)")
    a = ap.parse_args(argv)

    src, out = Path(a.src), Path(a.out)
    if not src.is_dir():
        sys.exit(f"source folder not found: {src}")

    file_cfg = load_config(a.config) if a.config else {}
    cfg = build_cfg(a, file_cfg)

    script, csv_warnings = load_script(a.script)
    for msg in csv_warnings:
        print("warning:", msg)

    if cfg["auto_speaker_colors"]:
        for key in sorted(script):
            sp = script[key][0]
            if sp and sp not in cfg["colors"]:
                cfg["colors"][sp] = PALETTE[len(cfg["colors"]) % len(PALETTE)]

    only_keys = None
    if a.only:
        only_keys = {k.strip() for k in a.only.split(",") if k.strip()}

    if not a.dry_run:
        out.mkdir(parents=True, exist_ok=True)

    n_text = 0
    n_copy = 0
    used = set()
    shrunk_keys = []
    overflow_keys = []

    for p in sorted(src.iterdir()):
        if not p.is_file() or p.suffix.lower() not in SUPPORTED_EXTS:
            continue
        key = key_of(p.name)
        if only_keys is not None and key not in only_keys:
            continue

        if key in script:
            used.add(key)
            sp, tx = script[key]
            if tx:
                if a.dry_run:
                    meta = check_layout_only(p, sp, tx, cfg)
                else:
                    meta, _ = process(p, sp, tx, out / p.name, cfg)
                if meta["shrunk"]:
                    shrunk_keys.append((key, meta["size"]))
                if meta["overflow"]:
                    overflow_keys.append(key)
                    print(f"WARNING [OVERFLOW]: key '{key}' ({p.name}) truncated at min font size {meta['size']}px")
                n_text += 1
                continue
        else:
            print(f"warning: no script entry for image '{p.name}' (key '{key}')")

        if not a.dry_run:
            if cfg["uniform_height"] and cfg["mode"] == "extend":
                process_blank_band(p, out / p.name, cfg)
            elif cfg["format"] != "keep":
                im = _load_rgb_image(p, cfg["band_color"])
                save_image(im, out / p.name, fmt=cfg["format"], quality=cfg["quality"])
            else:
                shutil.copy2(p, out / p.name)
        n_copy += 1

    unmatched_script = []
    for key in script:
        if only_keys is not None and key not in only_keys:
            continue
        if key not in used:
            unmatched_script.append(key)
            print("warning: no image for script key", key)

    if shrunk_keys:
        details = ", ".join(f"{k}({sz}px)" for k, sz in shrunk_keys)
        print(f"info: auto-shrunk text on {len(shrunk_keys)} image(s): {details}")

    prefix = "dry-run" if a.dry_run else "done"
    print(f"{prefix}: with-dialogue={n_text} copied={n_copy} mode={cfg['mode']} out={out}")

    if a.strict and (csv_warnings or unmatched_script or overflow_keys):
        print(
            f"strict failure: csv_warnings={len(csv_warnings)} "
            f"unmatched_script={len(unmatched_script)} overflow={len(overflow_keys)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
