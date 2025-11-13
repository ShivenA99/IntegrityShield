"""
Truly Selective Manipulation V4 - FIXED
For repeated characters with different visuals:
Creates TWO separate fonts like V1, but loads source font separately to avoid glyph contamination.
This ensures each glyph is cloned from the ORIGINAL unmodified glyph, not a previously modified one.
"""

import os
import shutil
import tempfile
import json
from fontTools.ttLib import TTFont
import subprocess
from pathlib import Path
import uuid
from datetime import datetime
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.varLib import instancer

class TrulySelectiveManipulatorV4:
    def __init__(self, fonts_folder, output_folder):
        self.fonts_folder = Path(fonts_folder)
        self.output_folder = Path(output_folder)
        self.base_font = self.fonts_folder / 'Roboto.ttf'

        # Load Unicode alternates from JSON file
        alternates_file = Path(__file__).parent / 'unicode_alternates.json'
        with open(alternates_file, 'r', encoding='utf-8') as f:
            alternates_data = json.load(f)

        # Merge all categories into a single dictionary
        self.alternates = {}
        self.alternates.update(alternates_data.get('lowercase', {}))
        self.alternates.update(alternates_data.get('uppercase', {}))
        self.alternates.update(alternates_data.get('digits', {}))
        self.alternates.update(alternates_data.get('punctuation', {}))

    def create_manipulation(self, visual_word, hidden_word):
        """
        Create manipulation using TWO separate fonts (like V1).
        Fixes the glyph contamination bug by loading source font separately.

        This allows repeated characters to have different visuals because we're using
        TWO fonts: normal font and deceptive font.
        """
        try:
            if len(visual_word) != len(hidden_word):
                return {
                    'success': False,
                    'error': 'Words must be same length'
                }

            if not self.base_font.exists():
                return {
                    'success': False,
                    'error': f'Base font not found: {self.base_font}'
                }

            # Generate unique ID
            job_id = str(uuid.uuid4())[:8]

            # Logging
            logs_root = self.output_folder / 'logs'
            logs_root.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_dir = logs_root / f'{timestamp}_{job_id}'
            log_dir.mkdir(exist_ok=True)
            log_entries = [
                f"Job ID: {job_id}",
                f"Timestamp: {timestamp}",
                f"Visual word: {visual_word}",
                f"Hidden word: {hidden_word}",
                f"Method: Alternate Unicode Codepoints (V4) - Using JSON mappings"
            ]

            # Use alternates loaded from JSON file
            ALTERNATES = self.alternates

            # Create fonts
            normal_font_path = self.output_folder / f'{job_id}_normal.ttf'
            deceptive_font_path = self.output_folder / f'{job_id}_deceptive_v4.ttf'

            # Load and instantiate base font
            base_font_tt = TTFont(str(self.base_font))
            if 'fvar' in base_font_tt:
                axis_defaults = {axis.axisTag: axis.defaultValue for axis in base_font_tt['fvar'].axes}
                log_entries.append(f"Variable font instantiated: {axis_defaults}")
                base_font_tt = instancer.instantiateVariableFont(base_font_tt, axis_defaults, inplace=False)
            else:
                log_entries.append("Static font detected")

            base_font_tt.save(str(normal_font_path))
            log_entries.append(f"Saved normal font: {normal_font_path.name}")

            # Work on deceptive font
            font = TTFont(str(normal_font_path))

            glyf_table = font.get('glyf')
            hmtx_table = font.get('hmtx')

            if not glyf_table or not hmtx_table:
                return {
                    'success': False,
                    'error': 'Missing glyf/hmtx tables'
                }

            cmap = font.getBestCmap()
            if not cmap:
                return {
                    'success': False,
                    'error': 'Cannot read cmap'
                }

            # Validate characters
            for c in set(visual_word + hidden_word):
                if ord(c) not in cmap:
                    return {
                        'success': False,
                        'error': f"Character '{c}' not in font"
                    }

            glyph_set = font.getGlyphSet()

            # Track character usage to know when to use alternates
            char_usage = {}
            for char in hidden_word:
                char_usage[char] = char_usage.get(char, 0) + 1

            # Track which occurrence we're on
            char_occurrence = {}

            modified_hidden_word = ""
            log_entries.append("Creating character mappings:")

            for idx, (hidden_char, visual_char) in enumerate(zip(hidden_word, visual_word)):
                # Track occurrence number
                if hidden_char not in char_occurrence:
                    char_occurrence[hidden_char] = 0

                occurrence_num = char_occurrence[hidden_char]
                char_occurrence[hidden_char] += 1

                visual_glyph = cmap.get(ord(visual_char))

                # Determine which character to use
                if occurrence_num == 0:
                    # First occurrence - use base character
                    use_char = hidden_char
                    hidden_glyph = cmap.get(ord(hidden_char))
                else:
                    # Subsequent occurrence - use alternate
                    if hidden_char in ALTERNATES:
                        alternates_list = ALTERNATES[hidden_char]
                        alt_index = occurrence_num - 1

                        if alt_index < len(alternates_list):
                            use_char = alternates_list[alt_index]
                            alt_codepoint = ord(use_char)

                            # Create or find glyph for alternate
                            if alt_codepoint in cmap:
                                hidden_glyph = cmap[alt_codepoint]
                            else:
                                # Add new glyph mapping
                                hidden_glyph = f"{hidden_char}_alt{alt_index}"
                                glyph_order = list(font.getGlyphOrder())
                                if hidden_glyph not in glyph_order:
                                    glyph_order.append(hidden_glyph)
                                    font.setGlyphOrder(glyph_order)

                                # Add to cmap
                                for table in font['cmap'].tables:
                                    if table.isUnicode():
                                        table.cmap[alt_codepoint] = hidden_glyph
                        else:
                            # Ran out of alternates
                            log_entries.append(f"  Pos {idx}: WARNING - no more alternates for '{hidden_char}' (occurrence {occurrence_num + 1})")
                            use_char = hidden_char
                            hidden_glyph = cmap.get(ord(hidden_char))
                    else:
                        # No alternates defined
                        log_entries.append(f"  Pos {idx}: WARNING - no alternates defined for '{hidden_char}'")
                        use_char = hidden_char
                        hidden_glyph = cmap.get(ord(hidden_char))

                # Clone visual glyph to hidden glyph (always, even if same)
                if hidden_glyph != visual_glyph:
                    # Different glyphs - need to clone
                    pen = TTGlyphPen(glyph_set)
                    glyph_set[visual_glyph].draw(pen)
                    new_glyph = pen.glyph()

                    visual_tt_glyph = font['glyf'][visual_glyph]
                    if hasattr(visual_tt_glyph, "program") and visual_tt_glyph.program:
                        new_glyph.program = visual_tt_glyph.program

                    glyf_table[hidden_glyph] = new_glyph
                    hmtx_table.metrics[hidden_glyph] = font['hmtx'].metrics[visual_glyph]

                    if use_char == hidden_char:
                        log_entries.append(f"  Pos {idx}: '{use_char}' → '{visual_char}' (occurrence {occurrence_num + 1}/{char_usage[hidden_char]})")
                    else:
                        log_entries.append(f"  Pos {idx}: '{use_char}' (U+{ord(use_char):04X}) → '{visual_char}' (occurrence {occurrence_num + 1}/{char_usage[hidden_char]})")
                else:
                    # Same glyph - no cloning needed but log it
                    if use_char != hidden_char:
                        log_entries.append(f"  Pos {idx}: '{use_char}' (U+{ord(use_char):04X}) same as '{visual_char}' (no clone needed)")

                modified_hidden_word += use_char

            font.save(str(deceptive_font_path))
            log_entries.append(f"Saved deceptive font: {deceptive_font_path.name}")
            log_entries.append(f"Modified hidden word: {repr(modified_hidden_word)}")

            # Create PDF
            pdf_file = self._create_pdf(
                visual_word,
                modified_hidden_word,
                normal_font_path,
                deceptive_font_path,
                job_id
            )

            # Save log
            log_file = log_dir / 'steps.log'
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(log_entries) + '\n')

            if pdf_file:
                return {
                    'success': True,
                    'pdf_file': pdf_file,
                    'font_file': deceptive_font_path.name,
                    'log_dir': str(log_dir.relative_to(self.output_folder)),
                    'message': 'V4 manipulation successful (variation selectors)'
                }
            else:
                return {
                    'success': False,
                    'error': 'PDF creation failed'
                }

        except Exception as e:
            import traceback
            return {
                'success': False,
                'error': f"{str(e)}\n{traceback.format_exc()}"
            }

    def _create_pdf(self, visual_word, modified_hidden_word, normal_font, deceptive_font, job_id):
        """Create PDF with alternate Unicode characters."""
        temp_dir = tempfile.mkdtemp()
        try:
            shutil.copy(normal_font, os.path.join(temp_dir, 'normal.ttf'))
            shutil.copy(deceptive_font, os.path.join(temp_dir, 'deceptive.ttf'))

            tex_content = r"""\documentclass[12pt]{article}
\usepackage{fontspec}
\usepackage{xcolor}
\usepackage[margin=1in]{geometry}

\setmainfont{normal}[
    Path = """ + temp_dir + r"""/,
    Extension = .ttf
]

\newfontfamily\deceptivefont{deceptive}[
    Path = """ + temp_dir + r"""/,
    Extension = .ttf
]

\begin{document}

\begin{center}
{\Huge \textbf{Font Manipulation Demo V4}}\\[0.3cm]
{\large Variation Selectors for Repeated Characters}
\end{center}

\vspace{1.5cm}

\section*{Normal Text}

This paragraph uses normal font. The word """ + visual_word + r""" appears here naturally.

\vspace{1cm}

\section*{Deceptive Word Test}

\begin{center}
\fbox{\parbox{0.9\textwidth}{
\textbf{INSTRUCTIONS:}
\begin{enumerate}
    \item Compare the three instances below
    \item Second (RED) uses variation selectors
    \item Try copying the RED text
\end{enumerate}
}}
\end{center}

\vspace{1.5cm}

\begin{center}
{\LARGE Normal: \textbf{""" + visual_word + r"""}}\\[1cm]
{\Huge \textcolor{red}{Deceptive: {\deceptivefont\textbf{""" + modified_hidden_word + r"""}}}}\\[1cm]
{\LARGE Normal: \textbf{""" + visual_word + r"""}}
\end{center}

\vspace{1.5cm}

\section*{Technical Details}

\begin{itemize}
    \item Visual: \textbf{""" + visual_word + r"""}
    \item Mode: V4 - Variation Selectors
    \item Handles repeated characters needing different visuals
\end{itemize}

\end{document}
"""

            tex_file = os.path.join(temp_dir, 'document.tex')
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(tex_content)

            # Compile
            for _ in range(2):
                subprocess.run(
                    ['xelatex', '-interaction=nonstopmode', 'document.tex'],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True
                )

            pdf_src = os.path.join(temp_dir, 'document.pdf')
            pdf_dst = self.output_folder / f'{job_id}.pdf'

            if os.path.exists(pdf_src):
                shutil.copy(pdf_src, pdf_dst)
                return pdf_dst.name
            else:
                return None

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
