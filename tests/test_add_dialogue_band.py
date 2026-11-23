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


if __name__ == "__main__":
    unittest.main()
