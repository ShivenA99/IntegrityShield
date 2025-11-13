import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen

from backend.manipulators.truly_selective import TrulySelectiveManipulator


def _glyph_bounds(ttfont: TTFont, glyph_name: str):
    """Return the bounding box for the given glyph."""
    glyph_set = ttfont.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    return pen.bounds


class TrulySelectiveManipulatorTests(TestCase):
    """Tests for the truly selective manipulator glyph cloning logic."""

    def test_hidden_word_glyphs_match_visual_glyphs(self):
        """Hidden characters should reuse the visual glyph outlines and metrics."""
        fonts_folder = Path('backend') / 'fonts'

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            manipulator = TrulySelectiveManipulator(str(fonts_folder), str(output_dir))

            with patch.object(TrulySelectiveManipulator, '_create_pdf', return_value='dummy.pdf'):
                result = manipulator.create_manipulation('hello', 'world')

            self.assertTrue(result['success'])

            deceptive_font = output_dir / result['font_file']
            normal_font = output_dir / result['font_file'].replace('_deceptive.ttf', '_normal.ttf')

            self.assertTrue(deceptive_font.exists())
            self.assertTrue(normal_font.exists())

            deceptive_tt = TTFont(str(deceptive_font))
            normal_tt = TTFont(str(normal_font))

            deceptive_cmap = deceptive_tt.getBestCmap()
            normal_cmap = normal_tt.getBestCmap()

            for hidden_char, visual_char in zip('world', 'hello'):
                hidden_glyph = deceptive_cmap[ord(hidden_char)]
                baseline_visual_glyph = normal_cmap[ord(visual_char)]

                # Hidden glyph should share geometry with the visual glyph as it
                # appears in the pristine (normal) font.
                self.assertEqual(
                    _glyph_bounds(deceptive_tt, hidden_glyph),
                    _glyph_bounds(normal_tt, baseline_visual_glyph)
                )

                # Metrics should match the baseline visual glyph as well.
                hidden_metrics = deceptive_tt['hmtx'].metrics[hidden_glyph]
                visual_metrics = normal_tt['hmtx'].metrics[baseline_visual_glyph]
                self.assertEqual(hidden_metrics, visual_metrics)
