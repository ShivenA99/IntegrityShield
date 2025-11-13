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

class TrulySelectiveManipulator:
    def __init__(self, fonts_folder, output_folder):
        self.fonts_folder = Path(fonts_folder)
        self.output_folder = Path(output_folder)
        self.base_font = self.fonts_folder / 'Roboto.ttf'

        # Multiple source fonts for handling repeated characters with different visuals
        self.source_fonts = [
            self.fonts_folder / 'Roboto.ttf',
            self.fonts_folder / 'TimesNewRoman.ttf',
            self.fonts_folder / 'Arial.ttf'
        ]

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

            # Create fonts: one normal + one deceptive font per character position
            normal_font_path = self.output_folder / f'{job_id}_normal.ttf'
            deceptive_fonts = []  # List of (position, font_path)

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

            # Load base font for manipulation
            source_font = TTFont(str(normal_font_path))
            source_cmap = source_font.getBestCmap()
            source_glyph_set = source_font.getGlyphSet()

            if not source_cmap:
                return {
                    'success': False,
                    'error': 'Unable to read cmap from base font'
                }

            # Validate all characters exist
            for c in set(visual_word + hidden_word):
                if ord(c) not in source_cmap:
                    return {
                        'success': False,
                        'error': f"Character '{c}' not in font"
                    }

            # OPTIMIZED UPFRONT: Create all position-specific fonts before PDF generation
            temp_font_dir = self.output_folder / f'{job_id}_fonts'
            temp_font_dir.mkdir(exist_ok=True)

            log_entries.append(f"Using upfront multi-font approach:")
            log_entries.append(f"Font directory: {temp_font_dir.name}")

            # Prepare character mappings and create fonts
            char_mappings = []
            deceptive_font_paths = []

            for pos, (hidden_char, visual_char) in enumerate(zip(hidden_word, visual_word)):
                needs_font = hidden_char != visual_char
                char_mappings.append({
                    'pos': pos,
                    'hidden': hidden_char,
                    'visual': visual_char,
                    'needs_font': needs_font
                })

                if needs_font:
                    # Create position-specific font immediately
                    pos_font = TTFont(str(normal_font_path))
                    pos_glyf = pos_font.get('glyf')
                    pos_hmtx = pos_font.get('hmtx')
                    pos_cmap = pos_font.getBestCmap()

                    hidden_glyph = pos_cmap.get(ord(hidden_char))
                    visual_glyph = source_cmap.get(ord(visual_char))

                    if hidden_glyph and visual_glyph:
                        # Clone visual glyph to hidden glyph
                        pen = TTGlyphPen(source_glyph_set)
                        source_glyph_set[visual_glyph].draw(pen)
                        new_glyph = pen.glyph()

                        # Preserve hinting
                        visual_tt_glyph = source_font['glyf'][visual_glyph]
                        if hasattr(visual_tt_glyph, "program") and visual_tt_glyph.program:
                            new_glyph.program = visual_tt_glyph.program

                        pos_glyf[hidden_glyph] = new_glyph
                        pos_hmtx.metrics[hidden_glyph] = source_font['hmtx'].metrics[visual_glyph]

                    # Save position font
                    pos_font_path = temp_font_dir / f'pos{pos}.ttf'
                    pos_font.save(str(pos_font_path))
                    deceptive_font_paths.append(pos_font_path)

                    log_entries.append(f"  Pos {pos}: '{hidden_char}' → '{visual_char}' (font: {pos_font_path.name})")

            # Store info for PDF generation
            deceptive_fonts = {
                'font_dir': temp_font_dir,
                'normal_font': normal_font_path,
                'mappings': char_mappings,
                'font_paths': deceptive_font_paths
            }

            log_entries.append(f"Created {len(deceptive_font_paths)} position-specific fonts upfront")

            # Create PDF with position-specific fonts
            pdf_file = self._create_pdf_multichar(
                visual_word,
                hidden_word,
                normal_font_path,
                deceptive_fonts,
                job_id
            )

            log_file = log_dir / 'steps.log'
            with open(log_file, 'w', encoding='utf-8') as handle:
                handle.write('\n'.join(log_entries) + '\n')

            if pdf_file:
                return {
                    'success': True,
                    'pdf_file': pdf_file,
                    'font_file': normal_font_path.name,
                    'log_dir': str(log_dir.relative_to(self.output_folder)),
                    'message': 'Sequential multi-font manipulation successful'
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

    def _create_pdf_multichar(self, visual_word, hidden_word, normal_font, font_data, job_id):
        """Create PDF with pre-created position-specific fonts."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Copy normal font
            shutil.copy(normal_font, os.path.join(temp_dir, 'normal.ttf'))

            # Extract font data
            mappings = font_data['mappings']
            font_dir = font_data['font_dir']

            # Copy all position-specific fonts to temp dir
            font_declarations = []
            for pos_font_path in font_data.get('font_paths', []):
                shutil.copy(pos_font_path, os.path.join(temp_dir, pos_font_path.name))
                # Extract position number from filename (e.g., pos0.ttf -> 0)
                pos_num = pos_font_path.stem.replace('pos', '')
                font_declarations.append(f"\\newfontfamily\\pos{pos_num}font{{pos{pos_num}}}[Path={temp_dir}/,Extension=.ttf]")

            # Build deceptive word with font switches and ActualText for proper text layer
            deceptive_word_parts = []
            for mapping in mappings:
                pos = mapping['pos']
                hidden_char = mapping['hidden']
                needs_font = mapping['needs_font']

                if not needs_font:
                    # No manipulation - use normal font
                    deceptive_word_parts.append(hidden_char)
                else:
                    # Add character with font switch and ActualText for PDF text layer
                    # Use PDF literal to set ActualText
                    deceptive_word_parts.append(f"\\BeginAccSupp{{method=pdfstringdef,ActualText={hidden_char}}}{{\\pos{pos}font {hidden_char}}}\\EndAccSupp{{}}")

            deceptive_word_tex = ''.join(deceptive_word_parts)

            # Build font declarations in preamble (one per line)
            preamble_fonts = '\n'.join(font_declarations)

            tex_content = r"""\documentclass[12pt]{article}
\usepackage{fontspec}
\usepackage{xcolor}
\usepackage[margin=1in]{geometry}
\usepackage{accsupp}

\setmainfont{normal}[
    Path = """ + temp_dir + r"""/,
    Extension = .ttf
]

""" + preamble_fonts + r"""

\begin{document}

\begin{center}
{\Huge \textbf{Font Manipulation Demo}}\\[0.3cm]
{\large Sequential Multi-Font Approach}
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
    \item Second (RED): DECEPTIVE - Copy this!
    \item Third: NORMAL
    \item The RED word copies as different text
\end{enumerate}
}}
\end{center}

\vspace{1.5cm}

\begin{center}
{\LARGE Normal: \textbf{""" + visual_word + r"""}}\\[1cm]
{\Huge \textcolor{red}{Deceptive: \textbf{""" + deceptive_word_tex + r"""}}}\\[1cm]
{\LARGE Normal: \textbf{""" + visual_word + r"""}}
\end{center}

\vspace{1.5cm}

\section*{Technical Details}

\begin{itemize}
    \item Visual: \textbf{""" + visual_word + r"""}
    \item Hidden: \texttt{""" + hidden_word + r"""}
    \item Mode: Sequential Multi-Font (""" + str(len([m for m in mappings if m['needs_font']])) + r""" fonts)
    \item Each character uses position-specific font
\end{itemize}

\begin{center}
\small{\textit{arXiv:2505.16957 - Font Manipulation Research}}
\end{center}

\end{document}
"""

            tex_file = os.path.join(temp_dir, 'document.tex')
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(tex_content)

            # Compile with LuaLaTeX (faster than XeLaTeX for multi-font documents)
            for _ in range(2):
                subprocess.run(
                    ['lualatex', '-interaction=nonstopmode', 'document.tex'],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True
                )

            pdf_src = os.path.join(temp_dir, 'document.pdf')
            pdf_dst = self.output_folder / f'{job_id}.pdf'

            if os.path.exists(pdf_src):
                shutil.copy(pdf_src, pdf_dst)
                # Copy tex file for debugging
                tex_dst = self.output_folder / f'{job_id}.tex'
                shutil.copy(tex_file, tex_dst)
                return pdf_dst.name
            else:
                return None

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

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
\usepackage{accsupp}

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

            # Compile with LuaLaTeX (faster than XeLaTeX for multi-font documents)
            for _ in range(2):
                subprocess.run(
                    ['lualatex', '-interaction=nonstopmode', 'document.tex'],
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
