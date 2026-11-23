#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dialogue band batch composer v1.5.

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


def rgb_to_hex(rgb):
    """Format an RGB 3-tuple as '#RRGGBB'."""
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _outline_rgb(fg_rgb):
    r, g, b = fg_rgb
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if lum > 128 else (255, 255, 255)


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


def fit_text(
    draw,
    text,
    max_w,
    max_h,
    font_path,
    max_lines,
    start_size=44,
    min_size=20,
    step=2,
    line_height_mult=1.45,
):
    """Find the largest font size that fits text inside max_w x max_h within max_lines."""
    step = max(1, step)
    start_size = max(min_size, start_size)
    sizes = list(range(start_size, min_size - 1, -step))
    if sizes[-1] != min_size:
        sizes.append(min_size)

    for size in sizes:
        font = ImageFont.truetype(font_path, size)
        lines = _wrap_all_paragraphs(draw, text, font, max_w, max_lines)
        line_h = max(1, int(round(size * line_height_mult)))
        all_fit_w = all(draw.textlength(ln, font=font) <= max_w for ln in lines)
        if len(lines) <= max_lines and line_h * len(lines) <= max_h and all_fit_w:
            return font, lines, line_h, {
                "size": size,
                "shrunk": size < start_size,
                "overflow": False,
            }

    font = ImageFont.truetype(font_path, min_size)
    raw_lines = _wrap_all_paragraphs(draw, text, font, max_w, max_lines)
    line_h = max(1, int(round(min_size * line_height_mult)))
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


def _divider_color(band_color):
    r, g, b = band_color
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum < 128:
        return (min(255, r + 36), min(255, g + 36), min(255, b + 42))
    return (max(0, r - 36), max(0, g - 36), max(0, b - 42))


def _draw_extend_band(w, h, band_h, band_color, im, position="bottom"):
    canvas = Image.new("RGB", (w, h + band_h), band_color)
    border_h = max(1, w // 600)
    d = ImageDraw.Draw(canvas)
    div_col = _divider_color(band_color)
    if position == "top":
        canvas.paste(im, (0, band_h))
        d.rectangle([0, band_h - border_h, w - 1, band_h - 1], fill=div_col)
        return canvas, 0
    canvas.paste(im, (0, 0))
    d.rectangle([0, h, w - 1, h + border_h - 1], fill=div_col)
    return canvas, h


def _build_overlay_canvas(
    im,
    w,
    h,
    band_h,
    band_color,
    overlay_opacity,
    overlay_fade=0.30,
    overlay_margin=0.0,
    position="bottom",
):
    band_h = min(h, max(1, band_h))
    margin_px = min(max(0, h - band_h), max(0, int(round(h * max(0.0, float(overlay_margin))))))
    fade_ratio = max(0.0, min(0.60, float(overlay_fade)))
    opacity = max(0.0, min(1.0, float(overlay_opacity)))
    target_alpha = int(round(255 * opacity))

    if position == "top":
        top = margin_px
        bottom = top + band_h
        fade_top = min(top, int(round(band_h * fade_ratio * 0.5))) if margin_px > 0 else 0
        fade_bot = min(h - bottom, int(round(band_h * fade_ratio)))
    else:
        bottom = h - margin_px
        top = bottom - band_h
        fade_top = min(top, int(round(band_h * fade_ratio)))
        fade_bot = min(h - bottom, int(round(band_h * fade_ratio * 0.5))) if margin_px > 0 else 0

    if target_alpha == 0:
        return im.convert("RGBA"), top

    strip_h = fade_top + band_h + fade_bot
    grad = Image.new("RGBA", (1, strip_h), (0, 0, 0, 0))
    gpix = grad.load()
    for row in range(fade_top):
        t = (row + 1) / (fade_top + 1)
        gpix[0, row] = (*band_color, int(round(target_alpha * (t * t))))
    for row in range(fade_top, fade_top + band_h):
        gpix[0, row] = (*band_color, target_alpha)
    for k in range(fade_bot):
        t = (fade_bot - k) / (fade_bot + 1)
        gpix[0, fade_top + band_h + k] = (*band_color, int(round(target_alpha * (t * t))))

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    stretched = grad.resize((w, strip_h), Image.Resampling.NEAREST)
    overlay.paste(stretched, (0, top - fade_top))
    return Image.alpha_composite(im.convert("RGBA"), overlay), top


def render_blank_band(img_path, cfg):
    """Render an empty band (extend mode) onto `img_path` and return the PIL Image."""
    band_color = cfg["band_color"]
    im = _load_rgb_image(img_path, band_color)
    w, h = im.size
    band_h = max(1, int(round(w * cfg["band"])))
    canvas, _ = _draw_extend_band(w, h, band_h, band_color, im, position=cfg.get("position", "bottom"))
    return canvas


def process_blank_band(img_path, out_path, cfg):
    """Append an empty band (extend mode) to match dialogue-page aspect ratio."""
    canvas = render_blank_band(img_path, cfg)
    return save_image(canvas, out_path, fmt=cfg["format"], quality=cfg["quality"])


def _plate_fill_rgb(band_color, is_overlay):
    if is_overlay:
        return band_color
    r, g, b = band_color
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum < 128:
        return (min(255, r + 18), min(255, g + 19), min(255, b + 24))
    return (max(0, r - 18), max(0, g - 18), max(0, b - 16))


def parse_speaker_name_args(items):
    """Parse repeatable 'ORIG=NEW' speaker rename pairs into a dict."""
    out = {}
    for raw in items or ():
        if "=" not in raw:
            raise ValueError(f"Invalid --speaker-name format (expected ORIG=NEW): {raw!r}")
        orig, new = raw.split("=", 1)
        orig = orig.strip()
        new = new.strip()
        if orig:
            out[orig] = new
    return out


def apply_speaker_aliases(speaker, text, cfg):
    """Apply configured speaker display-name aliases and optional body substitutions."""
    aliases = cfg.get("speaker_names") or {}
    sp_clean = (speaker or "").strip()
    disp_speaker = aliases.get(sp_clean, "").strip() or sp_clean
    out_text = text or ""

    if aliases and out_text:
        ordered_keys = sorted((k for k in aliases if k), key=len, reverse=True)
        for k in ordered_keys:
            rep = aliases[k].strip() or k
            out_text = out_text.replace("{{" + k + "}}", rep).replace("{" + k + "}", rep)
        if cfg.get("replace_speaker_in_body"):
            active = [k for k in ordered_keys if aliases[k].strip()]
            if active:
                protected = set(active)
                if "\u5f7c" in protected:
                    protected.add("\u5f7c\u5973")
                pattern_keys = sorted(protected, key=len, reverse=True)
                pat = re.compile("|".join(re.escape(k) for k in pattern_keys))
                out_text = pat.sub(
                    lambda m: aliases.get(m.group(0), "").strip() or m.group(0), out_text
                )
    return disp_speaker, out_text


def _measure_speaker_metrics(draw, eff_speaker, size, speaker_style, gap_mult, bold_path):
    display_speaker = eff_speaker
    if speaker_style == "bracket" and not (
        eff_speaker.startswith("\u3010") and eff_speaker.endswith("\u3011")
    ):
        display_speaker = f"\u3010{eff_speaker}\u3011"
    f_name = ImageFont.truetype(bold_path, size)
    nb = draw.textbbox((0, 0), display_speaker, font=f_name)
    name_h = max(nb[3] - nb[1], int(round(size * 0.85)))
    if speaker_style == "plate":
        plate_pad_y = max(4, int(round(size * 0.22)))
        plate_pad_x = max(8, int(round(size * 0.42)))
        speaker_box_h = name_h + plate_pad_y * 2
    else:
        plate_pad_y = 0
        plate_pad_x = 0
        speaker_box_h = name_h
    name_gap = max(4, int(round(size * gap_mult)))
    name_block_h = speaker_box_h + name_gap
    return {
        "name_size": size,
        "f_name": f_name,
        "nb": nb,
        "name_h": name_h,
        "name_gap": name_gap,
        "name_block_h": name_block_h,
        "display_speaker": display_speaker,
        "plate_pad_x": plate_pad_x,
        "plate_pad_y": plate_pad_y,
        "speaker_box_h": speaker_box_h,
    }


def _compute_layout(w, h, speaker, text, cfg, draw):
    band_h = max(1, int(round(w * cfg["band"])))
    if cfg.get("mode") == "overlay":
        band_h = min(h, band_h)
    eff_speaker, eff_text = apply_speaker_aliases(speaker, text, cfg)

    scale = float(cfg.get("font_scale", 1.0))
    speaker_style = str(cfg.get("speaker_style", "plate")).lower()
    if speaker_style not in ("plate", "bar", "bracket", "plain"):
        speaker_style = "plate"
    gap_mult = max(0.15, min(1.50, float(cfg.get("speaker_gap", 0.50))))

    pad_x = max(0.01, min(0.35, float(cfg.get("pad_x", 0.045))))
    pad = max(4, min(max(4, (w - 20) // 2), int(round(w * pad_x))))
    v_pad = max(4, int(round(band_h * 0.10)))
    min_size = max(10, int(round(w * 0.024 * scale)))
    uniform_ratio = cfg.get("uniform_font_ratio")
    if uniform_ratio is not None:
        start_size = max(min_size, int(w * float(uniform_ratio) + 1e-6))
    else:
        start_size = max(14, int(round(w * 0.053 * scale)))
    start_size = max(min_size, start_size)
    step = max(1, int(round(w * 0.0024)))
    line_h_mult = max(1.0, float(cfg.get("line_height", 1.45)))
    max_body_w = max(1, w - pad * 2)

    if not eff_speaker:
        avail_h = max(1, band_h - v_pad * 2)
        font, lines, line_h, fit_meta = fit_text(
            draw,
            eff_text,
            max_body_w,
            avail_h,
            cfg["serif"],
            cfg["max_lines"],
            start_size=start_size,
            min_size=min_size,
            step=step,
            line_height_mult=line_h_mult,
        )
        sp_metrics = {
            "name_size": 0,
            "f_name": None,
            "nb": (0, 0, 0, 0),
            "name_h": 0,
            "name_gap": 0,
            "name_block_h": 0,
            "display_speaker": "",
            "plate_pad_x": 0,
            "plate_pad_y": 0,
            "speaker_box_h": 0,
        }
    else:
        sizes = list(range(start_size, min_size - 1, -step))
        if sizes[-1] != min_size:
            sizes.append(min_size)

        chosen = None
        for size in sizes:
            sp_m = _measure_speaker_metrics(draw, eff_speaker, size, speaker_style, gap_mult, cfg["bold"])
            avail_h = max(1, band_h - v_pad * 2 - sp_m["name_block_h"])
            font = ImageFont.truetype(cfg["font"], size)
            lines = _wrap_all_paragraphs(draw, eff_text, font, max_body_w, cfg["max_lines"])
            line_h = max(1, int(round(size * line_h_mult)))
            all_fit_w = all(draw.textlength(ln, font=font) <= max_body_w for ln in lines)
            if len(lines) <= cfg["max_lines"] and line_h * len(lines) <= avail_h and all_fit_w:
                chosen = (
                    sp_m,
                    font,
                    lines,
                    line_h,
                    {"size": size, "shrunk": size < start_size, "overflow": False},
                )
                break

        if chosen is not None:
            sp_metrics, font, lines, line_h, fit_meta = chosen
        else:
            sp_metrics = _measure_speaker_metrics(
                draw, eff_speaker, min_size, speaker_style, gap_mult, cfg["bold"]
            )
            avail_h = max(1, band_h - v_pad * 2 - sp_metrics["name_block_h"])
            font = ImageFont.truetype(cfg["font"], min_size)
            raw_lines = _wrap_all_paragraphs(draw, eff_text, font, max_body_w, cfg["max_lines"])
            line_h = max(1, int(round(min_size * line_h_mult)))
            cap = max(1, min(cfg["max_lines"], max(1, avail_h // line_h)))
            lines = raw_lines[:cap]
            overflow = len(raw_lines) > cap or any(
                draw.textlength(ln, font=font) > max_body_w for ln in lines
            )
            fit_meta = {
                "size": min_size,
                "shrunk": min_size < start_size,
                "overflow": overflow,
            }

    return {
        "band_h": band_h,
        "pad": pad,
        "v_pad": v_pad,
        "eff_speaker": eff_speaker,
        "eff_text": eff_text,
        "speaker_style": speaker_style,
        **sp_metrics,
        "font": font,
        "lines": lines,
        "line_h": line_h,
        "fit_meta": fit_meta,
    }


def compute_uniform_font_ratio(image_paths, script, cfg):
    """Scan dialogue images and return `(min_ratio, bottleneck_info)` for uniform font sizing."""
    scan_cfg = dict(cfg)
    scan_cfg["uniform_font_ratio"] = None
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)

    min_ratio = None
    bottleneck = None
    for p in image_paths:
        key = key_of(Path(p).name)
        if key not in script:
            continue
        sp, tx = script[key]
        if not tx:
            continue
        with Image.open(p) as raw:
            im = ImageOps.exif_transpose(raw)
            w, h = im.size
        layout = _compute_layout(w, h, sp, tx, scan_cfg, draw)
        sz = layout["fit_meta"]["size"]
        ratio = sz / max(1, w)
        if min_ratio is None or ratio < min_ratio:
            min_ratio = ratio
            bottleneck = {"key": key, "filename": Path(p).name, "size": sz, "width": w}
    return min_ratio, bottleneck


def check_layout_only(img_path, speaker, text, cfg):
    """Compute text layout for dry-run verification without saving files."""
    with Image.open(img_path) as raw:
        im = ImageOps.exif_transpose(raw)
        w, h = im.size
    dummy = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dummy)
    layout = _compute_layout(w, h, speaker, text, cfg, d)
    return layout["fit_meta"]


def render_image(img_path, speaker, text, cfg):
    """Render a dialogue band onto `img_path` and return `(canvas, fit_meta)`."""
    band_color = cfg["band_color"]
    im = _load_rgb_image(img_path, band_color)
    w, h = im.size
    position = cfg.get("position", "bottom")

    if cfg["mode"] == "extend":
        band_h = max(1, int(round(w * cfg["band"])))
        canvas, top = _draw_extend_band(w, h, band_h, band_color, im, position=position)
        draw_target = ImageDraw.Draw(canvas)
    else:
        band_h = min(h, max(1, int(round(w * cfg["band"]))))
        base, top = _build_overlay_canvas(
            im,
            w,
            h,
            band_h,
            band_color,
            cfg["overlay_opacity"],
            overlay_fade=cfg.get("overlay_fade", 0.30),
            overlay_margin=cfg.get("overlay_margin", 0.0),
            position=position,
        )
        txt_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_target = ImageDraw.Draw(txt_layer)

    layout = _compute_layout(w, h, speaker, text, cfg, draw_target)
    pad = layout["pad"]
    font = layout["font"]
    lines = layout["lines"]
    line_h = layout["line_h"]
    body_size = layout["fit_meta"]["size"]

    ref_b = draw_target.textbbox((0, 0), "\u3042\u6f22g", font=font)
    glyph_h = max(1, ref_b[3] - ref_b[1])
    total_block_h = layout["name_block_h"] + max(0, len(lines) - 1) * line_h + glyph_h

    centered_top = top + (band_h - total_block_h) // 2
    offset_px = int(round(band_h * float(cfg.get("text_offset_y", 0.0))))
    min_top = top + 2
    max_top = max(min_top, top + band_h - total_block_h - 2)
    block_top = max(min_top, min(max_top, centered_top + offset_px))

    is_overlay = cfg["mode"] == "overlay"
    shadow_color = (0, 0, 0, 190)

    outline_lvl = max(0, int(cfg.get("text_outline", 0)))
    body_stroke = max(1, int(round(outline_lvl * w / 832.0))) if outline_lvl > 0 else 0
    name_stroke = body_stroke
    eff_speaker = layout["eff_speaker"]

    if eff_speaker:
        speaker_color = (
            cfg["colors"].get(speaker)
            or cfg["colors"].get(eff_speaker)
            or MAIN_SPEAKER_COLOR
        )
        sp_outline = _outline_rgb(speaker_color)
        disp_sp = layout["display_speaker"]
        sp_style = layout["speaker_style"]
        sp_w = draw_target.textlength(disp_sp, font=layout["f_name"])
        glyph_sp_h = max(1, layout["nb"][3] - layout["nb"][1])
        s_off = max(1, layout["name_size"] // 22)

        if sp_style == "plate":
            accent_w = max(4, int(round(w / 180)))
            accent_gap = max(6, int(round(layout["name_size"] * 0.30)))
            plate_pad_x = layout["plate_pad_x"]
            plate_pad_y = layout["plate_pad_y"]
            bar_left_off = max(6, int(round(plate_pad_x * 0.75)))
            plate_w = bar_left_off + accent_w + accent_gap + sp_w + plate_pad_x
            plate_h = layout["speaker_box_h"]

            px0 = pad
            px1 = int(round(pad + plate_w))
            plate_box = [px0, block_top, px1, block_top + plate_h]
            radius = min(max(4, int(round(layout["name_size"] * 0.22))), max(1, plate_h // 2))
            border_w = max(1, w // 600)
            plate_bg = _plate_fill_rgb(band_color, is_overlay)

            bar_x = px0 + bar_left_off
            bar_top = block_top + plate_pad_y
            bar_bot = bar_top + layout["name_h"]
            bar_box = [bar_x, bar_top, bar_x + accent_w - 1, bar_bot]
            bar_rad = min(max(1, accent_w // 2), max(1, layout["name_h"] // 2))

            name_x = bar_x + accent_w + accent_gap
            name_y = bar_top + max(0, (layout["name_h"] - glyph_sp_h) // 2) - layout["nb"][1]

            if is_overlay:
                draw_target.rounded_rectangle(
                    [plate_box[0] + s_off, plate_box[1] + s_off, plate_box[2] + s_off, plate_box[3] + s_off],
                    radius=radius,
                    fill=(0, 0, 0, 145),
                )
                draw_target.rounded_rectangle(
                    plate_box,
                    radius=radius,
                    fill=(*plate_bg, 215),
                    outline=(*speaker_color, 195),
                    width=border_w,
                )
                draw_target.rounded_rectangle(bar_box, radius=bar_rad, fill=(*speaker_color, 255))
                draw_target.text(
                    (name_x + s_off, name_y + s_off),
                    disp_sp,
                    font=layout["f_name"],
                    fill=shadow_color,
                    stroke_width=name_stroke,
                    stroke_fill=shadow_color,
                )
                draw_target.text(
                    (name_x, name_y),
                    disp_sp,
                    font=layout["f_name"],
                    fill=(*speaker_color, 255),
                    stroke_width=name_stroke,
                    stroke_fill=(*sp_outline, 255) if name_stroke > 0 else None,
                )
            else:
                draw_target.rounded_rectangle(
                    plate_box,
                    radius=radius,
                    fill=plate_bg,
                    outline=speaker_color,
                    width=border_w,
                )
                draw_target.rounded_rectangle(bar_box, radius=bar_rad, fill=speaker_color)
                draw_target.text(
                    (name_x, name_y),
                    disp_sp,
                    font=layout["f_name"],
                    fill=speaker_color,
                    stroke_width=name_stroke,
                    stroke_fill=sp_outline if name_stroke > 0 else None,
                )

        elif sp_style == "bar":
            accent_w = max(4, int(round(w / 150)))
            accent_gap = max(8, int(round(layout["name_size"] * 0.32)))
            bar_x = pad

            bar_box = [bar_x, block_top, bar_x + accent_w - 1, block_top + layout["name_h"]]
            bar_rad = min(max(1, accent_w // 2), max(1, layout["name_h"] // 2))
            name_x = bar_x + accent_w + accent_gap
            name_y = block_top + max(0, (layout["name_h"] - glyph_sp_h) // 2) - layout["nb"][1]
            if is_overlay:
                draw_target.rounded_rectangle(
                    [bar_box[0] + s_off, bar_box[1] + s_off, bar_box[2] + s_off, bar_box[3] + s_off],
                    radius=bar_rad,
                    fill=shadow_color,
                )
                draw_target.text(
                    (name_x + s_off, name_y + s_off),
                    disp_sp,
                    font=layout["f_name"],
                    fill=shadow_color,
                    stroke_width=name_stroke,
                    stroke_fill=shadow_color,
                )
                draw_target.rounded_rectangle(bar_box, radius=bar_rad, fill=(*speaker_color, 255))
                draw_target.text(
                    (name_x, name_y),
                    disp_sp,
                    font=layout["f_name"],
                    fill=(*speaker_color, 255),
                    stroke_width=name_stroke,
                    stroke_fill=(*sp_outline, 255) if name_stroke > 0 else None,
                )
            else:
                draw_target.rounded_rectangle(bar_box, radius=bar_rad, fill=speaker_color)
                draw_target.text(
                    (name_x, name_y),
                    disp_sp,
                    font=layout["f_name"],
                    fill=speaker_color,
                    stroke_width=name_stroke,
                    stroke_fill=sp_outline if name_stroke > 0 else None,
                )

        else:
            # 'bracket' or 'plain'
            name_x = pad
            name_y = block_top + max(0, (layout["name_h"] - glyph_sp_h) // 2) - layout["nb"][1]
            if is_overlay:
                draw_target.text(
                    (name_x + s_off, name_y + s_off),
                    disp_sp,
                    font=layout["f_name"],
                    fill=shadow_color,
                    stroke_width=name_stroke,
                    stroke_fill=shadow_color,
                )
                draw_target.text(
                    (name_x, name_y),
                    disp_sp,
                    font=layout["f_name"],
                    fill=(*speaker_color, 255),
                    stroke_width=name_stroke,
                    stroke_fill=(*sp_outline, 255) if name_stroke > 0 else None,
                )
            else:
                draw_target.text(
                    (name_x, name_y),
                    disp_sp,
                    font=layout["f_name"],
                    fill=speaker_color,
                    stroke_width=name_stroke,
                    stroke_fill=sp_outline if name_stroke > 0 else None,
                )

        body_y = block_top + layout["speaker_box_h"] + layout["name_gap"] - ref_b[1]
    else:
        body_y = block_top - ref_b[1]

    body_rgb = cfg["text_color"] if eff_speaker else cfg["narration_color"]
    body_outline = _outline_rgb(body_rgb)
    b_off = max(1, body_size // 22)
    for ln in lines:
        ln_x = pad

        if is_overlay:
            draw_target.text(
                (ln_x + b_off, body_y + b_off),
                ln,
                font=font,
                fill=shadow_color,
                stroke_width=body_stroke,
                stroke_fill=shadow_color,
            )
            draw_target.text(
                (ln_x, body_y),
                ln,
                font=font,
                fill=(*body_rgb, 255),
                stroke_width=body_stroke,
                stroke_fill=(*body_outline, 255) if body_stroke > 0 else None,
            )
        else:
            draw_target.text(
                (ln_x, body_y),
                ln,
                font=font,
                fill=body_rgb,
                stroke_width=body_stroke,
                stroke_fill=body_outline if body_stroke > 0 else None,
            )
        body_y += line_h

    if is_overlay:
        canvas = Image.alpha_composite(base, txt_layer).convert("RGB")

    return canvas, layout["fit_meta"]


def process(img_path, speaker, text, out_path, cfg):
    """Render a dialogue band onto `img_path` and write the output image."""
    canvas, fit_meta = render_image(img_path, speaker, text, cfg)
    saved = save_image(canvas, out_path, fmt=cfg["format"], quality=cfg["quality"])
    return fit_meta, saved


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

    speaker_names = {}
    raw_names = file_cfg.get("speaker_names") or {}
    if isinstance(raw_names, dict):
        for k, v in raw_names.items():
            ks = str(k).strip()
            vs = str(v).strip()
            if ks and vs:
                speaker_names[ks] = vs
    cli_names = parse_speaker_name_args(getattr(args, "speaker_name", None))
    for k, v in cli_names.items():
        if v:
            speaker_names[k] = v
        else:
            speaker_names.pop(k, None)

    return {
        "mode": pick_opt(args.mode, "mode", "extend"),
        "band": float(pick_opt(args.band, "band", 0.24)),
        "max_lines": int(pick_opt(args.max_lines, "max_lines", 2)),
        "font_scale": float(pick_opt(args.font_scale, "font_scale", 1.0)),
        "uniform_height": bool(args.uniform_height or file_cfg.get("uniform_height", False)),
        "uniform_font": bool(args.uniform_font or file_cfg.get("uniform_font", False)),
        "uniform_font_ratio": None,
        "format": str(pick_opt(args.format, "format", "keep")).lower(),
        "quality": int(pick_opt(args.quality, "quality", 92)),
        "band_color": parse_color(pick_opt(args.band_color, "band_color", None), DEFAULT_BAND_COLOR),
        "text_color": parse_color(pick_opt(args.text_color, "text_color", None), DEFAULT_TEXT_COLOR),
        "narration_color": parse_color(
            pick_opt(args.narration_color, "narration_color", None), DEFAULT_NARRATION_COLOR
        ),
        "overlay_opacity": float(pick_opt(args.overlay_opacity, "overlay_opacity", 0.76)),
        "overlay_fade": float(pick_opt(args.overlay_fade, "overlay_fade", 0.30)),
        "overlay_margin": float(pick_opt(args.overlay_margin, "overlay_margin", 0.0)),
        "text_outline": int(pick_opt(args.text_outline, "text_outline", 0)),
        "position": str(pick_opt(args.position, "position", "bottom")).lower(),
        "text_offset_y": float(pick_opt(args.text_offset_y, "text_offset_y", 0.0)),
        "pad_x": float(pick_opt(args.pad_x, "pad_x", 0.045)),
        "line_height": float(pick_opt(args.line_height, "line_height", 1.45)),
        "speaker_style": str(pick_opt(args.speaker_style, "speaker_style", "plate")).lower(),
        "speaker_gap": float(pick_opt(args.speaker_gap, "speaker_gap", 0.50)),
        "speaker_names": speaker_names,
        "replace_speaker_in_body": bool(
            getattr(args, "replace_speaker_in_body", False)
            or file_cfg.get("replace_speaker_in_body", False)
        ),
        "auto_speaker_colors": bool(args.speaker_colors or file_cfg.get("auto_speaker_colors", False)),
        "colors": colors,
        **fonts,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dialogue band batch composer v1.5")
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
    ap.add_argument("--speaker-style", choices=["plate", "bar", "bracket", "plain"], default=None)
    ap.add_argument("--speaker-gap", type=float, default=None)
    ap.add_argument("--speaker-name", action="append", default=None, help="Rename speaker ORIG=NEW")
    ap.add_argument("--replace-speaker-in-body", action="store_true")
    ap.add_argument("--speaker-colors", action="store_true")
    ap.add_argument("--config", default=None)
    ap.add_argument("--uniform-height", action="store_true")
    ap.add_argument("--uniform-font", action="store_true")
    ap.add_argument("--position", choices=["bottom", "top"], default=None)
    ap.add_argument("--text-offset-y", type=float, default=None)
    ap.add_argument("--pad-x", type=float, default=None)
    ap.add_argument("--line-height", type=float, default=None)
    ap.add_argument("--overlay-opacity", type=float, default=None)
    ap.add_argument("--overlay-fade", type=float, default=None)
    ap.add_argument("--overlay-margin", type=float, default=None)
    ap.add_argument("--text-outline", type=int, choices=[0, 1, 2, 3, 4], default=None)
    ap.add_argument("--band-color", default=None)
    ap.add_argument("--text-color", default=None)
    ap.add_argument("--narration-color", default=None)
    ap.add_argument("--format", choices=["keep", "png", "jpg", "jpeg", "webp"], default=None)
    ap.add_argument("--quality", type=int, default=None)
    ap.add_argument("--export-html", action="store_true")
    ap.add_argument("--title", default=None, help="Story title for --export-html")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--only", default=None, help="Comma-separated keys to process (e.g. 001,003)")
    a = ap.parse_args(argv)

    src, out = Path(a.src), Path(a.out)
    if not src.is_dir():
        sys.exit(f"source folder not found: {src}")

    file_cfg = load_config(a.config) if a.config else {}
    cfg = build_cfg(a, file_cfg)

    only_keys = None
    if a.only:
        only_keys = {k.strip() for k in a.only.split(",") if k.strip()}

    if a.export_html:
        import export_html_viewer

        if a.dry_run:
            entries, seq_warnings = export_html_viewer.load_script_sequence(a.script)
            for msg in seq_warnings:
                print("warning:", msg)
            print(f"dry-run (html-viewer): entries={len(entries)} out={out}")
            return 0
        res = export_html_viewer.export_html_viewer(
            src, Path(a.script), out, cfg, title=a.title, only_keys=only_keys
        )
        for msg in res["warnings"]:
            print(msg)
        print(
            f"done (html-viewer): steps={res['steps']} images={res['images']} index={res['index_path']}"
        )
        if a.strict and any("no image for script key" in w or "skipped" in w for w in res["warnings"]):
            return 1
        return 0

    script, csv_warnings = load_script(a.script)
    for msg in csv_warnings:
        print("warning:", msg)

    if cfg["auto_speaker_colors"]:
        for key in sorted(script):
            sp = script[key][0]
            if sp and sp not in cfg["colors"]:
                cfg["colors"][sp] = PALETTE[len(cfg["colors"]) % len(PALETTE)]

    if not a.dry_run:
        out.mkdir(parents=True, exist_ok=True)

    target_files = [
        p
        for p in sorted(src.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]
    if only_keys is not None:
        target_files = [p for p in target_files if key_of(p.name) in only_keys]

    if cfg["uniform_font"]:
        min_ratio, bottleneck = compute_uniform_font_ratio(target_files, script, cfg)
        cfg["uniform_font_ratio"] = min_ratio
        if bottleneck:
            print(
                f"info: uniform-font active: {bottleneck['size']}px "
                f"(bottleneck: {bottleneck['filename']})"
            )

    n_text = 0
    n_copy = 0
    used = set()
    shrunk_keys = []
    overflow_keys = []

    for p in target_files:
        key = key_of(p.name)

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
