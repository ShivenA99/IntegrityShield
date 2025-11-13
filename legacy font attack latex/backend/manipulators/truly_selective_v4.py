"""
Truly Selective Manipulation
Only affects ONE specific word instance, all other text completely normal
"""

import os
import shutil
import tempfile
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

    def create_manipulation(self, visual_word, hidden_word):
        """
        Create truly selective manipulation using two fonts.

        Returns:
            dict: {
                'success': bool,
                'pdf_file': str,
                'font_file': str (optional),
                'message': str
            }
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

            # Generate unique ID for this manipulation
            job_id = str(uuid.uuid4())[:8]

            # Prepare logging
            logs_root = self.output_folder / 'logs'
            logs_root.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_dir = logs_root / f'{timestamp}_{job_id}'
            log_dir.mkdir(exist_ok=True)
            log_entries = [
                f"Job ID: {job_id}",
                f"Timestamp: {timestamp}",
                f"Visual word: {visual_word}",
                f"Hidden word: {hidden_word}"
            ]

            # Create two fonts
            normal_font_path = self.output_folder / f'{job_id}_normal.ttf'
            deceptive_font_path = self.output_folder / f'{job_id}_deceptive_v4.ttf'

            # Load base font and, if variable, instantiate it to a static face so we can
            # manipulate glyph data safely.
            base_font_tt = TTFont(str(self.base_font))
            if 'fvar' in base_font_tt:
                axis_defaults = {axis.axisTag: axis.defaultValue for axis in base_font_tt['fvar'].axes}
                log_entries.append(f"Detected variable font. Instantiating with axis defaults: {axis_defaults}")
                base_font_tt = instancer.instantiateVariableFont(base_font_tt, axis_defaults, inplace=False)
            else:
                log_entries.append("Base font is static. No instancing required.")

            # Save static/unchanged version for normal text rendering
            base_font_tt.save(str(normal_font_path))
            log_entries.append(f"Saved static base font to {normal_font_path.name}")

            # Work on a fresh copy for deceptive manipulation
            font = TTFont(str(normal_font_path))
            source_font = TTFont(str(normal_font_path))  # keep pristine copy for cloning

            # Access glyph and metrics tables for glyph cloning approach
            glyf_table = font.get('glyf')
            hmtx_table = font.get('hmtx')

            if glyf_table is None or hmtx_table is None:
                return {
                    'success': False,
                    'error': 'Required glyf/hmtx tables missing in base font'
                }

            cmap = font.getBestCmap()
            if cmap is None:
                return {
                    'success': False,
                    'error': 'Unable to read cmap from base font'
                }

            missing_visual_chars = [c for c in set(visual_word) if ord(c) not in cmap]
            if missing_visual_chars:
                missing = ', '.join(sorted(missing_visual_chars))
                return {
                    'success': False,
                    'error': f"Visual characters not in font: {missing}"
                }

            missing_hidden_chars = [c for c in set(hidden_word) if ord(c) not in cmap]
            if missing_hidden_chars:
                missing = ', '.join(sorted(missing_hidden_chars))
                return {
                    'success': False,
                    'error': f"Hidden characters not in font: {missing}"
                }

            glyph_set = font.getGlyphSet()
            source_glyph_set = source_font.getGlyphSet()

            log_entries.append("V4: Beginning glyph cloning operations (with pristine source):")

            # Clone glyph outlines/metrics from the visual characters onto the hidden ones
            for hidden_char, visual_char in zip(hidden_word, visual_word):
                hidden_glyph = cmap.get(ord(hidden_char))
                visual_glyph = cmap.get(ord(visual_char))

                if not hidden_glyph or not visual_glyph:
                    return {
                        'success': False,
                        'error': f"Missing glyph mapping for pair '{hidden_char}' → '{visual_char}'"
                    }

                if hidden_glyph == visual_glyph:
                    # Already identical glyphs, nothing to copy
                    continue

                if visual_glyph not in glyf_table.glyphs:
                    return {
                        'success': False,
                        'error': f"Glyph '{visual_glyph}' missing from glyf table"
                    }

                visual_tt_glyph = source_font['glyf'][visual_glyph]
                pen = TTGlyphPen(source_glyph_set)
                source_glyph_set[visual_glyph].draw(pen)
                new_glyph = pen.glyph()

                # Preserve hinting instructions when present
                if hasattr(visual_tt_glyph, "program") and visual_tt_glyph.program:
                    new_glyph.program = visual_tt_glyph.program

                glyf_table[hidden_glyph] = new_glyph

                if visual_glyph in source_font['hmtx'].metrics:
                    hmtx_table.metrics[hidden_glyph] = source_font['hmtx'].metrics[visual_glyph]

                log_entries.append(
                    f"  '{hidden_char}' (glyph '{hidden_glyph}') now uses outline from '{visual_char}' (glyph '{visual_glyph}')"
                )

            # Save deceptive font
            font.save(str(deceptive_font_path))
            log_entries.append(f"Saved deceptive font to {deceptive_font_path.name}")

            # Create PDF
            pdf_file = self._create_pdf(
                visual_word,
                hidden_word,
                normal_font_path,
                deceptive_font_path,
                job_id
            )

            log_file = log_dir / 'steps.log'
            with open(log_file, 'w', encoding='utf-8') as handle:
                handle.write('\n'.join(log_entries) + '\n')

            if pdf_file:
                return {
                    'success': True,
                    'pdf_file': pdf_file,
                    'font_file': deceptive_font_path.name,
                    'log_dir': str(log_dir.relative_to(self.output_folder)),
                    'message': 'Selective manipulation successful'
                }
            else:
                return {
                    'success': False,
                    'error': 'PDF creation failed'
                }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _create_pdf(self, visual_word, hidden_word, normal_font, deceptive_font, job_id):
        """Create PDF with mixed fonts."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Copy fonts to temp
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
{\Huge \textbf{Font Manipulation Demo}}\\[0.3cm]
{\large Selective Word Deception}
\end{center}

\vspace{1.5cm}

\section*{Normal Text}

This paragraph uses normal font. The word """ + visual_word + r""" appears here naturally.
All text renders correctly: a b c d e f g h i j k l m n o p q r s t u v w x y z.

\vspace{1cm}

\section*{Deceptive Word Test}

\begin{center}
\fbox{\parbox{0.9\textwidth}{
\textbf{INSTRUCTIONS:}
\begin{enumerate}
    \item Look at the three instances below
    \item First: NORMAL
    \item Second (RED): DECEPTIVE
    \item Third: NORMAL
    \item Copy the RED word
\end{enumerate}
}}
\end{center}

\vspace{1.5cm}

\begin{center}
{\LARGE Normal: \textbf{""" + visual_word + r"""}}\\[1cm]
{\Huge \textcolor{red}{Deceptive: {\deceptivefont\textbf{""" + hidden_word + r"""}}}}\\[1cm]
{\LARGE Normal: \textbf{""" + visual_word + r"""}}
\end{center}

\vspace{1.5cm}

\section*{Technical Details}

\begin{itemize}
    \item Visual: \textbf{""" + visual_word + r"""}
    \item Hidden: \texttt{""" + hidden_word + r"""}
    \item Mode: Truly Selective (Dual Font)
    \item Only RED word is manipulated
\end{itemize}

\begin{center}
\small{\textit{arXiv:2505.16957 - Font Manipulation Research}}
\end{center}

\end{document}
"""

            tex_file = os.path.join(temp_dir, 'document.tex')
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(tex_content)

            # Compile with XeLaTeX
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
