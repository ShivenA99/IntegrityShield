"""
Truly Selective Manipulation V3
Uses OpenType contextual alternates to handle cases where same character needs different visuals
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
from fontTools.feaLib.builder import addOpenTypeFeatures

class TrulySelectiveManipulatorV3:
    def __init__(self, fonts_folder, output_folder):
        self.fonts_folder = Path(fonts_folder)
        self.output_folder = Path(output_folder)
        self.base_font = self.fonts_folder / 'Roboto.ttf'

    def create_manipulation(self, visual_word, hidden_word):
        """
        Create truly selective manipulation using contextual alternates.

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
                f"Hidden word: {hidden_word}",
                f"Method: Contextual Alternates (V3)"
            ]

            # Create two fonts
            normal_font_path = self.output_folder / f'{job_id}_normal.ttf'
            deceptive_font_path = self.output_folder / f'{job_id}_deceptive_v3.ttf'

            # Load base font and, if variable, instantiate it to a static face
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

            # Access glyph and metrics tables
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

            # Validate all characters exist
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

            log_entries.append("Creating alternate glyphs for contextual substitution:")

            # Track which character positions need alternates
            char_positions = {}
            for idx, (hidden_char, visual_char) in enumerate(zip(hidden_word, visual_word)):
                if hidden_char not in char_positions:
                    char_positions[hidden_char] = []
                char_positions[hidden_char].append((idx, visual_char))

            # Create alternate glyphs for positions that need them
            alternate_glyphs = {}  # Maps (hidden_char, position) -> alternate_glyph_name

            for hidden_char, positions in char_positions.items():
                hidden_glyph_name = cmap.get(ord(hidden_char))

                for idx, (pos, visual_char) in enumerate(positions):
                    visual_glyph_name = cmap.get(ord(visual_char))

                    if hidden_glyph_name == visual_glyph_name:
                        # Same glyph, no alternate needed
                        log_entries.append(f"  Position {pos}: '{hidden_char}' = '{visual_char}' (same glyph, no alternate)")
                        continue

                    # Create alternate glyph name
                    alt_suffix = f".alt{pos}"
                    alt_glyph_name = hidden_glyph_name + alt_suffix

                    # Clone the visual glyph to create the alternate
                    pen = TTGlyphPen(glyph_set)
                    glyph_set[visual_glyph_name].draw(pen)
                    new_glyph = pen.glyph()

                    # Preserve hinting if present
                    visual_tt_glyph = font['glyf'][visual_glyph_name]
                    if hasattr(visual_tt_glyph, "program") and visual_tt_glyph.program:
                        new_glyph.program = visual_tt_glyph.program

                    # Add to glyf table
                    glyf_table[alt_glyph_name] = new_glyph

                    # Copy metrics
                    if visual_glyph_name in font['hmtx'].metrics:
                        hmtx_table.metrics[alt_glyph_name] = font['hmtx'].metrics[visual_glyph_name]

                    # Add to glyph order
                    glyph_order = list(font.getGlyphOrder())
                    if alt_glyph_name not in glyph_order:
                        glyph_order.append(alt_glyph_name)
                        font.setGlyphOrder(glyph_order)

                    alternate_glyphs[(hidden_char, pos)] = alt_glyph_name

                    log_entries.append(
                        f"  Position {pos}: '{hidden_char}' → '{visual_char}' (created {alt_glyph_name})"
                    )

            # Build contextual substitution feature
            if alternate_glyphs:
                fea_code = self._build_calt_feature(hidden_word, visual_word, cmap, alternate_glyphs, log_entries)

                # Add the feature to the font using a temporary file
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.fea', delete=False) as fea_file:
                        fea_file.write(fea_code)
                        fea_path = fea_file.name

                    addOpenTypeFeatures(font, fea_path)
                    os.unlink(fea_path)  # Clean up temp file
                    log_entries.append("Successfully added OpenType calt feature")
                except Exception as e:
                    log_entries.append(f"Warning: Failed to add calt feature: {e}")
                    # Continue anyway - the alternates are in the font even if feature fails

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
                    'message': 'Selective manipulation successful (V3 with contextual alternates)'
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

    def _build_calt_feature(self, hidden_word, visual_word, cmap, alternate_glyphs, log_entries):
        """Build OpenType calt feature code for contextual substitution."""

        # Build context-sensitive substitution rules
        # We need to substitute based on position in the specific sequence

        fea_lines = [
            "languagesystem DFLT dflt;",
            "languagesystem latn dflt;",
            "",
            "feature calt {",
        ]

        # Build a lookup for the entire word context
        # For each position, if we have an alternate, create a contextual rule

        for pos, (hidden_char, visual_char) in enumerate(zip(hidden_word, visual_word)):
            if (hidden_char, pos) in alternate_glyphs:
                hidden_glyph = cmap[ord(hidden_char)]
                alt_glyph = alternate_glyphs[(hidden_char, pos)]

                # Build context: what comes before and after
                context_before = []
                context_after = []

                for i in range(pos):
                    ctx_char = hidden_word[i]
                    ctx_glyph = cmap[ord(ctx_char)]
                    # Check if this position has an alternate
                    if (ctx_char, i) in alternate_glyphs:
                        ctx_glyph = alternate_glyphs[(ctx_char, i)]
                    context_before.append(ctx_glyph)

                for i in range(pos + 1, len(hidden_word)):
                    ctx_char = hidden_word[i]
                    ctx_glyph = cmap[ord(ctx_char)]
                    context_after.append(ctx_glyph)

                # Build the substitution rule
                rule_parts = []
                if context_before:
                    rule_parts.append(' '.join(context_before))
                rule_parts.append(f"{hidden_glyph}' by {alt_glyph}")
                if context_after:
                    rule_parts.append(' '.join(context_after))

                rule = "  sub " + ' '.join(rule_parts) + ";"
                fea_lines.append(rule)
                log_entries.append(f"  CALT rule: {rule}")

        fea_lines.append("} calt;")
        fea_lines.append("")

        fea_code = '\n'.join(fea_lines)
        log_entries.append(f"Generated feature code:\n{fea_code}")

        return fea_code

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
    Extension = .ttf,
    Contextuals = Alternate
]

\begin{document}

\begin{center}
{\Huge \textbf{Font Manipulation Demo V3}}\\[0.3cm]
{\large Contextual Alternates for Same-Character Mapping}
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
    \item Second (RED): DECEPTIVE with contextual alternates
    \item Third: NORMAL
    \item Copy the RED word - it should copy as """ + hidden_word + r""" but look like """ + visual_word + r"""
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
    \item Mode: V3 - Contextual Alternates (calt)
    \item Handles same character with different visuals
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