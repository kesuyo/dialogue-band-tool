import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import add_dialogue_band as adb


class TestKinsokuAndWrapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fonts = adb.resolve_fonts()
        cls.dummy = Image.new("RGB", (1, 1))
        cls.draw = ImageDraw.Draw(cls.dummy)

    def test_kinsoku_punctuation_and_brackets(self):
        # Closing/punctuation cannot start next line
        for ch in ["、", "。", "？", "！", "」", "）", "ー", "っ", "ッ", "ャ", "ァ", "～", "—"]:
            text = f"あ{ch}い"
            self.assertFalse(adb.can_break(text, 1), f"Should not break before {ch!r}")
        # Opening brackets cannot end previous line
        for ch in ["「", "『", "（", "【", "("]:
            text = f"{ch}あ"
            self.assertFalse(adb.can_break(text, 1), f"Should not break after {ch!r}")

    def test_kinsoku_inseparable_pairs_and_alnum(self):
        self.assertFalse(adb.can_break("……ねえ", 1))
        self.assertTrue(adb.can_break("……ねえ", 2))
        self.assertFalse(adb.can_break("——そう", 1))
        self.assertFalse(adb.can_break("本当！？嘘", 3))  # between ！ and ？
        self.assertFalse(adb.can_break("hello world", 2))
        self.assertTrue(adb.can_break("hello world", 6))  # after space
        self.assertFalse(adb.can_break("v1.0です", 2))  # 1 | .
        self.assertFalse(adb.can_break("v1.0です", 3))  # . | 0
        self.assertFalse(adb.can_break("100%だ", 3))  # 0 | %

    def test_sample_dialogues_wrap_naturally(self):
        # Sample dimensions: 832px width -> pad=37 -> max_w=758, band_h=200
        max_w = 832 - int(round(832 * 0.045)) * 2
        max_h = 100
        samples = [
            ("……ねえ、今日はもう少しだけ、そばにいて？", ["もう/少し", "少し/だけ", "そば/に"]),
            ("ずっと我慢してたの。あなたに会えない夜は、胸が苦しくて、眠れなかった……", ["夜/は", "苦し/くて", "我慢/して"]),
            ("「分かった。今日は帰らないで、朝までずっとそばにいるよ。約束する」", ["ずっ/と", "約束/する", "朝/まで"]),
        ]
        for text, forbidden_splits in samples:
            font, lines, _, meta = adb.fit_text(
                self.draw, text, max_w, max_h, self.fonts["font"], max_lines=2, start_size=44, min_size=20, step=2
            )
            self.assertFalse(meta["overflow"], f"Unexpected overflow for: {text}")
            self.assertLessEqual(len(lines), 2)
            for ln in lines:
                self.assertLessEqual(self.draw.textlength(ln, font=font), max_w)
            if len(lines) == 2:
                joined_marker = lines[0][-2:] + "/" + lines[1][:2]
                for bad in forbidden_splits:
                    a, b = bad.split("/")
                    self.assertFalse(
                        lines[0].endswith(a) and lines[1].startswith(b),
                        f"Awkward split {bad!r} in lines={lines} (marker={joined_marker})",
                    )

    def test_manual_newline_preserved(self):
        font_path = self.fonts["font"]
        _, lines, _, meta = adb.fit_text(
            self.draw,
            "今日はここまで。\nまた明日ね",
            max_w=758,
            max_h=120,
            font_path=font_path,
            max_lines=2,
            start_size=44,
            min_size=20,
        )
        self.assertFalse(meta["overflow"])
        self.assertEqual(lines, ["今日はここまで。", "また明日ね"])

    def test_rebalance_respects_max_w_on_both_lines(self):
        font = ImageFont.truetype(self.fonts["font"], 36)
        max_w = 420
        lines = ["あいうえおかきくけこ", "さ"]
        res = adb.rebalance(self.draw, lines, font, max_w)
        self.assertEqual(len(res), 2)
        for ln in res:
            self.assertLessEqual(self.draw.textlength(ln, font=font), max_w)

    def test_single_wide_char_no_infinite_loop(self):
        font = ImageFont.truetype(self.fonts["font"], 40)
        lines = adb.wrap_text(self.draw, "あいう", font, max_w=5)
        self.assertEqual(lines, ["あ", "い", "う"])


class TestCsvAndKeysAndFonts(unittest.TestCase):
    def test_key_of_earliest_separator(self):
        self.assertEqual(adb.key_of("001_sample.png"), "001")
        self.assertEqual(adb.key_of("001-a_scene.png"), "001")
        self.assertEqual(adb.key_of("002 scene_extra.jpg"), "002")
        self.assertEqual(adb.key_of("003.webp"), "003")

    def test_load_script_csv_features(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "script.csv"
            content = (
                "\ufeff"
                "id,speaker,line\n"
                "# comment line\n"
                "\n"
                '001,彼女,"……ねえ、今日は,もう少しだけ"\n'
                '002,,"一行目\n二行目"\n'
                "003,彼,一\\n二\n"
                "004,壊れ\n"
                "001,彼女,上書き\n"
            )
            p.write_text(content, encoding="utf-8")
            script, warnings = adb.load_script(p)

        self.assertEqual(script["001"], ("彼女", "上書き"))
        self.assertEqual(script["002"], ("", "一行目\n二行目"))
        self.assertEqual(script["003"], ("彼", "一\n二"))
        self.assertTrue(any("too few columns" in w for w in warnings))
        self.assertTrue(any("duplicate script key '001'" in w for w in warnings))

    def test_font_pick_and_resolve_fallback(self):
        existing = adb.resolve_fonts()["font"]
        self.assertEqual(adb.pick(["/nonexistent/font.ttf"], fallback=existing), existing)
        with self.assertRaises(FileNotFoundError):
            adb.pick(["/nonexistent/font.ttf"], override="/nonexistent/override.ttf")

        resolved = adb.resolve_fonts(
            font_opt=existing,
            font_candidates=["/nonexistent/a.ttf"],
            serif_candidates=["/nonexistent/b.ttf"],
            bold_candidates=["/nonexistent/c.ttf"],
        )
        self.assertEqual(resolved["font"], existing)
        self.assertEqual(resolved["serif"], existing)
        self.assertEqual(resolved["bold"], existing)


class TestEndToEndRendering(unittest.TestCase):
    def _make_sample_workspace(self, td, size=(832, 1216), mode="RGB"):
        root = Path(td)
        src = root / "src"
        out = root / "out"
        src.mkdir()
        color = (120, 160, 200, 180) if mode == "RGBA" else (120, 160, 200)
        Image.new(mode, size, color).save(src / "001_scene.png")
        Image.new(mode, size, color).save(src / "002_blank.png")
        csv_path = root / "script.csv"
        csv_path.write_text("001,彼女,……ねえ、今日はもう少しだけ、そばにいて？\n", encoding="utf-8")
        return src, csv_path, out

    def test_extend_overlay_and_uniform_height(self):
        with tempfile.TemporaryDirectory() as td:
            src, csv_path, out_ext = self._make_sample_workspace(td, mode="RGBA")
            rc = adb.main([str(src), str(csv_path), str(out_ext), "--mode", "extend", "--uniform-height"])
            self.assertEqual(rc, 0)
            with Image.open(out_ext / "001_scene.png") as im1, Image.open(out_ext / "002_blank.png") as im2:
                self.assertEqual(im1.size, im2.size)
                self.assertGreater(im1.size[1], 1216)

            out_ov = Path(td) / "out_ov"
            rc = adb.main([str(src), str(csv_path), str(out_ov), "--mode", "overlay", "--speaker-colors"])
            self.assertEqual(rc, 0)
            with Image.open(out_ov / "001_scene.png") as im1:
                self.assertEqual(im1.size, (832, 1216))

    def test_resolution_scaling_and_jpeg_config(self):
        with tempfile.TemporaryDirectory() as td:
            src, csv_path, out = self._make_sample_workspace(td, size=(400, 600))
            Image.new("RGB", (2000, 3000), (90, 90, 140)).save(src / "003_big.png")
            csv_path.write_text(
                "001,彼女,短いテスト\n003,,ナレーションのテスト\n",
                encoding="utf-8",
            )
            cfg_path = Path(td) / "cfg.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "mode": "extend",
                        "format": "jpg",
                        "quality": 90,
                        "speaker_colors": {"彼女": "#FF9EC7"},
                    }
                ),
                encoding="utf-8",
            )
            rc = adb.main([str(src), str(csv_path), str(out), "--config", str(cfg_path)])
            self.assertEqual(rc, 0)
            self.assertTrue((out / "001_scene.jpg").exists())
            self.assertTrue((out / "002_blank.jpg").exists())
            self.assertTrue((out / "003_big.jpg").exists())
            with Image.open(out / "001_scene.jpg") as im_s, Image.open(out / "003_big.jpg") as im_b:
                self.assertEqual(im_s.size, (400, 696))
                self.assertEqual(im_b.size, (2000, 3480))

    def test_dry_run_only_and_strict_overflow(self):
        with tempfile.TemporaryDirectory() as td:
            src, csv_path, out = self._make_sample_workspace(td, size=(500, 700))
            long_line = "あ" * 120
            csv_path.write_text(
                f"001,彼女,{long_line}\n999,彼,画像なし\n",
                encoding="utf-8",
            )
            # dry-run creates nothing
            rc_dry = adb.main([str(src), str(csv_path), str(out), "--dry-run", "--only", "001"])
            self.assertEqual(rc_dry, 0)
            self.assertFalse(out.exists())

            # strict exits non-zero on overflow / unmatched script key
            rc_strict = adb.main([str(src), str(csv_path), str(out), "--strict"])
            self.assertNotEqual(rc_strict, 0)

    def test_render_image_and_blank_band(self):
        sample_img = ROOT / "sample_input" / "001_sample.png"
        cfg = {
            "mode": "extend",
            "band": 0.24,
            "max_lines": 2,
            "font_scale": 1.0,
            "uniform_height": False,
            "format": "keep",
            "quality": 92,
            "band_color": adb.DEFAULT_BAND_COLOR,
            "text_color": adb.DEFAULT_TEXT_COLOR,
            "narration_color": adb.DEFAULT_NARRATION_COLOR,
            "overlay_opacity": 0.76,
            "auto_speaker_colors": False,
            "colors": {"彼女": (255, 158, 199)},
            **adb.resolve_fonts(),
        }
        rendered, meta = adb.render_image(sample_img, "彼女", "テストセリフ", cfg)
        self.assertFalse(meta["overflow"])
        self.assertEqual(rendered.size, (832, 1216 + int(round(832 * 0.24))))

        blank = adb.render_blank_band(sample_img, cfg)
        self.assertEqual(blank.size, rendered.size)

    def test_uniform_font_two_pass_and_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            out = root / "out"
            src.mkdir()
            p1 = src / "001_short.png"
            p2 = src / "002_long.png"
            Image.new("RGB", (800, 1000), (60, 80, 120)).save(p1)
            Image.new("RGB", (800, 1000), (60, 80, 120)).save(p2)
            csv_path = root / "script.csv"
            short_tx = "短いセリフ"
            long_tx = "これは文字サイズ統一機能を検証するための少し長めのセリフです。全ページ同じ大きさになります。"
            csv_path.write_text(f"001,彼女,{short_tx}\n002,彼女,{long_tx}\n", encoding="utf-8")

            script, _ = adb.load_script(csv_path)
            cfg = {
                "mode": "extend",
                "position": "bottom",
                "band": 0.24,
                "max_lines": 2,
                "font_scale": 1.0,
                "uniform_font": True,
                "uniform_font_ratio": None,
                "uniform_height": False,
                "align": "left",
                "text_offset_y": 0.0,
                "pad_x": 0.045,
                "line_height": 1.45,
                "format": "keep",
                "quality": 92,
                "band_color": adb.DEFAULT_BAND_COLOR,
                "text_color": adb.DEFAULT_TEXT_COLOR,
                "narration_color": adb.DEFAULT_NARRATION_COLOR,
                "overlay_opacity": 0.76,
                "overlay_fade": 0.30,
                "overlay_margin": 0.0,
                "text_outline": 0,
                "auto_speaker_colors": False,
                "colors": {},
                **adb.resolve_fonts(),
            }
            min_ratio, bottleneck = adb.compute_uniform_font_ratio([p1, p2], script, cfg)
            self.assertIsNotNone(min_ratio)
            self.assertEqual(bottleneck["filename"], "002_long.png")
            cfg["uniform_font_ratio"] = min_ratio

            _, meta1 = adb.render_image(p1, "彼女", short_tx, cfg)
            _, meta2 = adb.render_image(p2, "彼女", long_tx, cfg)
            self.assertEqual(meta1["size"], meta2["size"])

            rc = adb.main([str(src), str(csv_path), str(out), "--uniform-font"])
            self.assertEqual(rc, 0)
            self.assertTrue((out / "001_short.png").exists())
            self.assertTrue((out / "002_long.png").exists())

    def test_position_align_overlay_and_cli_options(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            out = root / "out"
            src.mkdir()
            p1 = src / "001_test.png"
            # Distinct top/bottom halves so top vs bottom placement is verifiable
            im = Image.new("RGB", (800, 1000), (200, 210, 220))
            for y in range(500, 1000):
                for x in range(800):
                    im.putpixel((x, y), (40, 60, 90))
            im.save(p1)
            csv_path = root / "script.csv"
            csv_path.write_text("001,彼女,上配置と中央揃えのテスト\n", encoding="utf-8")

            # Top extend band: top pixels match band_color, bottom keeps artwork
            cfg = {
                "mode": "extend",
                "position": "top",
                "band": 0.24,
                "max_lines": 2,
                "font_scale": 1.0,
                "uniform_font_ratio": None,
                "text_offset_y": -0.20,
                "pad_x": 0.12,
                "line_height": 1.70,
                "format": "keep",
                "quality": 92,
                "band_color": (240, 240, 244),
                "text_color": (20, 20, 24),
                "narration_color": (30, 30, 40),
                "overlay_opacity": 0.0,
                "overlay_fade": 0.40,
                "overlay_margin": 0.05,
                "text_outline": 2,
                "colors": {"彼女": (210, 40, 110)},
                **adb.resolve_fonts(),
            }
            top_ext, _ = adb.render_image(p1, "彼女", "上配置のテスト", cfg)
            self.assertEqual(top_ext.size, (800, 1192))
            self.assertEqual(top_ext.getpixel((5, 5)), (240, 240, 244))
            self.assertEqual(top_ext.getpixel((5, 1190)), (40, 60, 90))

            blank_top = adb.render_blank_band(p1, cfg)
            self.assertEqual(blank_top.size, (800, 1192))
            self.assertEqual(blank_top.getpixel((5, 5)), (240, 240, 244))

            # Overlay with 0.0 opacity leaves untouched pixels identical
            cfg["mode"] = "overlay"
            ov_zero, _ = adb.render_image(p1, "", "ナレーション", cfg)
            self.assertEqual(ov_zero.size, (800, 1000))
            self.assertEqual(ov_zero.getpixel((10, 950)), (40, 60, 90))

            # CLI flags end-to-end
            rc = adb.main(
                [
                    str(src),
                    str(csv_path),
                    str(out),
                    "--mode",
                    "overlay",
                    "--position",
                    "top",
                    "--text-offset-y",
                    "0.15",
                    "--pad-x",
                    "0.08",
                    "--line-height",
                    "1.6",
                    "--overlay-opacity",
                    "0.5",
                    "--overlay-fade",
                    "0.4",
                    "--overlay-margin",
                    "0.04",
                    "--text-outline",
                    "2",
                    "--band-color",
                    "#10141C",
                    "--text-color",
                    "#FFFFFF",
                    "--narration-color",
                    "#DDE6FF",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue((out / "001_test.png").exists())

    def test_speaker_styles_match_body_size_and_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            out = root / "out"
            src.mkdir()
            p1 = src / "001_sample.png"
            Image.new("RGB", (832, 1216), (90, 110, 140)).save(p1)
            csv_path = root / "script.csv"
            csv_path.write_text("001,彼女,彼も{{彼女}}も一緒だよ\n", encoding="utf-8")

            fonts = adb.resolve_fonts()
            dummy = Image.new("RGB", (1, 1))
            draw = ImageDraw.Draw(dummy)
            base_cfg = {
                "mode": "overlay",
                "position": "bottom",
                "band": 0.20,
                "max_lines": 2,
                "font_scale": 0.65,
                "speaker_style": "plate",
                "speaker_gap": 0.50,
                "speaker_names": {"彼女": "さくら"},
                "replace_speaker_in_body": True,
                "uniform_font_ratio": None,
                "pad_x": 0.045,
                "line_height": 1.45,
                "band_color": adb.DEFAULT_BAND_COLOR,
                "text_color": adb.DEFAULT_TEXT_COLOR,
                "narration_color": adb.DEFAULT_NARRATION_COLOR,
                "overlay_opacity": 0.35,
                "overlay_fade": 0.30,
                "overlay_margin": 0.0,
                "text_outline": 2,
                "text_offset_y": 0.0,
                "colors": {"彼女": (255, 158, 199)},
                **fonts,
            }
            # Speaker size always matches body font size across font_scale & shrinkage
            l_small = adb._compute_layout(832, 1216, "彼女", "短いセリフ", base_cfg, draw)
            self.assertEqual(l_small["name_size"], l_small["fit_meta"]["size"])
            self.assertEqual(l_small["eff_speaker"], "さくら")

            cfg_big = dict(base_cfg, font_scale=1.20)
            l_big = adb._compute_layout(832, 1216, "彼女", "短いセリフ", cfg_big, draw)
            self.assertEqual(l_big["name_size"], l_big["fit_meta"]["size"])
            self.assertGreater(l_big["name_size"], l_small["name_size"])

            # Alias safety: renaming '彼' alone must not corrupt '彼女' or compound words in body text
            alias_cfg = {"speaker_names": {"彼": "タロウ"}, "replace_speaker_in_body": True}
            sp_out, tx_out = adb.apply_speaker_aliases(
                "彼", "彼女と彼と彼らと彼等と彼氏と彼方と彼岸と{{彼}}", alias_cfg
            )
            self.assertEqual(sp_out, "タロウ")
            self.assertEqual(tx_out, "彼女とタロウと彼らと彼等と彼氏と彼方と彼岸とタロウ")

            for mode in ("extend", "overlay"):
                for style in ("plate", "bar", "bracket", "plain"):
                    c = dict(base_cfg, mode=mode, speaker_style=style, speaker_gap=0.4)
                    im, meta = adb.render_image(p1, "彼女", "テストセリフ", c)
                    self.assertFalse(meta["overflow"])
                    self.assertEqual(im.width, 832)

            rc = adb.main(
                [
                    str(src),
                    str(csv_path),
                    str(out),
                    "--mode",
                    "overlay",
                    "--speaker-style",
                    "bar",
                    "--speaker-gap",
                    "0.45",
                    "--speaker-name",
                    "彼女=さくら",
                    "--replace-speaker-in-body",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue((out / "001_sample.png").exists())


class TestGuiApp(unittest.TestCase):
    def test_gui_app_preview_and_config(self):
        import tkinter as tk
        import gui

        root = tk.Tk()
        root.withdraw()
        try:
            app = gui.DialogueBandApp(root)
            sample_cfg = ROOT / "sample_config.json"
            self.assertTrue(app.load_config_file(str(sample_cfg), silent=True))

            sample_img = ROOT / "sample_input" / "001_sample.png"
            app.mode_var.set("extend")
            im_ext, info_ext = app.render_preview_pil(sample_img)
            self.assertGreater(im_ext.height, 1216)
            expected_sp = app.speaker_names.get("彼女") or "彼女"
            self.assertIn(expected_sp, info_ext)

            app.mode_var.set("overlay")
            im_ov, info_ov = app.render_preview_pil(sample_img)
            self.assertEqual(im_ov.size, (832, 1216))
            self.assertIn("832x1216", info_ov)

            # v1.2-v1.5 controls, speaker rename, & config roundtrip
            app.uniform_font_var.set(True)
            app.speaker_style_var.set("bracket")
            app.speaker_gap_var.set(0.65)
            app.speaker_names = {"彼女": "さくら"}
            app.replace_in_body_var.set(True)
            app.position_var.set("top")
            app.overlay_opacity_var.set(50.0)
            app.overlay_fade_var.set(45.0)
            app.overlay_margin_var.set(3.0)
            app.text_offset_y_var.set(-15.0)
            app.pad_x_var.set(8.0)
            app.line_height_var.set(1.6)
            app.text_outline_var.set("2")

            im_v15, info_v15 = app.render_preview_pil(sample_img)
            self.assertEqual(im_v15.size, (832, 1216))
            self.assertIn("統一:", info_v15)
            self.assertIn("さくら", info_v15)

            with tempfile.TemporaryDirectory() as td:
                cfg_out = Path(td) / "saved.json"
                saved_dict = app._collect_config_dict()
                cfg_out.write_text(json.dumps(saved_dict, ensure_ascii=False, indent=2), encoding="utf-8")

                app.reset_style_defaults()
                self.assertEqual(app.position_var.get(), "bottom")
                self.assertEqual(app.speaker_style_var.get(), "plate")
                self.assertTrue(app.load_config_file(str(cfg_out), silent=True))
                self.assertTrue(app.uniform_font_var.get())
                self.assertEqual(app.speaker_style_var.get(), "bracket")
                self.assertEqual(app.speaker_names, {"彼女": "さくら"})
                self.assertTrue(app.replace_in_body_var.get())
                self.assertAlmostEqual(app.speaker_gap_var.get(), 0.65, places=2)
                self.assertEqual(app.position_var.get(), "top")
                self.assertAlmostEqual(app.overlay_opacity_var.get(), 50.0, places=1)
                self.assertEqual(app.text_outline_var.get(), "2")

            app.title_var.set("GUIテスト作品")
            app.sfx_off_var.set("")
            app.default_sfx_var.set(True)
            self.assertEqual(app.title_var.get(), "GUIテスト作品")
            self.assertEqual(app.sfx_off_var.get(), "")
            self.assertTrue(app.default_sfx_var.get())
            with tempfile.TemporaryDirectory() as td_html:
                import export_html_viewer

                html_res = export_html_viewer.export_html_viewer(
                    ROOT / "sample_input",
                    ROOT / "sample_script.csv",
                    Path(td_html),
                    app.build_runtime_cfg(),
                    title=app.title_var.get(),
                    default_sfx=app.default_sfx_var.get(),
                )
                self.assertEqual(html_res["steps"], 3)
                self.assertFalse(html_res["has_alt_images"])
                self.assertTrue((Path(td_html) / "index.html").is_file())
        finally:
            root.destroy()

    def test_gui_refresh_speaker_list_multiline_and_3speaker_template(self):
        import tkinter as tk
        import gui

        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tkinter unavailable: {exc}")
        root.withdraw()
        try:
            app = gui.DialogueBandApp(root)
            with tempfile.TemporaryDirectory() as td:
                csv_p = Path(td) / "multi.csv"
                csv_p.write_text(
                    "001,彼女A,セリフ1\n"
                    "001,彼女B,セリフ2\n"
                    "001,彼,セリフ3\n",
                    encoding="utf-8",
                )
                app.speaker_colors.clear()
                app.speaker_names.clear()
                app.script_var.set(str(csv_p))
                app._refresh_speaker_list()
                self.assertEqual(tuple(app.speaker_combo["values"]), ("彼女A", "彼女B", "彼"))

            tpl_cfg = ROOT / "sample_config_3speakers.json"
            self.assertTrue(app.load_config_file(str(tpl_cfg), silent=True))
            self.assertEqual(set(app.speaker_colors.keys()), {"彼女A", "彼女B", "彼"})
            self.assertEqual(set(app.speaker_names.keys()), {"彼女A", "彼女B", "彼"})
            self.assertTrue(app.replace_in_body_var.get())
            self.assertFalse(app.auto_colors_var.get())
        finally:
            root.destroy()


class TestHtmlViewerExport(unittest.TestCase):
    def test_load_script_sequence_allows_multiple_lines_per_image(self):
        import export_html_viewer

        with tempfile.TemporaryDirectory() as td:
            csv_p = Path(td) / "seq.csv"
            csv_p.write_text(
                "\ufeff"
                "id,speaker,line\n"
                "# comment\n"
                "\n"
                "001,彼女,最初の一言\n"
                '001,彼,"二言目\\n改行"\n'
                "002,,地の文テスト\n",
                encoding="utf-8",
            )
            entries, warnings = export_html_viewer.load_script_sequence(csv_p)

        self.assertEqual(warnings, [])
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0], {"key": "001", "speaker": "彼女", "text": "最初の一言"})
        self.assertEqual(entries[1], {"key": "001", "speaker": "彼", "text": "二言目\n改行"})
        self.assertEqual(entries[2], {"key": "002", "speaker": "", "text": "地の文テスト"})

    def test_export_html_viewer_structure_and_offline_features(self):
        import export_html_viewer

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            out = root / "viewer"
            src.mkdir()
            Image.new("RGB", (600, 800), (40, 50, 70)).save(src / "001_a.png")
            Image.new("RGB", (600, 800), (70, 50, 40)).save(src / "002_cg.png")
            Image.new("RGB", (600, 800), (50, 70, 50)).save(src / "003_end.png")

            csv_p = root / "script.csv"
            csv_p.write_text(
                "001,彼女,おはよう\n"
                "001,彼,おはよう、{{彼女}}\n"
                "003,,そして二人は歩き出した。\n",
                encoding="utf-8",
            )
            cfg = {
                "mode": "overlay",
                "position": "bottom",
                "overlay_opacity": 0.45,
                "overlay_fade": 0.35,
                "overlay_margin": 0.0,
                "text_outline": 2,
                "band_color": (12, 12, 14),
                "text_color": (255, 255, 255),
                "narration_color": (234, 237, 245),
                "speaker_style": "plate",
                "speaker_gap": 0.5,
                "speaker_names": {"彼女": "さくら"},
                "replace_speaker_in_body": False,
                "font_scale": 1.0,
                "line_height": 1.45,
                "pad_x": 0.045,
                "format": "keep",
                "quality": 92,
                "auto_speaker_colors": False,
                "colors": {"彼女": (255, 158, 199), "彼": (150, 200, 255)},
            }

            res = export_html_viewer.export_html_viewer(src, csv_p, out, cfg, title="サンプル物語")
            self.assertEqual(res["images"], 3)
            self.assertEqual(res["steps"], 4)
            self.assertTrue((out / "index.html").is_file())
            self.assertTrue((out / "scenario.js").is_file())
            self.assertTrue((out / "images" / "001_a.png").is_file())
            self.assertTrue((out / "images" / "002_cg.png").is_file())
            self.assertTrue((out / "images" / "003_end.png").is_file())

            js_raw = (out / "scenario.js").read_text(encoding="utf-8")
            prefix = "window.__DIALOGUE_VIEWER_DATA__ = "
            self.assertTrue(js_raw.startswith(prefix))
            payload = json.loads(js_raw[len(prefix) :].rstrip().rstrip(";"))

            self.assertEqual(payload["version"], "1.8")
            self.assertEqual(payload["title"], "サンプル物語")
            self.assertEqual(payload["displayTitle"], "サンプル物語")
            self.assertFalse(payload["hasAltImages"])
            self.assertIn("maxLines", payload["defaults"])
            self.assertFalse(payload["defaults"]["replaceInBody"])
            self.assertEqual(payload["speakers"], ["さくら", "彼"])
            self.assertEqual(payload["speakerColors"]["さくら"], "#FF9EC7")
            self.assertAlmostEqual(payload["defaults"]["overlayOpacity"], 0.45, places=2)
            self.assertEqual(payload["defaults"]["speakerStyle"], "plate")
            self.assertNotIn("align", payload["defaults"])
            self.assertNotIn("speakerScale", payload["defaults"])

            steps = payload["steps"]
            self.assertEqual([s["key"] for s in steps], ["001", "001", "002", "003"])
            self.assertEqual(steps[0]["speaker"], "さくら")
            self.assertEqual(steps[1]["text"], "おはよう、さくら")
            self.assertEqual(steps[2]["speaker"], "")
            self.assertEqual(steps[2]["text"], "")

            html_raw = (out / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("fetch(", html_raw)
            for token in (
                "btnToggleText",
                "btnToggleSfx",
                "btnRestoreSfx",
                "restore-dock",
                ">セリフを表示</button>",
                "modalNames",
                "chkReplaceInBody",
                "modalLog",
                "btnAuto",
                "modalThumbs",
                "rngOpacity",
                "rngAutoSpeed",
                "selMode",
                "topbar-visible",
                "btnMenuToggle",
                "chkPinTopbar",
                "btnFullscreen",
                "modalEnd",
                "settings-backdrop",
                "touchstart",
                "0.20",
                'min="1" max="100"',
                "opacityLevel: 50",
                "fontLevel: 50",
                "autoSpeedLevel: 50",
                "computeAutoDelayMs",
                "mapAutoWaitMult",
                "--extend-band-h",
                "vh * 0.85",
                "updateLayoutMetrics",
                'thumbMode = "images"',
                "tb-nav",
                "tb-actions",
                "btnCloseTopbar",
                "cols-3",
                "--font-px",
                "100dvh",
                "def.replaceInBody === true",
                '"彼等"',
            ):
                self.assertIn(token, html_raw)
            self.assertLess(html_raw.index("tabThumbImages"), html_raw.index("tabThumbScenes"))

            # replace_speaker_in_body=True propagates into scenario.js defaults.replaceInBody
            out_rep = root / "viewer_rep"
            export_html_viewer.export_html_viewer(
                src, csv_p, out_rep, dict(cfg, replace_speaker_in_body=True), title="置換ON"
            )
            rep_raw = (out_rep / "scenario.js").read_text(encoding="utf-8")
            payload_rep = json.loads(rep_raw[len(prefix) :].rstrip().rstrip(";"))
            self.assertTrue(payload_rep["defaults"]["replaceInBody"])
            for removed in (
                "selSpeakerStyle",
                "rngSpeakerScale",
                "selAlign",
                "settings-hint",
                "rngFade",
                "rngOutline",
                "selLayout",
                "rngAutoSec",
                "autoSec:",
                "プレースホルダ",
                "(overlay)",
                "(extend)",
                "閉じる (Esc)",
                ">セリフを表示 (H)<",
                "テキストなし画像",
                "overflow-x: auto",
                "localStorage",
                "sessionStorage",
            ):
                self.assertNotIn(removed, html_raw)

            # When --title is omitted, <title> falls back to folder name while displayTitle stays empty
            out_notitle = root / "viewer_notitle"
            export_html_viewer.export_html_viewer(src, csv_p, out_notitle, cfg, title=None)
            js_nt = (out_notitle / "scenario.js").read_text(encoding="utf-8")
            payload_nt = json.loads(js_nt[len(prefix) :].rstrip().rstrip(";"))
            self.assertEqual(payload_nt["title"], "src")
            self.assertEqual(payload_nt["displayTitle"], "")

    def test_cli_export_html_entrypoints(self):
        import export_html_viewer

        with tempfile.TemporaryDirectory() as td:
            out1 = Path(td) / "v1"
            out2 = Path(td) / "v2"
            rc1 = adb.main(
                [
                    str(ROOT / "sample_input"),
                    str(ROOT / "sample_script.csv"),
                    str(out1),
                    "--config",
                    str(ROOT / "sample_config.json"),
                    "--export-html",
                    "--title",
                    "CLIテスト",
                ]
            )
            self.assertEqual(rc1, 0)
            self.assertTrue((out1 / "index.html").is_file())
            self.assertTrue((out1 / "scenario.js").is_file())

            rc2 = export_html_viewer.main(
                [
                    str(ROOT / "sample_input"),
                    str(ROOT / "sample_script.csv"),
                    str(out2),
                    "--title",
                    "単体CLI",
                ]
            )
            self.assertEqual(rc2, 0)
            self.assertTrue((out2 / "index.html").is_file())

    def test_export_html_viewer_sfx_toggle_and_dedup(self):
        import export_html_viewer

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "sfx_on"
            alt = root / "sfx_off"
            out = root / "viewer"
            src.mkdir()
            alt.mkdir()

            Image.new("RGB", (600, 800), (40, 50, 70)).save(src / "001_scene.png")
            Image.new("RGB", (600, 800), (90, 90, 90)).save(src / "002_same.png")
            Image.new("RGB", (600, 800), (50, 70, 50)).save(src / "003_only_main.png")

            # 001 differs, 002 is byte-identical (dedup), 003 missing in alt, 004 extra in alt
            Image.new("RGB", (600, 800), (200, 60, 70)).save(alt / "001_clean.png")
            (alt / "002_clean.png").write_bytes((src / "002_same.png").read_bytes())
            Image.new("RGB", (600, 800), (10, 10, 10)).save(alt / "004_extra.png")

            csv_p = root / "script.csv"
            csv_p.write_text(
                "001,彼女,ドキッとするね\n"
                "001,彼,本当だね\n"
                "002,,同一画像のシーン\n"
                "003,彼女,差分なしページ\n",
                encoding="utf-8",
            )
            cfg = {
                "mode": "overlay",
                "position": "bottom",
                "band_color": (12, 12, 14),
                "text_color": (255, 255, 255),
                "narration_color": (234, 237, 245),
                "format": "keep",
                "quality": 92,
                "auto_speaker_colors": False,
                "colors": {},
            }
            res = export_html_viewer.export_html_viewer(
                src,
                csv_p,
                out,
                cfg,
                title="効果音切替テスト",
                sfx_off_dir=alt,
                default_sfx=False,
                sfx_label="描き文字",
            )
            self.assertEqual(res["images"], 3)
            self.assertEqual(res["alt_images"], 2)
            self.assertTrue(res["has_alt_images"])
            self.assertTrue(any("sfx-off image missing" in w and "003" in w for w in res["warnings"]))
            self.assertTrue(any("extra sfx-off image" in w and "004" in w for w in res["warnings"]))

            self.assertTrue((out / "images" / "sfx" / "001_scene.png").is_file())
            self.assertTrue((out / "images" / "sfx" / "002_same.png").is_file())
            self.assertTrue((out / "images" / "sfx" / "003_only_main.png").is_file())
            self.assertTrue((out / "images" / "nosfx" / "001_clean.png").is_file())
            # 002 was byte-identical -> deduplicated; 004 had no main image -> not copied
            self.assertFalse((out / "images" / "nosfx" / "002_clean.png").exists())
            self.assertFalse((out / "images" / "nosfx" / "004_extra.png").exists())

            js_raw = (out / "scenario.js").read_text(encoding="utf-8")
            prefix = "window.__DIALOGUE_VIEWER_DATA__ = "
            payload = json.loads(js_raw[len(prefix) :].rstrip().rstrip(";"))
            self.assertTrue(payload["hasAltImages"])
            self.assertEqual(payload["altConfig"], {"label": "描き文字", "defaultOn": False})
            self.assertEqual(payload["steps"][0]["image"], "images/sfx/001_scene.png")
            self.assertEqual(payload["steps"][0]["imageAlt"], "images/nosfx/001_clean.png")
            self.assertEqual(payload["steps"][1]["imageAlt"], "images/nosfx/001_clean.png")
            self.assertEqual(payload["steps"][2]["imageAlt"], "images/sfx/002_same.png")
            self.assertEqual(payload["steps"][3]["imageAlt"], "images/sfx/003_only_main.png")

            # CLI entrypoints roundtrip with --sfx-off-dir and --default-sfx off
            out_cli = root / "viewer_cli"
            rc_cli = adb.main(
                [
                    str(src),
                    str(csv_p),
                    str(out_cli),
                    "--export-html",
                    "--sfx-off-dir",
                    str(alt),
                    "--default-sfx",
                    "off",
                ]
            )
            self.assertEqual(rc_cli, 0)
            js_cli = (out_cli / "scenario.js").read_text(encoding="utf-8")
            payload_cli = json.loads(js_cli[len(prefix) :].rstrip().rstrip(";"))
            self.assertTrue(payload_cli["hasAltImages"])
            self.assertFalse(payload_cli["altConfig"]["defaultOn"])

            out_cli2 = root / "viewer_cli2"
            rc_cli2 = export_html_viewer.main(
                [
                    str(src),
                    str(csv_p),
                    str(out_cli2),
                    "--sfx-off-dir",
                    str(alt),
                    "--sfx-label",
                    "擬音",
                ]
            )
            self.assertEqual(rc_cli2, 0)
            js_cli2 = (out_cli2 / "scenario.js").read_text(encoding="utf-8")
            payload_cli2 = json.loads(js_cli2[len(prefix) :].rstrip().rstrip(";"))
            self.assertEqual(payload_cli2["altConfig"], {"label": "擬音", "defaultOn": True})

            # --strict should reject missing sfx-off image
            out_strict = root / "viewer_strict"
            rc_strict = adb.main(
                [
                    str(src),
                    str(csv_p),
                    str(out_strict),
                    "--export-html",
                    "--sfx-off-dir",
                    str(alt),
                    "--strict",
                ]
            )
            self.assertEqual(rc_strict, 1)


if __name__ == "__main__":
    unittest.main()
