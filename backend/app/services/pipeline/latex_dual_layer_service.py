from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import fitz

from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...utils.logging import get_logger
from ...utils.storage_paths import artifacts_root, enhanced_pdf_path, run_directory
from ...utils.time import isoformat, utc_now


@dataclass
class MappingDiagnostic:
    question_number: str
    question_id: Optional[str]
    mapping_id: Optional[str]
    original: str
    replacement: str
    status: str
    matched_fragment: Optional[str] = None
    start_index: Optional[int] = None
    end_index: Optional[int] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    notes: Optional[str] = None


@dataclass
class CompilePass:
    number: int
    return_code: int
    duration_ms: float
    log_length: int


@dataclass
class CompileSummary:
    success: bool
    duration_ms: float
    passes: List[CompilePass] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class OverlaySummary:
    success: bool
    overlays: int
    pages_processed: int
    per_page: List[Dict[str, Any]] = field(default_factory=list)
    method: str = "full_page_overlay"


class LatexAttackService:
    """Applies substring mappings directly to the manual LaTeX source and prepares artifacts."""

    MACRO_DEFINITION = r"""
% --- latex-dual-layer macros (auto-generated) ---
\newlength{\dlboxwidth}
\newlength{\dlboxheight}
\newlength{\dlboxdepth}
\newcommand{\duallayerbox}[2]{%
  \begingroup
  \settowidth{\dlboxwidth}{\strut #1}%
  \settoheight{\dlboxheight}{\strut #1}%
  \settodepth{\dlboxdepth}{\strut #1}%
  \ifdim\dlboxwidth=0pt
    \settowidth{\dlboxwidth}{#2}%
  \fi
  \raisebox{0pt}[\dlboxheight][\dlboxdepth]{%
    \makebox[\dlboxwidth][l]{\resizebox{\dlboxwidth}{!}{\strut #2}}%
  }%
  \endgroup
}

\newenvironment{dlEnumerateArabic}{%
  \begingroup
  \begin{enumerate}
}{%
  \end{enumerate}
  \endgroup
}

\newenvironment{dlEnumerateAlpha}{%
  \begingroup
  \renewcommand{\labelenumi}{(\alph{enumi})}%
  \begin{enumerate}
}{%
  \end{enumerate}
  \endgroup
}
% --- end latex-dual-layer macros ---
""".strip()

    PACKAGE_DEPENDENCIES: Tuple[str, ...] = ("graphicx", "calc", "xcolor")

    _BLANK_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0c"
        b"IDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xefF\xb8\x00\x00\x00"
        b"\x00IEND\xaeB`\x82"
    )

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self.structured_manager = StructuredDataManager()

    def execute(self, run_id: str, *, force: bool = False) -> Dict[str, Any]:
        structured = self.structured_manager.load(run_id) or {}
        manual_meta = structured.get("manual_input") or {}
        document_meta = structured.get("document") or {}

        tex_path_str = manual_meta.get("tex_path") or document_meta.get("latex_path")
        if not tex_path_str:
            raise ValueError("Manual LaTeX path not present in structured data")

        tex_path = Path(tex_path_str)
        if not tex_path.exists():
            raise FileNotFoundError(f"Manual LaTeX source not found at {tex_path}")

        artifacts_dir = artifacts_root(run_id) / "latex-dual-layer"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = artifacts_dir / "metadata.json"

        questions = self._load_questions(run_id)
        mapping_signature = self._build_mapping_signature(questions)

        if metadata_path.exists() and not force:
            cached = json.loads(metadata_path.read_text(encoding="utf-8"))
            cached_signature = cached.get("mapping_signature") or []
            if cached_signature == mapping_signature:
                cached["cached"] = True
                cached.setdefault("artifacts", {})
                return cached

        try:
            original_tex = tex_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            original_tex = tex_path.read_text(encoding="latin-1")

        base_tex = self._preprocess_source(original_tex)
        mutated_tex, diagnostics = self._apply_mappings(base_tex, questions)
        mutated_tex = self._apply_enumerate_fallbacks(mutated_tex)
        mutated_tex = self._ensure_macros(mutated_tex)

        attacked_tex_path = artifacts_dir / "latex_dual_layer_attacked.tex"
        attacked_tex_path.write_text(mutated_tex, encoding="utf-8")
        self._prepare_graphics_assets(tex_path, artifacts_dir, mutated_tex)

        diagnostics_payload = {
            "run_id": run_id,
            "generated_at": isoformat(utc_now()),
            "replacements": [asdict(entry) for entry in diagnostics],
            "replacement_summary": self._summarize_replacements(diagnostics),
        }
        diagnostics_path = artifacts_dir / "latex_dual_layer_log.json"
        diagnostics_path.write_text(json.dumps(diagnostics_payload, indent=2), encoding="utf-8")

        compile_log_path = artifacts_dir / "latex_dual_layer_compile.log"
        compiled_pdf_path = artifacts_dir / "latex_dual_layer_attacked.pdf"
        final_pdf_path = artifacts_dir / "latex_dual_layer_final.pdf"

        compile_summary = self._compile_latex(
            tex_source_path=tex_path,
            mutated_tex_path=attacked_tex_path,
            output_pdf_path=compiled_pdf_path,
            log_path=compile_log_path,
        )

        overlay_summary: OverlaySummary
        if not compile_summary.success or not compiled_pdf_path.exists():
            overlay_summary = OverlaySummary(
                success=False,
                overlays=0,
                pages_processed=0,
                per_page=[],
            )
            final_pdf_path.unlink(missing_ok=True)
        else:
            source_pdf_path = self._resolve_original_pdf_path(manual_meta, document_meta)
            overlay_summary = self._overlay_pdfs(
                original_pdf_path=source_pdf_path,
                compiled_pdf_path=compiled_pdf_path,
                final_pdf_path=final_pdf_path,
            )

        enhanced_pdf = enhanced_pdf_path(run_id, "latex_dual_layer")
        enhanced_pdf.parent.mkdir(parents=True, exist_ok=True)
        if final_pdf_path.exists():
            shutil.copy2(final_pdf_path, enhanced_pdf)
        else:
            enhanced_pdf.write_bytes(b"")

        replacement_summary = diagnostics_payload["replacement_summary"]
        render_metadata = self._update_structured_data(
            run_id=run_id,
            structured=structured,
            attacked_tex_path=attacked_tex_path,
            compiled_pdf_path=compiled_pdf_path if compiled_pdf_path.exists() else None,
            final_pdf_path=final_pdf_path if final_pdf_path.exists() else None,
            enhanced_pdf_path=enhanced_pdf,
            compile_log_path=compile_log_path,
            diagnostics_path=diagnostics_path,
            replacement_summary=replacement_summary,
            compile_summary=compile_summary,
            overlay_summary=overlay_summary,
        )

        result_payload = {
            "run_id": run_id,
            "generated_at": isoformat(utc_now()),
            "artifacts": {
                "attacked_tex": str(attacked_tex_path),
                "compiled_pdf": str(compiled_pdf_path) if compiled_pdf_path.exists() else None,
                "final_pdf": str(final_pdf_path) if final_pdf_path.exists() else None,
                "compile_log": str(compile_log_path),
                "diagnostics": str(diagnostics_path),
                "enhanced_pdf": str(enhanced_pdf),
            },
            "replacement_summary": replacement_summary,
            "compile_summary": {
                "success": compile_summary.success,
                "duration_ms": round(compile_summary.duration_ms, 2),
                "error": compile_summary.error,
                "passes": [asdict(pass_summary) for pass_summary in compile_summary.passes],
            },
            "overlay_summary": {
                "success": overlay_summary.success,
                "overlays": overlay_summary.overlays,
                "pages_processed": overlay_summary.pages_processed,
                "method": overlay_summary.method,
                "per_page": overlay_summary.per_page,
            },
            "question_diagnostics": diagnostics_payload["replacements"],
            "renderer_metadata": render_metadata,
            "mapping_signature": mapping_signature,
        }

        metadata_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

        return result_payload

    # ------------------------------------------------------------------
    # Replacement pipeline
    # ------------------------------------------------------------------
    def _load_questions(self, run_id: str) -> List[QuestionManipulation]:
        """Load questions from database, always using structured.json as source of truth for substring_mappings."""
        questions = (
            QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
            .order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
            .all()
        )
        
        # Always load substring_mappings from structured.json as the source of truth
        structured = self.structured_manager.load(run_id) or {}
        structured_questions = structured.get("questions", [])
        
        structured_map_by_id = {
            entry.get("manipulation_id"): entry for entry in structured_questions if entry.get("manipulation_id") is not None
        }
        structured_map_by_seq = {
            entry.get("sequence_index"): entry for entry in structured_questions if entry.get("sequence_index") is not None
        }
        structured_map_by_number = {
            str(entry.get("question_number") or entry.get("q_number") or ""): entry for entry in structured_questions
        }
        
        # Merge substring_mappings from structured.json into database questions
        # Use structured.json as source of truth - if mappings exist there, use them
        for question in questions:
            structured_q = (
                structured_map_by_id.get(question.id)
                or structured_map_by_seq.get(getattr(question, "sequence_index", None))
                or structured_map_by_number.get(str(question.question_number or ""))
            )
            
            if structured_q:
                manipulation = structured_q.get("manipulation", {})
                mappings = manipulation.get("substring_mappings", [])
                
                # Always use mappings from structured.json if they exist
                if mappings:
                    # Convert to JSON-safe format and assign to question
                    json_safe_mappings = json.loads(json.dumps(mappings))
                    question.substring_mappings = json_safe_mappings
                    self.logger.info(
                        f"Loaded {len(json_safe_mappings)} substring_mappings from structured.json for question {question.id}",
                        extra={
                            "run_id": run_id,
                            "question_id": question.id,
                            "question_number": question.question_number,
                        },
                    )
        
        return questions

    def _preprocess_source(self, tex_content: str) -> str:
        pattern = re.compile(r"\\usepackage\{enumitem\}\s*")
        return pattern.sub("", tex_content)

    def _apply_mappings(
        self,
        tex_content: str,
        questions: Iterable[QuestionManipulation],
    ) -> Tuple[str, List[MappingDiagnostic]]:
        diagnostics: List[MappingDiagnostic] = []

        segments = self._build_question_segments(tex_content)
        sorted_questions = sorted(
            questions,
            key=lambda q: (getattr(q, "sequence_index", 0), q.id or 0),
        )

        if not segments or len(segments) != len(sorted_questions):
            self.logger.warning(
                "latex-dual-layer: question segmentation mismatch (segments=%s, questions=%s); falling back to global replacement",
                len(segments),
                len(sorted_questions),
            )
            return self._apply_mappings_global(tex_content, sorted_questions)

        new_content_parts: List[str] = []
        last_index = 0

        for question, (seg_start, seg_end) in zip(sorted_questions, segments):
            seg_start = max(seg_start, last_index)
            segment_text = tex_content[seg_start:seg_end]

            updated_segment, segment_diags = self._apply_mappings_for_segment(
                question,
                segment_text,
                seg_start,
                tex_content,
            )

            if seg_start > last_index:
                new_content_parts.append(tex_content[last_index:seg_start])
            new_content_parts.append(updated_segment)
            diagnostics.extend(segment_diags)
            last_index = seg_end

        if last_index < len(tex_content):
            new_content_parts.append(tex_content[last_index:])

        mutated = "".join(new_content_parts)
        return mutated, diagnostics

    def _apply_mappings_for_segment(
        self,
        question: Any,
        segment_text: str,
        segment_start: int,
        full_text: str,
    ) -> Tuple[str, List[MappingDiagnostic]]:
        updated_segment = segment_text
        diagnostics: List[MappingDiagnostic] = []

        metadata = (getattr(question, "ai_model_results", {}) or {}).get("manual_seed", {}) if hasattr(question, "ai_model_results") else {}
        question_id = metadata.get("question_id") if isinstance(metadata, dict) else None
        if not question_id:
            question_id = getattr(question, "id", None)
        q_number = str(getattr(question, "question_number", None) or getattr(question, "id", ""))

        base_line_offset = full_text.count("\n", 0, segment_start)
        mappings = list(getattr(question, "substring_mappings", []) or [])
        occupied: List[Tuple[int, int]] = []

        if not mappings:
            diagnostics.append(
                MappingDiagnostic(
                    question_number=q_number,
                    question_id=question_id,
                    mapping_id=None,
                    original="",
                    replacement="",
                    status="no_mapping",
                    notes="No validated mapping available for this question",
                )
            )
            return segment_text, diagnostics

        for mapping in mappings:
            original_raw = str((mapping or {}).get("original") or "").strip()
            replacement_raw = str((mapping or {}).get("replacement") or "").strip()
            if not original_raw or not replacement_raw:
                continue

            diagnostic = MappingDiagnostic(
                question_number=q_number,
                question_id=question_id,
                mapping_id=(mapping or {}).get("id"),
                original=original_raw,
                replacement=replacement_raw,
                status="not_processed",
                notes=(mapping or {}).get("notes"),
            )

            # Try positional matching first if available
            latex_stem_text = (mapping or {}).get("latex_stem_text")
            start_pos = (mapping or {}).get("start_pos")
            end_pos = (mapping or {}).get("end_pos")
            
            local_match = None
            if latex_stem_text and start_pos is not None and end_pos is not None:
                # Use positional information
                local_match = self._locate_substring_by_position(
                    tex_content=updated_segment,
                    latex_stem_text=latex_stem_text,
                    original=original_raw,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    occupied=occupied
                )
            
            # Fallback to string search if positional matching fails
            if not local_match:
                local_match = self._locate_fragment(updated_segment, original_raw, occupied)
            
            if not local_match:
                diagnostic.status = "not_found"
                diagnostics.append(diagnostic)
                continue

            local_start, local_end = local_match
            fragment = updated_segment[local_start:local_end]
            replacement_fragment = self._format_replacement(fragment, replacement_raw)

            updated_segment = (
                updated_segment[:local_start]
                + replacement_fragment
                + updated_segment[local_end:]
            )

            absolute_start = segment_start + local_start
            absolute_end = segment_start + local_end
            
            # Add to occupied ranges
            occupied.append((local_start, local_end))

            diagnostic.status = "replaced"
            diagnostic.matched_fragment = fragment
            diagnostic.start_index = absolute_start
            diagnostic.end_index = absolute_end
            diagnostic.start_line = base_line_offset + segment_text.count("\n", 0, local_start) + 1
            diagnostic.end_line = base_line_offset + segment_text.count("\n", 0, local_end) + 1

            diagnostics.append(diagnostic)

        return updated_segment, diagnostics

    def _apply_mappings_global(
        self,
        tex_content: str,
        questions: Iterable[Any],
    ) -> Tuple[str, List[MappingDiagnostic]]:
        diagnostics: List[MappingDiagnostic] = []
        replacements: List[Tuple[int, int, str, MappingDiagnostic]] = []
        occupied: List[Tuple[int, int]] = []

        for question in questions:
            metadata = (getattr(question, "ai_model_results", {}) or {}).get("manual_seed", {}) if hasattr(question, "ai_model_results") else {}
            question_id = metadata.get("question_id") if isinstance(metadata, dict) else None
            q_number = str(getattr(question, "question_number", None) or getattr(question, "id", ""))

            for mapping in list(getattr(question, "substring_mappings", []) or []):
                original_raw = str((mapping or {}).get("original") or "").strip()
                replacement_raw = str((mapping or {}).get("replacement") or "").strip()
                if not original_raw or not replacement_raw:
                    continue

                diagnostic = MappingDiagnostic(
                    question_number=q_number,
                    question_id=question_id,
                    mapping_id=(mapping or {}).get("id"),
                    original=original_raw,
                    replacement=replacement_raw,
                    status="not_processed",
                    notes=(mapping or {}).get("notes"),
                )

                match = self._locate_fragment(tex_content, original_raw, occupied)
                if not match:
                    diagnostic.status = "not_found"
                    diagnostics.append(diagnostic)
                    continue

                start_idx, end_idx = match
                fragment = tex_content[start_idx:end_idx]
                replacement_fragment = self._format_replacement(fragment, replacement_raw)

                diagnostic.status = "replaced"
                diagnostic.matched_fragment = fragment
                diagnostic.start_index = start_idx
                diagnostic.end_index = end_idx
                diagnostic.start_line = tex_content.count("\n", 0, start_idx) + 1
                diagnostic.end_line = tex_content.count("\n", 0, end_idx) + 1

                replacements.append((start_idx, end_idx, replacement_fragment, diagnostic))
                occupied.append((start_idx, end_idx))

        mutated = tex_content
        for start_idx, end_idx, replacement_fragment, diagnostic in sorted(
            replacements, key=lambda item: item[0], reverse=True
        ):
            mutated = mutated[:start_idx] + replacement_fragment + mutated[end_idx:]
            diagnostics.append(diagnostic)

        return mutated, diagnostics

    def _build_question_segments(self, content: str) -> List[Tuple[int, int]]:
        return self._compute_top_level_item_spans(content)

    def _compute_top_level_item_spans(self, content: str) -> List[Tuple[int, int]]:
        if not content:
            return []

        token_pattern = re.compile(
            r"\\begin\{(?:dlEnumerateAlpha|dlEnumerateArabic|enumerate)\}(?:\[[^\]]*\])?"
            r"|\\end\{(?:dlEnumerateAlpha|dlEnumerateArabic|enumerate)\}"
            r"|\\item\b"
        )

        level = 0
        segments: List[Tuple[int, int]] = []
        current_start: Optional[int] = None

        for match in token_pattern.finditer(content):
            token = match.group()
            if token.startswith("\\begin"):
                level += 1
                continue

            if token.startswith("\\end"):
                if level == 1 and current_start is not None:
                    segments.append((current_start, match.start()))
                    current_start = None
                level = max(0, level - 1)
                continue

            if level == 1:
                if current_start is not None:
                    segments.append((current_start, match.start()))
                current_start = match.start()

        if current_start is not None:
            segments.append((current_start, len(content)))

        segments.sort(key=lambda pair: pair[0])
        return segments
    def _apply_enumerate_fallbacks(self, content: str) -> str:
        pattern_alpha = re.compile(
            r"\\begin{enumerate}\[label=\(\\alph\*\)\](.*?)\\end{enumerate}",
            flags=re.DOTALL,
        )
        pattern_arabic = re.compile(
            r"\\begin{enumerate}\[label=\\arabic\*\.\](.*?)\\end{enumerate}",
            flags=re.DOTALL,
        )

        def substitute(pattern: re.Pattern[str], begin: str, end: str, text: str) -> str:
            while True:
                text, count = pattern.subn(
                    lambda match: f"{begin}{match.group(1)}{end}",
                    text,
                )
                if count == 0:
                    break
            return text

        converted = substitute(pattern_alpha, "\\begin{dlEnumerateAlpha}", "\\end{dlEnumerateAlpha}", content)
        converted = substitute(pattern_arabic, "\\begin{dlEnumerateArabic}", "\\end{dlEnumerateArabic}", converted)
        converted = self._rewrite_plain_enumerates(converted)
        return converted

    def _rewrite_plain_enumerates(self, content: str) -> str:
        """
        Replace bare enumerate environments with dual-layer aware variants.
        Top-level enumerate blocks become dlEnumerateArabic; nested blocks become dlEnumerateAlpha.
        """
        token_pattern = re.compile(
            r"\\begin\{([^\}]+)\}(?:\[[^\]]*\])?"
            r"|\\end\{([^\}]+)\}"
        )

        enumerate_envs = {"enumerate", "dlEnumerateAlpha", "dlEnumerateArabic"}
        replacements: List[Tuple[int, int, str]] = []
        conversion_stack: List[str] = []

        for match in token_pattern.finditer(content):
            begin_env, end_env = match.groups()
            if begin_env:
                env_name = begin_env
                if env_name not in enumerate_envs:
                    continue

                if env_name == "enumerate":
                    depth = len(conversion_stack)
                    replacement_env = "dlEnumerateArabic" if depth == 0 else "dlEnumerateAlpha"
                    replacements.append(
                        (match.start(), match.end(), f"\\begin{{{replacement_env}}}")
                    )
                    conversion_stack.append(replacement_env)
                else:
                    conversion_stack.append(env_name)
            else:
                env_name = end_env or ""
                if env_name not in enumerate_envs:
                    continue

                if env_name == "enumerate":
                    replacement_env = conversion_stack.pop() if conversion_stack else "dlEnumerateAlpha"
                    replacements.append(
                        (match.start(), match.end(), f"\\end{{{replacement_env}}}")
                    )
                else:
                    if conversion_stack:
                        conversion_stack.pop()

        if not replacements:
            return content

        parts: List[str] = []
        last_index = 0
        for start, end, replacement in sorted(replacements, key=lambda item: item[0]):
            parts.append(content[last_index:start])
            parts.append(replacement)
            last_index = end

        parts.append(content[last_index:])
        return "".join(parts)

    def _locate_fragment(
        self,
        tex_content: str,
        original: str,
        occupied: List[Tuple[int, int]],
    ) -> Optional[Tuple[int, int]]:
        pattern = self._build_relaxed_pattern(original)
        for match in pattern.finditer(tex_content):
            candidate = (match.start(), match.end())
            prefix_start = max(0, candidate[0] - 20)
            prefix = tex_content[prefix_start:candidate[0]]
            if "\\duallayerbox{" in prefix:
                continue
            if self._range_available(candidate, occupied):
                return candidate
        return None
    
    def _locate_substring_by_position(
        self,
        tex_content: str,
        latex_stem_text: str,
        original: str,
        start_pos: int,
        end_pos: int,
        occupied: List[Tuple[int, int]] = None
    ) -> Optional[Tuple[int, int]]:
        """
        Locate substring in LaTeX using positional information.
        
        Args:
            tex_content: LaTeX content to search in
            latex_stem_text: Exact LaTeX stem text from mapping
            original: Original substring to find
            start_pos: Start position relative to latex_stem_text
            end_pos: End position relative to latex_stem_text
            occupied: List of occupied ranges to skip
            
        Returns:
            (start_index, end_index) tuple or None if not found
        """
        if occupied is None:
            occupied = []
        
        # Find latex_stem_text in tex_content
        stem_start = tex_content.find(latex_stem_text)
        if stem_start == -1:
            # Try normalized search (remove LaTeX commands)
            normalized_stem = self._normalize_latex_text(latex_stem_text)
            normalized_content = self._normalize_latex_text(tex_content)
            stem_start = normalized_content.find(normalized_stem)
            if stem_start != -1:
                # Map back to original positions (approximate)
                # This is a fallback - ideally latex_stem_text should match exactly
                stem_start = tex_content.find(latex_stem_text[:50])  # Try first 50 chars
                if stem_start == -1:
                    return None
        
        if stem_start == -1:
            return None
        
        # Calculate absolute positions
        absolute_start = stem_start + start_pos
        absolute_end = stem_start + end_pos
        
        # Verify positions are valid
        if absolute_start < 0 or absolute_end > len(tex_content) or absolute_start >= absolute_end:
            return None
        
        # Verify substring matches
        actual_substring = tex_content[absolute_start:absolute_end]
        if actual_substring != original:
            # Try to find original in the vicinity
            search_start = max(0, absolute_start - 50)
            search_end = min(len(tex_content), absolute_end + 50)
            search_area = tex_content[search_start:search_end]
            original_pos = search_area.find(original)
            if original_pos != -1:
                absolute_start = search_start + original_pos
                absolute_end = absolute_start + len(original)
            else:
                return None
        
        # Check if range is occupied
        candidate = (absolute_start, absolute_end)
        if not self._range_available(candidate, occupied):
            return None
        
        # Check if inside \duallayerbox{}
        prefix_start = max(0, absolute_start - 20)
        prefix = tex_content[prefix_start:absolute_start]
        if "\\duallayerbox{" in prefix:
            return None
        
        return candidate
    
    def _normalize_latex_text(self, text: str) -> str:
        """Normalize LaTeX text for comparison (remove commands, normalize whitespace)."""
        normalized = text
        # Remove common LaTeX commands
        normalized = re.sub(r"\\textbf\{([^}]*)\}", r"\1", normalized)
        normalized = re.sub(r"\\textit\{([^}]*)\}", r"\1", normalized)
        normalized = re.sub(r"\\emph\{([^}]*)\}", r"\1", normalized)
        normalized = re.sub(r"\\text\{([^}]*)\}", r"\1", normalized)
        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _build_mapping_signature(
        self, questions: Iterable[QuestionManipulation]
    ) -> List[str]:
        signature: List[str] = []
        for question in questions:
            label = str(getattr(question, "question_number", question.id))
            for mapping in list(question.substring_mappings or []):
                start = mapping.get("start_pos")
                end = mapping.get("end_pos")
                signature.append(
                    "|".join(
                        [
                            label,
                            str(mapping.get("original") or "").strip(),
                            str(mapping.get("replacement") or "").strip(),
                            str(start) if start is not None else "",
                            str(end) if end is not None else "",
                        ]
                    )
                )
        signature.sort()
        return signature

    def _prepare_graphics_assets(self, tex_path: Path, artifacts_dir: Path, latex_content: str) -> None:
        asset_directories = self._extract_graphic_paths(latex_content)
        filenames = self._extract_graphic_filenames(latex_content)
        if not asset_directories:
            asset_directories = [""]

        tex_root = tex_path.parent.resolve()

        for asset_dir in asset_directories:
            normalized_dir = self._normalize_graphic_path(asset_dir)
            if normalized_dir is None:
                continue
            root_target_dir = (
                (tex_root / normalized_dir).resolve()
                if normalized_dir != Path(".")
                else tex_root
            )
            artifact_target_dir = (
                (artifacts_dir / normalized_dir).resolve()
                if normalized_dir != Path(".")
                else artifacts_dir
            )
            root_target_dir.mkdir(parents=True, exist_ok=True)
            artifact_target_dir.mkdir(parents=True, exist_ok=True)

        for filename in filenames:
            for asset_dir in asset_directories or [""]:
                normalized_dir = self._normalize_graphic_path(asset_dir)
                if normalized_dir is None:
                    continue

                root_target = (
                    (tex_root / normalized_dir / filename).resolve()
                    if normalized_dir != Path(".")
                    else (tex_root / filename).resolve()
                )
                artifact_target = (
                    (artifacts_dir / normalized_dir / filename).resolve()
                    if normalized_dir != Path(".")
                    else (artifacts_dir / filename).resolve()
                )

                root_target.parent.mkdir(parents=True, exist_ok=True)

                needs_placeholder = True
                if root_target.exists():
                    try:
                        if root_target.stat().st_size > len(self._BLANK_PNG):
                            needs_placeholder = False
                    except OSError:
                        needs_placeholder = True

                if needs_placeholder:
                    if filename.lower().endswith(".png"):
                        root_target.write_bytes(self._BLANK_PNG)
                    else:
                        root_target.write_bytes(b"")

                if artifact_target != root_target:
                    artifact_target.parent.mkdir(parents=True, exist_ok=True)
                    copy_required = True
                    if artifact_target.exists():
                        try:
                            if artifact_target.stat().st_size > len(self._BLANK_PNG):
                                copy_required = False
                        except OSError:
                            copy_required = True
                    if copy_required:
                        try:
                            shutil.copy2(root_target, artifact_target)
                        except Exception:
                            if filename.lower().endswith(".png"):
                                artifact_target.write_bytes(self._BLANK_PNG)
                            else:
                                artifact_target.write_bytes(b"")

    def _extract_graphic_paths(self, latex_content: str) -> List[str]:
        pattern = re.compile(r"\\graphicspath\{\{([^}]*)\}\}")
        matches = pattern.findall(latex_content)
        paths: List[str] = []
        for match in matches:
            for candidate in match.split("}{"):
                cleaned = candidate.strip()
                if cleaned:
                    paths.append(cleaned)
        return paths

    def _extract_graphic_filenames(self, latex_content: str) -> List[str]:
        pattern = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
        files = pattern.findall(latex_content)
        unique = {entry.strip() for entry in files if entry.strip()}
        return sorted(unique)

    def _normalize_graphic_path(self, path_str: str) -> Optional[Path]:
        normalized = (path_str or "").strip()
        if not normalized:
            return Path(".")
        normalized = normalized.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized.startswith("/"):
            return None
        return Path(normalized.rstrip("/"))

    def _build_relaxed_pattern(self, text: str) -> re.Pattern[str]:
        tokens = re.split(r"(\\s+)", text)
        pieces: List[str] = []
        for token in tokens:
            if not token:
                continue
            if token.isspace():
                pieces.append(r"\\s+")
            else:
                pieces.append(re.escape(token))
        pattern = "".join(pieces) or re.escape(text)
        return re.compile(pattern, flags=re.MULTILINE | re.DOTALL)

    def _range_available(
        self, candidate: Tuple[int, int], occupied: List[Tuple[int, int]]
    ) -> bool:
        candidate_start, candidate_end = candidate
        for start, end in occupied:
            if start <= candidate_start < end or start < candidate_end <= end:
                return False
        return True

    def _format_replacement(self, original_fragment: str, replacement_text: str) -> str:
        escaped_replacement = self._escape_replacement_text(replacement_text)
        return f"\\duallayerbox{{{original_fragment}}}{{{escaped_replacement}}}"

    def _escape_replacement_text(self, value: str) -> str:
        mapping = {
            "\\": r"\textbackslash{}",
            "{": r"\{",
            "}": r"\}",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "&": r"\&",
            "_": r"\_",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }
        escaped: List[str] = []
        for char in value:
            escaped.append(mapping.get(char, char))
        return "".join(escaped)

    def _ensure_macros(self, content: str) -> str:
        updated = content
        for package in self.PACKAGE_DEPENDENCIES:
            updated = self._ensure_package(updated, package)
        if "\\newcommand{\\duallayerbox}" in updated:
            return updated
        begin_document = "\\begin{document}"
        insertion = "\n" + self.MACRO_DEFINITION + "\n"
        if begin_document in updated:
            return updated.replace(begin_document, f"{insertion}{begin_document}", 1)
        return updated + insertion

    def _ensure_package(self, content: str, package: str) -> str:
        pattern = re.compile(rf"\\usepackage(?:\[[^]]*\])?\{{{re.escape(package)}\}}")
        if pattern.search(content):
            return content
        documentclass_pattern = re.compile(r"\\documentclass[^\n]*\n")
        match = documentclass_pattern.search(content)
        insertion = f"\\usepackage{{{package}}}\n"
        if match:
            insert_at = match.end()
            return content[:insert_at] + insertion + content[insert_at:]
        return insertion + content

    # ------------------------------------------------------------------
    # Compilation & overlay
    # ------------------------------------------------------------------
    def _compile_latex(
        self,
        tex_source_path: Path,
        mutated_tex_path: Path,
        output_pdf_path: Path,
        log_path: Path,
    ) -> CompileSummary:
        work_start = time.time()
        timeout = self._compile_timeout()
        passes: List[CompilePass] = []
        log_chunks: List[str] = []
        error_message: Optional[str] = None
        success = True

        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir) / "src"
            work_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(tex_source_path.parent, work_dir, dirs_exist_ok=True)
            temp_tex = work_dir / tex_source_path.name
            temp_tex.write_text(mutated_tex_path.read_text(encoding="utf-8"), encoding="utf-8")

            for artifact_item in mutated_tex_path.parent.iterdir():
                if artifact_item.name == mutated_tex_path.name:
                    continue
                target_item = work_dir / artifact_item.name
                try:
                    if artifact_item.is_dir():
                        shutil.copytree(artifact_item, target_item, dirs_exist_ok=True)
                    elif artifact_item.is_file():
                        target_item.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(artifact_item, target_item)
                except Exception:
                    continue

            command = ["pdflatex", "-interaction=nonstopmode", temp_tex.name]

            for pass_number in (1, 2):
                pass_start = time.time()
                try:
                    proc = subprocess.run(
                        command,
                        cwd=work_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=timeout,
                        check=False,
                    )
                    duration_ms = (time.time() - pass_start) * 1000
                    log_chunks.append(
                        f"=== pdflatex pass {pass_number} (rc={proc.returncode}) ===\n{proc.stdout}\n"
                    )
                    passes.append(
                        CompilePass(
                            number=pass_number,
                            return_code=proc.returncode,
                            duration_ms=round(duration_ms, 2),
                            log_length=len(proc.stdout or ""),
                        )
                    )
                    if proc.returncode != 0:
                        success = False
                        error_message = f"pdflatex pass {pass_number} exited with {proc.returncode}"
                        break
                except subprocess.TimeoutExpired as exc:  # noqa: PERF203
                    duration_ms = (time.time() - pass_start) * 1000
                    passes.append(
                        CompilePass(
                            number=pass_number,
                            return_code=-1,
                            duration_ms=round(duration_ms, 2),
                            log_length=0,
                        )
                    )
                    log_chunks.append(
                        f"=== pdflatex pass {pass_number} TIMEOUT after {round(duration_ms, 2)}ms ===\n{exc.output or ''}\n"
                    )
                    success = False
                    error_message = f"pdflatex pass {pass_number} timed out after {round(timeout, 2)}s"
                    break

            compiled_source = work_dir / f"{temp_tex.stem}.pdf"
            if success and compiled_source.exists():
                shutil.copy2(compiled_source, output_pdf_path)
            elif output_pdf_path.exists():
                output_pdf_path.unlink()

        log_path.write_text("\n".join(log_chunks), encoding="utf-8")

        duration_ms = (time.time() - work_start) * 1000
        return CompileSummary(
            success=success and output_pdf_path.exists(),
            duration_ms=round(duration_ms, 2),
            passes=passes,
            error=error_message,
        )

    def _overlay_pdfs(
        self,
        original_pdf_path: Optional[Path],
        compiled_pdf_path: Path,
        final_pdf_path: Path,
    ) -> OverlaySummary:
        if not compiled_pdf_path.exists():
            return OverlaySummary(success=False, overlays=0, pages_processed=0)

        overlays = 0
        pages_processed = 0
        per_page: List[Dict[str, Any]] = []

        compiled_doc = fitz.open(compiled_pdf_path)
        try:
            original_doc = fitz.open(original_pdf_path) if original_pdf_path and original_pdf_path.exists() else None

            for page_index in range(len(compiled_doc)):
                page = compiled_doc[page_index]
                pages_processed += 1
                overlay_count = 0
                if original_doc and page_index < len(original_doc):
                    original_page = original_doc[page_index]
                    pix = original_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    page.insert_image(page.rect, stream=pix.tobytes("png"))
                    overlay_count += 1
                overlays += overlay_count
                per_page.append({"page": page_index + 1, "overlays": overlay_count})

            compiled_doc.save(final_pdf_path)
            success = True
        finally:
            compiled_doc.close()
            if 'original_doc' in locals() and original_doc is not None:
                original_doc.close()

        return OverlaySummary(
            success=success,
            overlays=overlays,
            pages_processed=pages_processed,
            per_page=per_page,
        )

    # ------------------------------------------------------------------
    # Structured data & helpers
    # ------------------------------------------------------------------
    def _update_structured_data(
        self,
        *,
        run_id: str,
        structured: Dict[str, Any],
        attacked_tex_path: Path,
        compiled_pdf_path: Optional[Path],
        final_pdf_path: Optional[Path],
        enhanced_pdf_path: Path,
        compile_log_path: Path,
        diagnostics_path: Path,
        replacement_summary: Dict[str, Any],
        compile_summary: CompileSummary,
        overlay_summary: OverlaySummary,
    ) -> Dict[str, Any]:
        manipulation_results = structured.setdefault("manipulation_results", {})
        artifacts_section = manipulation_results.setdefault("artifacts", {})
        debug_section = manipulation_results.setdefault("debug", {})
        enhanced_map = manipulation_results.setdefault("enhanced_pdfs", {})

        artifacts_entry = artifacts_section.setdefault("latex_dual_layer", {})
        artifacts_entry.update(
            {
                "attacked_tex": self._relative_to_run(attacked_tex_path, run_id),
                "compiled_pdf": self._relative_to_run(compiled_pdf_path, run_id)
                if compiled_pdf_path
                else None,
                "final_pdf": self._relative_to_run(final_pdf_path, run_id)
                if final_pdf_path
                else None,
                "compile_log": self._relative_to_run(compile_log_path, run_id),
                "diagnostics": self._relative_to_run(diagnostics_path, run_id),
            }
        )

        debug_section["latex_dual_layer"] = {
            "replacement_summary": replacement_summary,
            "compile": {
                "success": compile_summary.success,
                "duration_ms": compile_summary.duration_ms,
                "error": compile_summary.error,
                "passes": [asdict(pass_summary) for pass_summary in compile_summary.passes],
            },
            "overlay": {
                "success": overlay_summary.success,
                "overlays": overlay_summary.overlays,
                "pages_processed": overlay_summary.pages_processed,
                "per_page": overlay_summary.per_page,
            },
        }

        final_size = final_pdf_path.stat().st_size if final_pdf_path and final_pdf_path.exists() else 0

        render_stats = {
            "replacement_targets": replacement_summary.get("total", 0),
            "replacement_success": replacement_summary.get("replaced", 0),
            "compile_success": compile_summary.success,
            "compile_duration_ms": compile_summary.duration_ms,
            "overlay_success": overlay_summary.success,
            "overlay_applied": overlay_summary.overlays,
        }

        enhanced_entry = enhanced_map.setdefault("latex_dual_layer", {})
        enhanced_entry.update(
            {
                "path": str(enhanced_pdf_path),
                "relative_path": self._relative_to_run(enhanced_pdf_path, run_id),
                "file_size_bytes": final_size,
                "replacements": replacement_summary.get("total", 0),
                "overlay_applied": overlay_summary.overlays,
                "overlay_targets": replacement_summary.get("replaced", 0),
                "effectiveness_score": None,
                "render_stats": render_stats,
            }
        )

        self.structured_manager.save(run_id, structured)

        return {
            "file_size_bytes": final_size,
            "replacements": replacement_summary.get("total", 0),
            "overlay_applied": overlay_summary.overlays,
            "overlay_targets": replacement_summary.get("replaced", 0),
            "artifact_rel_paths": {
                key: value
                for key, value in artifacts_entry.items()
                if value is not None
            },
            "replacement_summary": replacement_summary,
            "compile_summary": debug_section["latex_dual_layer"]["compile"],
            "overlay_summary": debug_section["latex_dual_layer"]["overlay"],
        }

    def _summarize_replacements(self, diagnostics: List[MappingDiagnostic]) -> Dict[str, Any]:
        total = len(diagnostics)
        replaced = sum(1 for entry in diagnostics if entry.status == "replaced")
        not_found = sum(1 for entry in diagnostics if entry.status == "not_found")
        no_mapping = sum(1 for entry in diagnostics if entry.status == "no_mapping")
        return {
            "total": total,
            "replaced": replaced,
            "not_found": not_found,
            "no_mapping": no_mapping,
        }

    def _resolve_original_pdf_path(
        self,
        manual_meta: Dict[str, Any],
        document_meta: Dict[str, Any],
    ) -> Optional[Path]:
        source_pdf_path_str = manual_meta.get("pdf_path") or document_meta.get("source_path")
        if not source_pdf_path_str:
            return None
        pdf_path = Path(source_pdf_path_str)
        return pdf_path if pdf_path.exists() else None

    def _relative_to_run(self, path: Optional[Path], run_id: str) -> Optional[str]:
        if not path:
            return None
        try:
            return str(path.relative_to(run_directory(run_id)))
        except ValueError:
            return str(path)

    def _compile_timeout(self) -> float:
        try:
            from flask import current_app

            return float(current_app.config.get("LATEX_COMPILATION_TIMEOUT", 60))
        except Exception:
            return float(os.getenv("FAIRTESTAI_LATEX_COMPILATION_TIMEOUT", "60"))

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

