#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop GUI for Dialogue Band Batch Composer v1.2."""

import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from PIL import Image, ImageTk

import add_dialogue_band as adb

try:
    import ctypes

    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / ".gui_state.json"


class DialogueBandApp:
    """Tkinter desktop GUI with tabbed controls, live preview, and background batch runner."""

    def __init__(self, root):
        self.root = root
        self.root.title("帯テキスト一括合成ツール v1.2")
        self.root.geometry("1160x800")
        self.root.minsize(960, 680)

        self._initializing = True
        self.speaker_colors = {}
        self.image_files = []
        self._preview_pil = None
        self._preview_photo = None
        self._resize_job = None
        self._preview_job = None
        self._uniform_cache = (None, None)  # (cache_key, (min_ratio, bottleneck))
        self._running = False
        self._action_buttons = []

        self._init_vars()
        self._build_ui()
        self._load_initial_state()
        self._initializing = False
        self.refresh_preview()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_vars(self):
        self.src_var = tk.StringVar()
        self.script_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.config_var = tk.StringVar()

        # Basic settings
        self.mode_var = tk.StringVar(value="extend")
        self.band_var = tk.StringVar(value="0.24")
        self.max_lines_var = tk.StringVar(value="2")
        self.font_scale_var = tk.StringVar(value="1.0")
        self.format_var = tk.StringVar(value="keep")
        self.quality_var = tk.StringVar(value="92")
        self.uniform_font_var = tk.BooleanVar(value=False)
        self.auto_colors_var = tk.BooleanVar(value=False)
        self.uniform_height_var = tk.BooleanVar(value=False)

        # Position / Transparency / Colors
        self.position_var = tk.StringVar(value="bottom")
        self.align_var = tk.StringVar(value="left")
        self.text_offset_y_var = tk.DoubleVar(value=0.0)
        self.pad_x_var = tk.DoubleVar(value=4.5)
        self.line_height_var = tk.DoubleVar(value=1.45)
        self.overlay_opacity_var = tk.DoubleVar(value=76.0)
        self.overlay_fade_var = tk.DoubleVar(value=30.0)
        self.overlay_margin_var = tk.DoubleVar(value=0.0)
        self.text_outline_var = tk.StringVar(value="0")

        self.band_color_var = tk.StringVar(value=adb.rgb_to_hex(adb.DEFAULT_BAND_COLOR))
        self.text_color_var = tk.StringVar(value=adb.rgb_to_hex(adb.DEFAULT_TEXT_COLOR))
        self.narration_color_var = tk.StringVar(value=adb.rgb_to_hex(adb.DEFAULT_NARRATION_COLOR))
        self.speaker_sel_var = tk.StringVar()

        # Scale readout labels
        self.offset_y_lbl_var = tk.StringVar(value="0%")
        self.pad_x_lbl_var = tk.StringVar(value="4.5%")
        self.line_h_lbl_var = tk.StringVar(value="1.45")
        self.opacity_lbl_var = tk.StringVar(value="76%")
        self.fade_lbl_var = tk.StringVar(value="30%")
        self.margin_lbl_var = tk.StringVar(value="0.0%")

        # Fonts & Filters
        self.only_var = tk.StringVar()
        self.font_var = tk.StringVar()
        self.font_serif_var = tk.StringVar()
        self.font_bold_var = tk.StringVar()

        # Preview & Status
        self.preview_sel_var = tk.StringVar()
        self.preview_info_var = tk.StringVar(value="画像を選択してください")
        self.status_var = tk.StringVar(value="待機中")
        self.progress_var = tk.DoubleVar(value=0.0)

    def _build_ui(self):
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        left = ttk.Frame(outer, width=455)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        left.rowconfigure(1, weight=0)

        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=1)

        self._build_left_pane(left)
        self._build_right_pane(right)

    def _add_path_row(self, parent, row, label, var, cmd, extra_btns=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 6))
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=3)
        btn_box = ttk.Frame(parent)
        btn_box.grid(row=row, column=2, sticky="e", padx=(6, 0), pady=3)
        ttk.Button(btn_box, text="参照", width=5, command=cmd).pack(side="left")
        if extra_btns:
            for txt, bcmd in extra_btns:
                ttk.Button(btn_box, text=txt, width=5, command=bcmd).pack(side="left", padx=(4, 0))

    def _build_left_pane(self, parent):
        nb = ttk.Notebook(parent)
        nb.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        tab_basic = ttk.Frame(nb, padding=8)
        tab_style = ttk.Frame(nb, padding=8)
        tab_detail = ttk.Frame(nb, padding=8)
        nb.add(tab_basic, text=" 基本 ")
        nb.add(tab_style, text=" 位置・透過・色 ")
        nb.add(tab_detail, text=" フォント・詳細 ")

        self._build_tab_basic(tab_basic)
        self._build_tab_style(tab_style)
        self._build_tab_detail(tab_detail)

        # Always-visible action area
        f_act = ttk.LabelFrame(parent, text="実行", padding=8)
        f_act.grid(row=1, column=0, sticky="ew")
        f_act.columnconfigure(0, weight=1)
        f_act.columnconfigure(1, weight=1)

        btn_preview = ttk.Button(f_act, text="プレビュー更新", command=self.refresh_preview)
        btn_preview.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        btn_dry = ttk.Button(f_act, text="チェックのみ (Dry-run)", command=lambda: self._start_worker(dry_run=True))
        btn_dry.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))

        btn_run = ttk.Button(f_act, text="一括生成を実行", command=lambda: self._start_worker(dry_run=False))
        btn_run.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(0, 8))
        btn_open = ttk.Button(f_act, text="出力フォルダを開く", command=self.open_output_dir)
        btn_open.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(0, 8))

        self._action_buttons = [btn_preview, btn_dry, btn_run, btn_open]

        self.progress_bar = ttk.Progressbar(f_act, variable=self.progress_var, maximum=100.0)
        self.progress_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(f_act, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, sticky="w")

    def _build_tab_basic(self, parent):
        parent.columnconfigure(0, weight=1)

        f_paths = ttk.LabelFrame(parent, text="フォルダ・台本・設定", padding=8)
        f_paths.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        f_paths.columnconfigure(1, weight=1)

        self._add_path_row(f_paths, 0, "画像フォルダ", self.src_var, self._browse_src)
        self._add_path_row(f_paths, 1, "台本CSV", self.script_var, self._browse_script)
        self._add_path_row(f_paths, 2, "出力フォルダ", self.out_var, self._browse_out)
        self._add_path_row(
            f_paths,
            3,
            "設定JSON",
            self.config_var,
            self._browse_config,
            extra_btns=[("読込", self._on_load_config_btn), ("保存", self._on_save_config_btn)],
        )

        f_opt = ttk.LabelFrame(parent, text="基本設定", padding=8)
        f_opt.grid(row=1, column=0, sticky="ew")
        f_opt.columnconfigure(1, weight=1)
        f_opt.columnconfigure(3, weight=1)

        ttk.Label(f_opt, text="方式").grid(row=0, column=0, sticky="w", pady=4)
        mode_box = ttk.Frame(f_opt)
        mode_box.grid(row=0, column=1, columnspan=3, sticky="w", pady=4)
        ttk.Radiobutton(
            mode_box, text="extend（下に継ぎ足し）", value="extend", variable=self.mode_var, command=self.schedule_preview
        ).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(
            mode_box, text="overlay（半透明重ね）", value="overlay", variable=self.mode_var, command=self.schedule_preview
        ).pack(side="left")

        ttk.Label(f_opt, text="帯の高さ比率").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            f_opt,
            from_=0.10,
            to=0.60,
            increment=0.02,
            textvariable=self.band_var,
            width=8,
            command=self.schedule_preview,
        ).grid(row=1, column=1, sticky="w", pady=4, padx=(0, 10))

        ttk.Label(f_opt, text="最大行数").grid(row=1, column=2, sticky="w", pady=4, padx=(0, 6))
        ttk.Spinbox(
            f_opt, from_=1, to=6, increment=1, textvariable=self.max_lines_var, width=6, command=self.schedule_preview
        ).grid(row=1, column=3, sticky="w", pady=4)

        ttk.Label(f_opt, text="フォント倍率").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            f_opt,
            from_=0.50,
            to=2.00,
            increment=0.05,
            textvariable=self.font_scale_var,
            width=8,
            command=self.schedule_preview,
        ).grid(row=2, column=1, sticky="w", pady=4, padx=(0, 10))

        ttk.Label(f_opt, text="出力形式").grid(row=2, column=2, sticky="w", pady=4, padx=(0, 6))
        fmt_box = ttk.Frame(f_opt)
        fmt_box.grid(row=2, column=3, sticky="w", pady=4)
        ttk.Combobox(
            fmt_box, textvariable=self.format_var, values=("keep", "png", "jpg", "webp"), state="readonly", width=6
        ).pack(side="left")
        ttk.Label(fmt_box, text="画質").pack(side="left", padx=(6, 2))
        ttk.Spinbox(fmt_box, from_=50, to=100, increment=1, textvariable=self.quality_var, width=4).pack(side="left")

        ttk.Checkbutton(
            f_opt,
            text="全ページの文字サイズを統一 (--uniform-font)",
            variable=self.uniform_font_var,
            command=self.schedule_preview,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 2))
        ttk.Checkbutton(
            f_opt,
            text="話者ごとに自動色分け (--speaker-colors)",
            variable=self.auto_colors_var,
            command=self.schedule_preview,
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=2)
        ttk.Checkbutton(
            f_opt,
            text="セリフなし画像も高さを揃える (extend時)",
            variable=self.uniform_height_var,
            command=self.schedule_preview,
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=2)

    def _add_scale_row(self, parent, row, label, var, lbl_var, frm, to, fmt_fn, reset_val=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 6))

        def on_move(_val):
            lbl_var.set(fmt_fn(var.get()))
            if not self._initializing:
                self.schedule_preview(80)

        sc = ttk.Scale(parent, from_=frm, to=to, variable=var, orient="horizontal", command=on_move)
        sc.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Label(parent, textvariable=lbl_var, width=6, anchor="e").grid(row=row, column=2, sticky="e", padx=(4, 0))
        if reset_val is not None:
            def do_reset():
                var.set(reset_val)
                lbl_var.set(fmt_fn(reset_val))
                self.schedule_preview(50)

            ttk.Button(parent, text="戻す", width=4, command=do_reset).grid(row=row, column=3, padx=(4, 0))

    def _build_tab_style(self, parent):
        parent.columnconfigure(0, weight=1)

        f_pos = ttk.LabelFrame(parent, text="位置・余白・行間", padding=8)
        f_pos.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        f_pos.columnconfigure(1, weight=1)

        ttk.Label(f_pos, text="帯の位置").grid(row=0, column=0, sticky="w", pady=2)
        pos_box = ttk.Frame(f_pos)
        pos_box.grid(row=0, column=1, columnspan=3, sticky="w", pady=2)
        ttk.Radiobutton(
            pos_box, text="下部 (bottom)", value="bottom", variable=self.position_var, command=self.schedule_preview
        ).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(
            pos_box, text="上部 (top)", value="top", variable=self.position_var, command=self.schedule_preview
        ).pack(side="left")

        ttk.Label(f_pos, text="文字揃え").grid(row=1, column=0, sticky="w", pady=2)
        aln_box = ttk.Frame(f_pos)
        aln_box.grid(row=1, column=1, columnspan=3, sticky="w", pady=2)
        for txt, val in (("左", "left"), ("中央", "center"), ("右", "right")):
            ttk.Radiobutton(
                aln_box, text=txt, value=val, variable=self.align_var, command=self.schedule_preview
            ).pack(side="left", padx=(0, 10))

        self._add_scale_row(
            f_pos, 2, "上下位置", self.text_offset_y_var, self.offset_y_lbl_var, -35.0, 35.0,
            lambda v: f"{v:+.0f}%", reset_val=0.0,
        )
        self._add_scale_row(
            f_pos, 3, "左右余白", self.pad_x_var, self.pad_x_lbl_var, 1.0, 25.0,
            lambda v: f"{v:.1f}%", reset_val=4.5,
        )
        self._add_scale_row(
            f_pos, 4, "行間倍率", self.line_height_var, self.line_h_lbl_var, 1.10, 2.00,
            lambda v: f"{v:.2f}", reset_val=1.45,
        )

        f_ov = ttk.LabelFrame(parent, text="半透明 (overlay)・縁取り", padding=8)
        f_ov.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        f_ov.columnconfigure(1, weight=1)

        self._add_scale_row(
            f_ov, 0, "透過の濃さ", self.overlay_opacity_var, self.opacity_lbl_var, 0.0, 100.0,
            lambda v: f"{v:.0f}%", reset_val=76.0,
        )
        self._add_scale_row(
            f_ov, 1, "グラデ幅", self.overlay_fade_var, self.fade_lbl_var, 0.0, 60.0,
            lambda v: f"{v:.0f}%", reset_val=30.0,
        )
        self._add_scale_row(
            f_ov, 2, "端マージン", self.overlay_margin_var, self.margin_lbl_var, 0.0, 25.0,
            lambda v: f"{v:.1f}%", reset_val=0.0,
        )

        ttk.Label(f_ov, text="文字縁取り").grid(row=3, column=0, sticky="w", pady=3)
        out_box = ttk.Frame(f_ov)
        out_box.grid(row=3, column=1, columnspan=3, sticky="w", pady=3)
        ttk.Spinbox(
            out_box, from_=0, to=4, increment=1, textvariable=self.text_outline_var, width=5,
            command=self.schedule_preview,
        ).pack(side="left")
        ttk.Label(out_box, text="0=なし / 1〜4 (薄い透過でも見やすくなります)", foreground="#666666").pack(
            side="left", padx=(8, 0)
        )

        f_col = ttk.LabelFrame(parent, text="カラー設定", padding=8)
        f_col.grid(row=2, column=0, sticky="ew")
        f_col.columnconfigure(1, weight=1)

        self._color_swatches = {}
        row_colors = ttk.Frame(f_col)
        row_colors.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        for idx, (title, cvar) in enumerate(
            (("帯色", self.band_color_var), ("本文", self.text_color_var), ("地の文", self.narration_color_var))
        ):
            ttk.Label(row_colors, text=title).pack(side="left", padx=(0 if idx == 0 else 10, 4))
            sw = tk.Label(row_colors, width=3, relief="solid", bd=1, bg=cvar.get())
            sw.pack(side="left", padx=(0, 4))
            self._color_swatches[title] = (sw, cvar)
            ttk.Button(
                row_colors,
                text="変更",
                width=4,
                command=lambda t=title, v=cvar: self._pick_color_var(t, v),
            ).pack(side="left")

        sp_row = ttk.Frame(f_col)
        sp_row.grid(row=1, column=0, columnspan=4, sticky="ew")
        ttk.Label(sp_row, text="話者色").pack(side="left", padx=(0, 6))
        self.speaker_combo = ttk.Combobox(sp_row, textvariable=self.speaker_sel_var, state="readonly", width=12)
        self.speaker_combo.pack(side="left", padx=(0, 6))
        self.speaker_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_speaker_swatch())
        self.speaker_swatch = tk.Label(sp_row, width=3, relief="solid", bd=1, bg="#FF9EC7")
        self.speaker_swatch.pack(side="left", padx=(0, 6))
        ttk.Button(sp_row, text="色変更", width=6, command=self._pick_speaker_color).pack(side="left", padx=(0, 4))
        ttk.Button(sp_row, text="解除", width=5, command=self._clear_speaker_color).pack(side="left")

    def _build_tab_detail(self, parent):
        parent.columnconfigure(0, weight=1)

        f_fonts = ttk.LabelFrame(parent, text="フォント指定 (空欄時は自動検出)", padding=8)
        f_fonts.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        f_fonts.columnconfigure(1, weight=1)

        self._add_path_row(
            f_fonts, 0, "本文フォント", self.font_var, lambda: self._browse_font(self.font_var),
            extra_btns=[("ｸﾘｱ", lambda: self._clear_var(self.font_var))],
        )
        self._add_path_row(
            f_fonts, 1, "明朝(地の文)", self.font_serif_var, lambda: self._browse_font(self.font_serif_var),
            extra_btns=[("ｸﾘｱ", lambda: self._clear_var(self.font_serif_var))],
        )
        self._add_path_row(
            f_fonts, 2, "太字(話者名)", self.font_bold_var, lambda: self._browse_font(self.font_bold_var),
            extra_btns=[("ｸﾘｱ", lambda: self._clear_var(self.font_bold_var))],
        )

        f_misc = ttk.LabelFrame(parent, text="その他", padding=8)
        f_misc.grid(row=1, column=0, sticky="ew")
        f_misc.columnconfigure(1, weight=1)

        ttk.Label(f_misc, text="対象キー (任意)").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 6))
        ttk.Entry(f_misc, textvariable=self.only_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(f_misc, text="例: 001,003", foreground="#666666").grid(row=0, column=2, sticky="w", padx=(6, 0))

        ttk.Button(f_misc, text="位置・透過・色設定を初期値に戻す", command=self.reset_style_defaults).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 2)
        )

    def _build_right_pane(self, parent):
        f_prev = ttk.LabelFrame(parent, text="プレビュー", padding=6)
        f_prev.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        f_prev.columnconfigure(0, weight=1)
        f_prev.rowconfigure(1, weight=1)

        nav = ttk.Frame(f_prev)
        nav.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        nav.columnconfigure(3, weight=1)

        ttk.Button(nav, text="◀ 前", width=6, command=lambda: self._step_preview(-1)).grid(row=0, column=0, padx=(0, 4))
        self.preview_combo = ttk.Combobox(nav, textvariable=self.preview_sel_var, state="readonly", width=22)
        self.preview_combo.grid(row=0, column=1, padx=(0, 4))
        self.preview_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_preview())
        ttk.Button(nav, text="次 ▶", width=6, command=lambda: self._step_preview(1)).grid(row=0, column=2, padx=(0, 10))
        ttk.Label(nav, textvariable=self.preview_info_var).grid(row=0, column=3, sticky="w")

        self.preview_container = tk.Frame(f_prev, bg="#1E1E22")
        self.preview_container.grid(row=1, column=0, sticky="nsew")
        self.preview_container.pack_propagate(False)
        self.preview_container.bind("<Configure>", self._on_preview_resize)

        self.preview_label = tk.Label(
            self.preview_container,
            bg="#1E1E22",
            fg="#C5C8D4",
            text="画像フォルダを選択するとプレビューが表示されます",
        )
        self.preview_label.pack(fill="both", expand=True)

        f_log = ttk.LabelFrame(parent, text="実行ログ", padding=6)
        f_log.grid(row=1, column=0, sticky="nsew")
        f_log.columnconfigure(0, weight=1)
        f_log.rowconfigure(0, weight=1)

        self.log_text = tk.Text(f_log, height=8, state="disabled", wrap="word", font=("Consolas", 9))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(f_log, orient="vertical", command=self.log_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sb.set)

    # --- Color & Style Helpers ---

    def _sync_scale_labels(self):
        self.offset_y_lbl_var.set(f"{self.text_offset_y_var.get():+.0f}%")
        self.pad_x_lbl_var.set(f"{self.pad_x_var.get():.1f}%")
        self.line_h_lbl_var.set(f"{self.line_height_var.get():.2f}")
        self.opacity_lbl_var.set(f"{self.overlay_opacity_var.get():.0f}%")
        self.fade_lbl_var.set(f"{self.overlay_fade_var.get():.0f}%")
        self.margin_lbl_var.set(f"{self.overlay_margin_var.get():.1f}%")

    def _sync_color_swatches(self):
        for sw, cvar in self._color_swatches.values():
            try:
                rgb = adb.parse_color(cvar.get(), adb.DEFAULT_BAND_COLOR)
                sw.configure(bg=adb.rgb_to_hex(rgb))
            except Exception:
                pass
        self._sync_speaker_swatch()

    def _pick_color_var(self, title, cvar):
        init_col = cvar.get()
        _, hex_col = colorchooser.askcolor(color=init_col, title=f"{title}を選択")
        if hex_col:
            cvar.set(hex_col.upper())
            self._sync_color_swatches()
            self.schedule_preview(50)

    def _refresh_speaker_list(self, script=None):
        names = list(self.speaker_colors.keys())
        if script is None:
            script_path = self.script_var.get().strip()
            if script_path and Path(script_path).is_file():
                try:
                    script, _ = adb.load_script(script_path)
                except Exception:
                    script = {}
            else:
                script = {}
        for key in sorted(script):
            sp = script[key][0]
            if sp and sp not in names:
                names.append(sp)
        self.speaker_combo["values"] = names
        if names and self.speaker_sel_var.get() not in names:
            self.speaker_sel_var.set(names[0])
        elif not names:
            self.speaker_sel_var.set("")
        self._sync_speaker_swatch()

    def _sync_speaker_swatch(self):
        sp = self.speaker_sel_var.get()
        if sp and sp in self.speaker_colors:
            try:
                rgb = adb.parse_color(self.speaker_colors[sp], adb.MAIN_SPEAKER_COLOR)
                self.speaker_swatch.configure(bg=adb.rgb_to_hex(rgb))
                return
            except Exception:
                pass
        self.speaker_swatch.configure(bg=adb.rgb_to_hex(adb.MAIN_SPEAKER_COLOR))

    def _pick_speaker_color(self):
        sp = self.speaker_sel_var.get().strip()
        if not sp:
            messagebox.showinfo("お知らせ", "台本CSVを読み込むか話者を選択してください。")
            return
        cur = self.speaker_colors.get(sp, adb.rgb_to_hex(adb.MAIN_SPEAKER_COLOR))
        _, hex_col = colorchooser.askcolor(color=cur, title=f"話者「{sp}」の色を選択")
        if hex_col:
            self.speaker_colors[sp] = hex_col.upper()
            self._sync_speaker_swatch()
            self.schedule_preview(50)

    def _clear_speaker_color(self):
        sp = self.speaker_sel_var.get().strip()
        if sp and sp in self.speaker_colors:
            del self.speaker_colors[sp]
            self._sync_speaker_swatch()
            self.schedule_preview(50)

    def reset_style_defaults(self):
        self._initializing = True
        try:
            self.position_var.set("bottom")
            self.align_var.set("left")
            self.text_offset_y_var.set(0.0)
            self.pad_x_var.set(4.5)
            self.line_height_var.set(1.45)
            self.overlay_opacity_var.set(76.0)
            self.overlay_fade_var.set(30.0)
            self.overlay_margin_var.set(0.0)
            self.text_outline_var.set("0")
            self.band_color_var.set(adb.rgb_to_hex(adb.DEFAULT_BAND_COLOR))
            self.text_color_var.set(adb.rgb_to_hex(adb.DEFAULT_TEXT_COLOR))
            self.narration_color_var.set(adb.rgb_to_hex(adb.DEFAULT_NARRATION_COLOR))
            self._sync_scale_labels()
            self._sync_color_swatches()
        finally:
            self._initializing = False
        self.refresh_preview()

    # --- Browse & Config handlers ---

    def _clear_var(self, var):
        var.set("")
        self.refresh_preview()

    def _browse_src(self):
        d = filedialog.askdirectory(initialdir=self.src_var.get() or str(BASE_DIR), title="画像フォルダを選択")
        if d:
            self.src_var.set(d)
            self._refresh_image_list()

    def _browse_script(self):
        p = filedialog.askopenfilename(
            initialdir=str(Path(self.script_var.get()).parent) if self.script_var.get() else str(BASE_DIR),
            title="台本CSVを選択",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if p:
            self.script_var.set(p)
            self._refresh_speaker_list()
            self.refresh_preview()

    def _browse_out(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get() or str(BASE_DIR), title="出力フォルダを選択")
        if d:
            self.out_var.set(d)

    def _browse_config(self):
        p = filedialog.askopenfilename(
            initialdir=str(Path(self.config_var.get()).parent) if self.config_var.get() else str(BASE_DIR),
            title="設定JSONを選択",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if p:
            self.config_var.set(p)
            self.load_config_file(p)

    def _browse_font(self, target_var):
        p = filedialog.askopenfilename(
            initialdir="C:/Windows/Fonts" if os.name == "nt" else "/",
            title="フォントファイルを選択",
            filetypes=[("Font files", "*.ttf *.ttc *.otf"), ("All files", "*.*")],
        )
        if p:
            target_var.set(p)
            self.refresh_preview()

    def _on_load_config_btn(self):
        p = self.config_var.get().strip()
        if not p:
            self._browse_config()
            return
        self.load_config_file(p)

    def _collect_config_dict(self):
        data = {
            "mode": self.mode_var.get(),
            "position": self.position_var.get(),
            "band": float(self.band_var.get()),
            "max_lines": int(self.max_lines_var.get()),
            "font_scale": float(self.font_scale_var.get()),
            "uniform_font": bool(self.uniform_font_var.get()),
            "uniform_height": bool(self.uniform_height_var.get()),
            "align": self.align_var.get(),
            "text_offset_y": round(float(self.text_offset_y_var.get()) / 100.0, 4),
            "pad_x": round(float(self.pad_x_var.get()) / 100.0, 4),
            "line_height": round(float(self.line_height_var.get()), 2),
            "format": self.format_var.get(),
            "quality": int(self.quality_var.get()),
            "band_color": self.band_color_var.get(),
            "overlay_opacity": round(float(self.overlay_opacity_var.get()) / 100.0, 4),
            "overlay_fade": round(float(self.overlay_fade_var.get()) / 100.0, 4),
            "overlay_margin": round(float(self.overlay_margin_var.get()) / 100.0, 4),
            "text_outline": int(self.text_outline_var.get()),
            "text_color": self.text_color_var.get(),
            "narration_color": self.narration_color_var.get(),
            "auto_speaker_colors": bool(self.auto_colors_var.get()),
            "speaker_colors": dict(self.speaker_colors),
        }
        if self.font_var.get().strip():
            data["font"] = self.font_var.get().strip()
        if self.font_serif_var.get().strip():
            data["font_serif"] = self.font_serif_var.get().strip()
        if self.font_bold_var.get().strip():
            data["font_bold"] = self.font_bold_var.get().strip()
        return data

    def _on_save_config_btn(self):
        initial = self.config_var.get().strip()
        p = filedialog.asksaveasfilename(
            initialdir=str(Path(initial).parent) if initial else str(BASE_DIR),
            initialfile=Path(initial).name if initial else "config.json",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            title="設定JSONを保存",
        )
        if not p:
            return
        try:
            data = self._collect_config_dict()
            Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.config_var.set(p)
            self.append_log(f"設定を保存しました: {p}")
        except Exception as exc:
            messagebox.showerror("保存エラー", str(exc))

    def load_config_file(self, path, silent=False):
        """Load settings from JSON into UI controls."""
        try:
            data = adb.load_config(path)
        except Exception as exc:
            if not silent:
                messagebox.showerror("設定読込エラー", str(exc))
            return False

        was_init = self._initializing
        self._initializing = True
        try:
            if data.get("mode") in ("extend", "overlay"):
                self.mode_var.set(data["mode"])
            if data.get("position") in ("bottom", "top"):
                self.position_var.set(data["position"])
            if data.get("align") in ("left", "center", "right"):
                self.align_var.set(data["align"])
            if "band" in data:
                self.band_var.set(str(data["band"]))
            if "max_lines" in data:
                self.max_lines_var.set(str(data["max_lines"]))
            if "font_scale" in data:
                self.font_scale_var.set(str(data["font_scale"]))
            if "format" in data:
                self.format_var.set(str(data["format"]).lower())
            if "quality" in data:
                self.quality_var.set(str(data["quality"]))
            if "uniform_font" in data:
                self.uniform_font_var.set(bool(data["uniform_font"]))
            if "uniform_height" in data:
                self.uniform_height_var.set(bool(data["uniform_height"]))
            if "auto_speaker_colors" in data:
                self.auto_colors_var.set(bool(data["auto_speaker_colors"]))

            if "text_offset_y" in data:
                self.text_offset_y_var.set(float(data["text_offset_y"]) * 100.0)
            if "pad_x" in data:
                self.pad_x_var.set(float(data["pad_x"]) * 100.0)
            if "line_height" in data:
                self.line_height_var.set(float(data["line_height"]))
            if "overlay_opacity" in data:
                self.overlay_opacity_var.set(float(data["overlay_opacity"]) * 100.0)
            if "overlay_fade" in data:
                self.overlay_fade_var.set(float(data["overlay_fade"]) * 100.0)
            if "overlay_margin" in data:
                self.overlay_margin_var.set(float(data["overlay_margin"]) * 100.0)
            if "text_outline" in data:
                self.text_outline_var.set(str(int(data["text_outline"])))

            if "band_color" in data:
                self.band_color_var.set(adb.rgb_to_hex(adb.parse_color(data["band_color"], adb.DEFAULT_BAND_COLOR)))
            if "text_color" in data:
                self.text_color_var.set(adb.rgb_to_hex(adb.parse_color(data["text_color"], adb.DEFAULT_TEXT_COLOR)))
            if "narration_color" in data:
                self.narration_color_var.set(
                    adb.rgb_to_hex(adb.parse_color(data["narration_color"], adb.DEFAULT_NARRATION_COLOR))
                )

            if "font" in data and data["font"]:
                self.font_var.set(str(data["font"]))
            if "font_serif" in data and data["font_serif"]:
                self.font_serif_var.set(str(data["font_serif"]))
            if "font_bold" in data and data["font_bold"]:
                self.font_bold_var.set(str(data["font_bold"]))

            raw_sp = data.get("speaker_colors") or {}
            if isinstance(raw_sp, dict):
                self.speaker_colors = {
                    str(sp): adb.rgb_to_hex(adb.parse_color(col, adb.MAIN_SPEAKER_COLOR))
                    for sp, col in raw_sp.items()
                }
            self._sync_scale_labels()
            self._sync_color_swatches()
            self._refresh_speaker_list()
        finally:
            self._initializing = was_init

        if not silent:
            self.append_log(f"設定を読み込みました: {path}")
        if not self._initializing:
            self.refresh_preview()
        return True

    # --- Runtime config & Preview ---

    def build_runtime_cfg(self):
        """Build a runtime cfg dict compatible with `add_dialogue_band`."""
        fonts = adb.resolve_fonts(
            font_opt=self.font_var.get().strip() or None,
            font_serif_opt=self.font_serif_var.get().strip() or None,
            font_bold_opt=self.font_bold_var.get().strip() or None,
        )
        colors = {
            sp: adb.parse_color(col, adb.MAIN_SPEAKER_COLOR) for sp, col in self.speaker_colors.items()
        }
        return {
            "mode": self.mode_var.get(),
            "position": self.position_var.get(),
            "band": float(self.band_var.get()),
            "max_lines": int(self.max_lines_var.get()),
            "font_scale": float(self.font_scale_var.get()),
            "uniform_font": bool(self.uniform_font_var.get()),
            "uniform_font_ratio": None,
            "uniform_height": bool(self.uniform_height_var.get()),
            "align": self.align_var.get(),
            "text_offset_y": float(self.text_offset_y_var.get()) / 100.0,
            "pad_x": float(self.pad_x_var.get()) / 100.0,
            "line_height": float(self.line_height_var.get()),
            "format": self.format_var.get().lower(),
            "quality": int(self.quality_var.get()),
            "band_color": adb.parse_color(self.band_color_var.get(), adb.DEFAULT_BAND_COLOR),
            "text_color": adb.parse_color(self.text_color_var.get(), adb.DEFAULT_TEXT_COLOR),
            "narration_color": adb.parse_color(self.narration_color_var.get(), adb.DEFAULT_NARRATION_COLOR),
            "overlay_opacity": float(self.overlay_opacity_var.get()) / 100.0,
            "overlay_fade": float(self.overlay_fade_var.get()) / 100.0,
            "overlay_margin": float(self.overlay_margin_var.get()) / 100.0,
            "text_outline": int(self.text_outline_var.get()),
            "auto_speaker_colors": bool(self.auto_colors_var.get()),
            "colors": colors,
            **fonts,
        }

    def _apply_auto_speaker_colors(self, cfg, script):
        if cfg["auto_speaker_colors"]:
            for key in sorted(script):
                sp = script[key][0]
                if sp and sp not in cfg["colors"]:
                    cfg["colors"][sp] = adb.PALETTE[len(cfg["colors"]) % len(adb.PALETTE)]

    def _get_uniform_ratio_cached(self, scan_files, script_path, script, cfg):
        mtime = Path(script_path).stat().st_mtime if script_path and Path(script_path).is_file() else None
        cache_key = (
            tuple(str(p) for p in scan_files),
            str(script_path),
            mtime,
            round(cfg["band"], 4),
            cfg["max_lines"],
            round(cfg["font_scale"], 4),
            round(cfg["pad_x"], 4),
            round(cfg["line_height"], 4),
            cfg["mode"],
            cfg["font"],
            cfg["serif"],
            cfg["bold"],
        )
        if self._uniform_cache[0] == cache_key and self._uniform_cache[1] is not None:
            return self._uniform_cache[1]
        res = adb.compute_uniform_font_ratio(scan_files, script, cfg)
        self._uniform_cache = (cache_key, res)
        return res

    def render_preview_pil(self, img_path):
        """Render a single image in memory for previewing and return `(PIL.Image, info_text)`."""
        cfg = self.build_runtime_cfg()
        script = {}
        script_path = self.script_var.get().strip()
        if script_path and Path(script_path).is_file():
            script, _ = adb.load_script(script_path)
            self._apply_auto_speaker_colors(cfg, script)

        bottleneck = None
        if cfg["uniform_font"] and script:
            parent_dir = Path(img_path).parent
            if self.image_files and self.image_files[0].parent == parent_dir:
                scan_files = self.image_files
            else:
                scan_files = [
                    p
                    for p in sorted(parent_dir.iterdir())
                    if p.is_file() and p.suffix.lower() in adb.SUPPORTED_EXTS
                ]
            min_ratio, bottleneck = self._get_uniform_ratio_cached(scan_files, script_path, script, cfg)
            cfg["uniform_font_ratio"] = min_ratio

        key = adb.key_of(Path(img_path).name)
        if key in script and script[key][1]:
            sp, tx = script[key]
            pil_im, meta = adb.render_image(img_path, sp, tx, cfg)
            flags = []
            if cfg["uniform_font"] and bottleneck:
                flags.append(f"統一:{bottleneck['size']}px (基準:{bottleneck['filename']})")
            elif meta["shrunk"]:
                flags.append("自動縮小")
            if meta["overflow"]:
                flags.append("※文字溢れ")
            flag_str = f" [{' / '.join(flags)}]" if flags else ""
            info = (
                f"{pil_im.width}x{pil_im.height} | キー:{key} | "
                f"話者:{sp or '(地の文)'} | 本文:{meta['size']}px{flag_str}"
            )
            return pil_im, info

        if cfg["uniform_height"] and cfg["mode"] == "extend":
            pil_im = adb.render_blank_band(img_path, cfg)
            note = "セリフなし (空帯あり)"
        else:
            pil_im = adb._load_rgb_image(img_path, cfg["band_color"])
            note = "セリフなし (そのまま)"
        return pil_im, f"{pil_im.width}x{pil_im.height} | キー:{key} | {note}"

    def _sync_image_list_only(self):
        src_str = self.src_var.get().strip()
        if not src_str or not Path(src_str).is_dir():
            self.image_files = []
            self.preview_combo["values"] = []
            self.preview_sel_var.set("")
            return
        files = [
            p
            for p in sorted(Path(src_str).iterdir())
            if p.is_file() and p.suffix.lower() in adb.SUPPORTED_EXTS
        ]
        self.image_files = files
        names = [p.name for p in files]
        self.preview_combo["values"] = names
        cur = self.preview_sel_var.get()
        if names:
            if cur not in names:
                self.preview_sel_var.set(names[0])
        else:
            self.preview_sel_var.set("")

    def _refresh_image_list(self):
        self._sync_image_list_only()
        self._refresh_speaker_list()
        self.refresh_preview()

    def _step_preview(self, delta):
        if not self.image_files:
            return
        names = [p.name for p in self.image_files]
        cur = self.preview_sel_var.get()
        idx = names.index(cur) if cur in names else 0
        nxt = (idx + delta) % len(names)
        self.preview_sel_var.set(names[nxt])
        self.refresh_preview()

    def schedule_preview(self, delay_ms=100):
        """Debounced preview refresh for sliders, spinboxes, and toggles."""
        if self._initializing:
            return
        if self._preview_job is not None:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(delay_ms, self.refresh_preview)

    def refresh_preview(self):
        """Re-render the currently selected preview image."""
        self._preview_job = None
        self._sync_image_list_only()
        if not self.image_files:
            self._preview_pil = None
            self._preview_photo = None
            self.preview_label.configure(image="", text="画像フォルダを選択するとプレビューが表示されます")
            self.preview_info_var.set("画像なし")
            return

        sel = self.preview_sel_var.get()
        target = next((p for p in self.image_files if p.name == sel), self.image_files[0])
        try:
            pil_im, info = self.render_preview_pil(target)
            self._preview_pil = pil_im
            self.preview_info_var.set(info)
            self._display_preview_pil()
        except Exception as exc:
            self._preview_pil = None
            self._preview_photo = None
            self.preview_label.configure(image="", text=f"プレビューエラー:\n{exc}")
            self.preview_info_var.set("エラー")

    def _on_preview_resize(self, _event):
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(80, self._display_preview_pil)

    def _display_preview_pil(self):
        self._resize_job = None
        if self._preview_pil is None:
            return
        cw = max(120, self.preview_container.winfo_width() - 12)
        ch = max(120, self.preview_container.winfo_height() - 12)
        im = self._preview_pil
        scale = min(cw / im.width, ch / im.height, 1.0)
        nw = max(1, int(round(im.width * scale)))
        nh = max(1, int(round(im.height * scale)))
        resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(resized)
        self._preview_photo = photo
        self.preview_label.configure(image=photo, text="")

    # --- Logging & Worker execution ---

    def append_log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _set_running(self, running):
        self._running = running
        state = "disabled" if running else "normal"
        for b in self._action_buttons:
            b.configure(state=state)

    def _start_worker(self, dry_run):
        if self._running:
            return

        src_str = self.src_var.get().strip()
        script_str = self.script_var.get().strip()
        out_str = self.out_var.get().strip()

        if not src_str or not Path(src_str).is_dir():
            messagebox.showerror("入力エラー", "有効な「画像フォルダ」を選択してください。")
            return
        if not script_str or not Path(script_str).is_file():
            messagebox.showerror("入力エラー", "有効な「台本CSV」を選択してください。")
            return
        if not dry_run and not out_str:
            messagebox.showerror("入力エラー", "「出力フォルダ」を指定してください。")
            return

        try:
            cfg = self.build_runtime_cfg()
        except Exception as exc:
            messagebox.showerror("設定エラー", str(exc))
            return

        only_raw = self.only_var.get().strip()
        only_keys = {k.strip() for k in only_raw.split(",") if k.strip()} if only_raw else None

        self._save_state()
        self._clear_log()
        self.progress_var.set(0.0)
        self.status_var.set("チェック中..." if dry_run else "生成中...")
        self._set_running(True)

        t = threading.Thread(
            target=self._run_batch_worker,
            args=(Path(src_str), Path(script_str), Path(out_str) if out_str else Path(), cfg, only_keys, dry_run),
            daemon=True,
        )
        t.start()

    def _ui_log(self, msg):
        self.root.after(0, self.append_log, msg)

    def _ui_progress(self, pct, status_text):
        self.root.after(0, self.progress_var.set, pct)
        self.root.after(0, self.status_var.set, status_text)

    def _run_batch_worker(self, src, script_path, out, cfg, only_keys, dry_run):
        try:
            script, csv_warnings = adb.load_script(script_path)
            for msg in csv_warnings:
                self._ui_log(f"warning: {msg}")
            self._apply_auto_speaker_colors(cfg, script)

            if not dry_run:
                out.mkdir(parents=True, exist_ok=True)

            files = [
                p
                for p in sorted(src.iterdir())
                if p.is_file() and p.suffix.lower() in adb.SUPPORTED_EXTS
            ]
            if only_keys is not None:
                files = [p for p in files if adb.key_of(p.name) in only_keys]

            if cfg["uniform_font"]:
                min_ratio, bottleneck = adb.compute_uniform_font_ratio(files, script, cfg)
                cfg["uniform_font_ratio"] = min_ratio
                if bottleneck:
                    self._ui_log(
                        f"info: uniform-font active: {bottleneck['size']}px (bottleneck: {bottleneck['filename']})"
                    )

            total = max(1, len(files))
            n_text = 0
            n_copy = 0
            used = set()
            shrunk_keys = []
            overflow_keys = []

            for idx, p in enumerate(files, 1):
                key = adb.key_of(p.name)
                if key in script:
                    used.add(key)
                    sp, tx = script[key]
                    if tx:
                        if dry_run:
                            meta = adb.check_layout_only(p, sp, tx, cfg)
                        else:
                            meta, _ = adb.process(p, sp, tx, out / p.name, cfg)
                        if meta["shrunk"]:
                            shrunk_keys.append((key, meta["size"]))
                        if meta["overflow"]:
                            overflow_keys.append(key)
                            self._ui_log(
                                f"WARNING [OVERFLOW]: key '{key}' ({p.name}) truncated at {meta['size']}px"
                            )
                        n_text += 1
                        self._ui_progress(idx / total * 100.0, f"処理中 ({idx}/{len(files)}): {p.name}")
                        continue
                else:
                    self._ui_log(f"warning: no script entry for image '{p.name}' (key '{key}')")

                if not dry_run:
                    if cfg["uniform_height"] and cfg["mode"] == "extend":
                        adb.process_blank_band(p, out / p.name, cfg)
                    elif cfg["format"] != "keep":
                        im = adb._load_rgb_image(p, cfg["band_color"])
                        adb.save_image(im, out / p.name, fmt=cfg["format"], quality=cfg["quality"])
                    else:
                        shutil.copy2(p, out / p.name)
                n_copy += 1
                self._ui_progress(idx / total * 100.0, f"処理中 ({idx}/{len(files)}): {p.name}")

            for key in script:
                if only_keys is not None and key not in only_keys:
                    continue
                if key not in used:
                    self._ui_log(f"warning: no image for script key {key}")

            if shrunk_keys and not cfg["uniform_font"]:
                details = ", ".join(f"{k}({sz}px)" for k, sz in shrunk_keys)
                self._ui_log(f"info: auto-shrunk text on {len(shrunk_keys)} image(s): {details}")

            prefix = "dry-run" if dry_run else "done"
            summary = f"{prefix}: with-dialogue={n_text} copied={n_copy} mode={cfg['mode']}"
            self._ui_log(summary)
            done_status = f"完了（セリフ合成:{n_text} / コピー:{n_copy} / 溢れ:{len(overflow_keys)}）"
            self._ui_progress(100.0, done_status)
        except Exception as exc:
            self._ui_log(f"ERROR: {exc}")
            self.root.after(0, self.status_var.set, f"エラー: {exc}")
            self.root.after(0, messagebox.showerror, "実行エラー", str(exc))
        finally:
            self.root.after(0, self._set_running, False)

    def open_output_dir(self):
        out_str = self.out_var.get().strip()
        if not out_str:
            messagebox.showinfo("お知らせ", "出力フォルダが指定されていません。")
            return
        p = Path(out_str)
        if not p.exists():
            messagebox.showinfo("お知らせ", f"出力フォルダがまだ存在しません:\n{p}")
            return
        if os.name == "nt":
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])

    # --- State persistence ---

    def _load_initial_state(self):
        if STATE_PATH.is_file():
            try:
                st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                self.src_var.set(st.get("src", ""))
                self.script_var.set(st.get("script", ""))
                self.out_var.set(st.get("out", ""))
                self.config_var.set(st.get("config", ""))
                if st.get("config") and Path(st["config"]).is_file():
                    self.load_config_file(st["config"], silent=True)
                for key, var in (
                    ("mode", self.mode_var),
                    ("position", self.position_var),
                    ("align", self.align_var),
                    ("band", self.band_var),
                    ("max_lines", self.max_lines_var),
                    ("font_scale", self.font_scale_var),
                    ("format", self.format_var),
                    ("quality", self.quality_var),
                    ("text_outline", self.text_outline_var),
                    ("band_color", self.band_color_var),
                    ("text_color", self.text_color_var),
                    ("narration_color", self.narration_color_var),
                    ("only", self.only_var),
                    ("font", self.font_var),
                    ("font_serif", self.font_serif_var),
                    ("font_bold", self.font_bold_var),
                ):
                    if key in st and st[key] is not None:
                        var.set(str(st[key]))
                for key, var in (
                    ("text_offset_y_pct", self.text_offset_y_var),
                    ("pad_x_pct", self.pad_x_var),
                    ("line_height", self.line_height_var),
                    ("overlay_opacity_pct", self.overlay_opacity_var),
                    ("overlay_fade_pct", self.overlay_fade_var),
                    ("overlay_margin_pct", self.overlay_margin_var),
                ):
                    if key in st and st[key] is not None:
                        var.set(float(st[key]))
                if "uniform_font" in st:
                    self.uniform_font_var.set(bool(st["uniform_font"]))
                if "auto_colors" in st:
                    self.auto_colors_var.set(bool(st["auto_colors"]))
                if "uniform_height" in st:
                    self.uniform_height_var.set(bool(st["uniform_height"]))
                if isinstance(st.get("speaker_colors"), dict):
                    self.speaker_colors = dict(st["speaker_colors"])
                self._sync_scale_labels()
                self._sync_color_swatches()
                self._sync_image_list_only()
                self._refresh_speaker_list()
                return
            except Exception:
                pass

        sample_in = BASE_DIR / "sample_input"
        sample_csv = BASE_DIR / "sample_script.csv"
        sample_out = BASE_DIR / "sample_output_extend"
        sample_cfg = BASE_DIR / "sample_config.json"

        if sample_in.is_dir():
            self.src_var.set(str(sample_in))
        if sample_csv.is_file():
            self.script_var.set(str(sample_csv))
        self.out_var.set(str(sample_out))
        if sample_cfg.is_file():
            self.config_var.set(str(sample_cfg))
            self.load_config_file(str(sample_cfg), silent=True)
        self._sync_scale_labels()
        self._sync_color_swatches()
        self._sync_image_list_only()
        self._refresh_speaker_list()

    def _save_state(self):
        try:
            st = {
                "src": self.src_var.get(),
                "script": self.script_var.get(),
                "out": self.out_var.get(),
                "config": self.config_var.get(),
                "mode": self.mode_var.get(),
                "position": self.position_var.get(),
                "align": self.align_var.get(),
                "band": self.band_var.get(),
                "max_lines": self.max_lines_var.get(),
                "font_scale": self.font_scale_var.get(),
                "format": self.format_var.get(),
                "quality": self.quality_var.get(),
                "uniform_font": self.uniform_font_var.get(),
                "auto_colors": self.auto_colors_var.get(),
                "uniform_height": self.uniform_height_var.get(),
                "text_offset_y_pct": self.text_offset_y_var.get(),
                "pad_x_pct": self.pad_x_var.get(),
                "line_height": self.line_height_var.get(),
                "overlay_opacity_pct": self.overlay_opacity_var.get(),
                "overlay_fade_pct": self.overlay_fade_var.get(),
                "overlay_margin_pct": self.overlay_margin_var.get(),
                "text_outline": self.text_outline_var.get(),
                "band_color": self.band_color_var.get(),
                "text_color": self.text_color_var.get(),
                "narration_color": self.narration_color_var.get(),
                "speaker_colors": dict(self.speaker_colors),
                "only": self.only_var.get(),
                "font": self.font_var.get(),
                "font_serif": self.font_serif_var.get(),
                "font_bold": self.font_bold_var.get(),
            }
            STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _on_close(self):
        self._save_state()
        self.root.destroy()


def _show_startup_error(msg):
    """Display startup error visibly even when launched via pythonw.exe without a console."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "帯テキスト一括合成ツール - 起動エラー", 0x10)
        return
    except Exception:
        pass
    try:
        err_root = tk.Tk()
        err_root.withdraw()
        messagebox.showerror("起動エラー", msg)
        err_root.destroy()
    except Exception:
        sys.stderr.write(msg + "\n")


def main():
    try:
        root = tk.Tk()
        DialogueBandApp(root)
        root.mainloop()
    except Exception:
        _show_startup_error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
