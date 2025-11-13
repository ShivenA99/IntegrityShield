"""
Cyrillic Homoglyphs Manipulation
Uses Cyrillic characters that look like Latin but have different Unicode
"""

import os
import shutil
import tempfile
from fontTools.ttLib import TTFont
import subprocess
from pathlib import Path
import uuid

class CyrillicManipulator:
    def __init__(self, fonts_folder, output_folder):
        self.fonts_folder = Path(fonts_folder)
        self.output_folder = Path(output_folder)
        self.base_font = self.fonts_folder / 'Roboto.ttf'

    def create_manipulation(self, visual_word, hidden_word):
        """
        Create manipulation using Cyrillic homoglyphs.

        Note: This maps Cyrillic chars to Latin glyphs.
        When copied, shows Cyrillic characters.
        """
        try:
            if not self.base_font.exists():
                return {
                    'success': False,
                    'error': f'Base font not found: {self.base_font}'
                }

            job_id = str(uuid.uuid4())[:8]

            # Cyrillic to Latin mappings
            cyrillic_mappings = {
                0x0443: ord('h'),  # у → h
                0x043E: ord('e'),  # о → e
                0x0440: ord('l'),  # р → l
                0x0441: ord('l'),  # с → l
                0x0430: ord('o'),  # а → o
            }

            font = TTFont(str(self.base_font))

            unicode_cmap = None
            for table in font['cmap'].tables:
                if table.platformID == 3 and table.platEncID == 1:
                    unicode_cmap = table
                    break

            if not unicode_cmap:
                return {
                    'success': False,
                    'error': 'No suitable cmap table'
                }

            # Map Cyrillic to Latin glyphs
            for cyrillic_code, latin_code in cyrillic_mappings.items():
                if latin_code in unicode_cmap.cmap:
                    target_glyph = unicode_cmap.cmap[latin_code]
                    unicode_cmap.cmap[cyrillic_code] = target_glyph

            # Save font
            font_path = self.output_folder / f'{job_id}_cyrillic.ttf'
            font.save(str(font_path))

            # Create deceptive word using Cyrillic
            deceptive_word = "уорса"  # Cyrillic chars that display as "hello"

            # Create PDF
            pdf_file = self._create_pdf(visual_word, deceptive_word, font_path, job_id)

            if pdf_file:
                return {
                    'success': True,
                    'pdf_file': pdf_file,
                    'font_file': font_path.name,
                    'message': 'Cyrillic manipulation successful'
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

    def _create_pdf(self, visual_word, deceptive_word, font_path, job_id):
        """Create PDF."""
        temp_dir = tempfile.mkdtemp()
        try:
            shutil.copy(font_path, os.path.join(temp_dir, 'font.ttf'))

            tex_content = r"""\documentclass[12pt]{article}
\usepackage{fontspec}
\usepackage{xcolor}
\usepackage[margin=1in]{geometry}

\setmainfont{font}[
    Path = """ + temp_dir + r"""/,
    Extension = .ttf
]

\begin{document}

\begin{center}
{\Huge \textbf{Cyrillic Manipulation}}\\[0.3cm]
{\large Cyrillic characters display as Latin}
\end{center}

\vspace{1.5cm}

\section*{Test}

\begin{center}
\fbox{\parbox{0.9\textwidth}{
Copy the RED word below and paste into a text editor.
You'll see Cyrillic characters or boxes!
}}
\end{center}

\vspace{1.5cm}

\begin{center}
{\LARGE Normal: \textbf{""" + visual_word + r"""}}\\[1cm]
{\Huge \textcolor{red}{Deceptive: \textbf{""" + deceptive_word + r"""}}}\\[1cm]
{\LARGE Normal: \textbf{""" + visual_word + r"""}}
\end{center}

\vspace{1cm}

\subsection*{How It Works}

\begin{itemize}
    \item RED word contains: Cyrillic characters (у о р с а)
    \item Font displays them as: """ + visual_word + r"""
    \item When copied: Shows Cyrillic or boxes
\end{itemize}

\end{document}
"""

            tex_file = os.path.join(temp_dir, 'document.tex')
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(tex_content)

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
