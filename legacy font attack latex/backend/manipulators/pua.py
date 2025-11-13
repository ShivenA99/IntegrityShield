"""
Private Use Area (PUA) Manipulation
Uses Unicode PUA range for custom character mappings
"""

import os
import shutil
import tempfile
from fontTools.ttLib import TTFont
import subprocess
from pathlib import Path
import uuid

class PUAManipulator:
    def __init__(self, fonts_folder, output_folder):
        self.fonts_folder = Path(fonts_folder)
        self.output_folder = Path(output_folder)
        self.base_font = self.fonts_folder / 'Roboto.ttf'

    def create_manipulation(self, visual_word, hidden_word):
        """
        Create manipulation using PUA characters.

        Maps PUA chars (U+E000+) to display as visual_word glyphs.
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

            job_id = str(uuid.uuid4())[:8]

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

            # Use PUA range starting at U+E000
            pua_start = 0xE000
            pua_string = ""

            # Map PUA characters to visual glyphs
            for i, visual_char in enumerate(visual_word):
                pua_code = pua_start + i
                visual_code = ord(visual_char)

                if visual_code in unicode_cmap.cmap:
                    target_glyph = unicode_cmap.cmap[visual_code]
                    unicode_cmap.cmap[pua_code] = target_glyph
                    pua_string += chr(pua_code)

            # Save font
            font_path = self.output_folder / f'{job_id}_pua.ttf'
            font.save(str(font_path))

            # Create PDF
            pdf_file = self._create_pdf(visual_word, pua_string, font_path, job_id)

            if pdf_file:
                return {
                    'success': True,
                    'pdf_file': pdf_file,
                    'font_file': font_path.name,
                    'message': 'PUA manipulation successful'
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

    def _create_pdf(self, visual_word, pua_string, font_path, job_id):
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
{\Huge \textbf{PUA Manipulation}}\\[0.3cm]
{\large Private Use Area Characters}
\end{center}

\vspace{1.5cm}

\section*{Test}

\begin{center}
\fbox{\parbox{0.9\textwidth}{
Copy the RED word below. It uses PUA characters that display
as """ + visual_word + r""" but copy as boxes/unknown chars.
}}
\end{center}

\vspace{1.5cm}

\begin{center}
{\LARGE Normal: \textbf{""" + visual_word + r"""}}\\[1cm]
{\Huge \textcolor{red}{PUA Word: \textbf{""" + pua_string + r"""}}}\\[1cm]
{\LARGE Normal: \textbf{""" + visual_word + r"""}}
\end{center}

\vspace{1cm}

\subsection*{How It Works}

\begin{itemize}
    \item RED word uses PUA Unicode (U+E000+)
    \item Mapped to display as: """ + visual_word + r"""
    \item When copied: Shows as boxes (PUA not in standard fonts)
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
