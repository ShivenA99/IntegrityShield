from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import string
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from flask import current_app

from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...utils.logging import get_logger
from ...utils.storage_paths import artifacts_root, enhanced_pdf_path, run_directory
from ...utils.time import isoformat, utc_now
from .font_attack import (
    AttackPlan,
    ChunkPlanner,
    FontAttackBuilder,
    FontBuildError,
    FontBuildResult,
    FontCache,
)
from .font_attack.prevention_font_library import (
    get_prevention_font_library,
    PreventionFontLibrary,
)


@dataclass
class MappingDiagnostic:
    mapping_id: Optional[str]
    question_number: str
    status: str
    original: str
    replacement: str
    location: Optional[Tuple[int, int]] = None
    notes: Optional[str] = None


@dataclass
class AttackJob:
    attack_id: str
    mapping_id: Optional[str]
    question_number: str
    visual_text: str
    hidden_text: str
    plan: AttackPlan
    latex_replacement: str
    font_results: Sequence[FontBuildResult]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


class LatexFontAttackService:
    """
    Rewrites reconstructed LaTeX using custom fonts so that each manipulated
    substring renders the original text while the PDF text layer preserves the
    replacement text.
    """

    DEFAULT_BASE_FONT = _backend_root() / "resources" / "fonts" / "Roboto-Regular.ttf"

    def __init__(self, base_font_path: Optional[Path] = None) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self.structured_manager = StructuredDataManager()
        candidate_path = Path(base_font_path) if base_font_path is not None else self.DEFAULT_BASE_FONT
        if not candidate_path.is_absolute():
            candidate_path = (_backend_root() / candidate_path).resolve()
        self.base_font_path = candidate_path
        self._tex_package_cache: Dict[str, bool] = {}
        self._needs_enumitem_patch: bool = False

    def execute(
        self,
        run_id: str,
        *,
        force: bool = False,
        tex_override: Optional[Path] = None,
        artifact_label: Optional[str] = None,
        record_method: Optional[str] = None,
    ) -> Dict[str, Any]:
        from ...models import PipelineRun

        self.logger.info("Starting LaTeX font attack", extra={"run_id": run_id})
        self._needs_enumitem_patch = False
        structured = self.structured_manager.load(run_id) or {}
        manual_meta = structured.get("manual_input") or {}
        document_meta = structured.get("document") or {}
        artifact_dir_name = artifact_label or "latex-font-attack"
        method_key = record_method or artifact_dir_name.replace("-", "_")

        # Check if we're in prevention mode
        run = PipelineRun.query.get(run_id)
        mode = run.pipeline_config.get("mode", "detection") if run else "detection"
        is_prevention_mode = mode == "prevention"

        # Load prevention font library if in prevention mode
        prevention_library = None
        if is_prevention_mode:
            library = get_prevention_font_library()
            if not library.is_loaded():
                self.logger.warning(
                    "Prevention font library not loaded. "
                    "Falling back to runtime font generation. "
                    "Run: python scripts/generate_prevention_font_library.py"
                )
                prevention_library = None
            else:
                prevention_library = library
                stats = library.get_library_stats()
                self.logger.info(
                    f"Prevention library loaded: {stats['total_fonts']} fonts available",
                    extra={"run_id": run_id, "library_stats": stats}
                )

        if tex_override is not None:
            tex_path = Path(tex_override)
        else:
            tex_path = self._resolve_tex_path(manual_meta, document_meta)
        if not tex_path.exists():
            raise FileNotFoundError(f"LaTeX source not found at {tex_path}")

        artifacts_dir = artifacts_root(run_id) / artifact_dir_name
        fonts_dir = artifacts_dir / "fonts"
        cache_dir = artifacts_dir / ".cache"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        if fonts_dir.exists():
            shutil.rmtree(fonts_dir)
        fonts_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = artifacts_dir / "metadata.json"

        questions = self._load_questions(run_id)
        original_tex = self._read_tex(tex_path)
        tex_hash = hashlib.sha256(original_tex.encode("utf-8")).hexdigest()
        mapping_signature = self._build_signature(questions, tex_hash, tex_path)

        if metadata_path.exists() and not force:
            cached = json.loads(metadata_path.read_text(encoding="utf-8"))
            if cached.get("mapping_signature") == mapping_signature:
                cached["cached"] = True
                return cached

        if not self.base_font_path.exists():
            error_message = f"Base font not found at {self.base_font_path}"
            self.logger.error(
                "Latex font attack aborted: base font missing",
                extra={"run_id": run_id, "font_path": str(self.base_font_path)},
            )
            return self._record_failure(
                run_id=run_id,
                artifacts_dir=artifacts_dir,
                enhanced_pdf_path=enhanced_pdf_path(run_id, method_key),
                metadata_path=metadata_path,
                structured=structured,
                mapping_signature=mapping_signature,
                error_message=error_message,
                method_key=method_key,
                tex_path=tex_path,
                tex_hash=tex_hash,
            )

        base_font_target = fonts_dir / self.base_font_path.name
        shutil.copy2(self.base_font_path, base_font_target)

        builder = FontAttackBuilder(self.base_font_path)
        planner = ChunkPlanner(builder.glyph_lookup)
        cache = FontCache(cache_dir)

        if is_prevention_mode:
            # Prevention mode: random character mappings for all question stems
            mutated_tex, jobs, diagnostics = self._apply_prevention_font_attack(
                original_tex, structured, planner, builder, fonts_dir, cache
            )
        else:
            # Detection mode: mapping-based font attack
            mutated_tex, jobs, diagnostics = self._apply_font_attack(
                original_tex, questions, planner, builder, fonts_dir, cache
            )

        attacked_tex_path = artifacts_dir / "latex_font_attack_attacked.tex"
        attacked_tex_path.write_text(mutated_tex, encoding="utf-8")

        compile_log_path = artifacts_dir / "latex_font_attack_compile.log"
        final_pdf_path = artifacts_dir / "latex_font_attack_final.pdf"

        compile_summary = self._compile_tex(
            tex_path=tex_path,
            mutated_tex_path=attacked_tex_path,
            fonts_dir=fonts_dir,
            output_pdf=final_pdf_path,
            log_path=compile_log_path,
        )

        enhanced_pdf = enhanced_pdf_path(run_id, method_key)
        enhanced_pdf.parent.mkdir(parents=True, exist_ok=True)
        if final_pdf_path.exists():
            shutil.copy2(final_pdf_path, enhanced_pdf)
        else:
            enhanced_pdf.write_bytes(b"")

        try:
            resolved_tex_path = str(tex_path.resolve())
        except Exception:
            resolved_tex_path = str(tex_path)

        tex_source_info = {
            "path": resolved_tex_path,
            "hash": tex_hash,
        }

        result_payload = {
            "run_id": run_id,
            "generated_at": isoformat(utc_now()),
            "tex_source": tex_source_info,
            "artifacts": {
                "attacked_tex": str(attacked_tex_path),
                "compile_log": str(compile_log_path),
                "final_pdf": str(final_pdf_path) if final_pdf_path.exists() else None,
                "fonts_dir": str(fonts_dir),
            },
            "compile_summary": compile_summary,
            "diagnostics": [asdict(entry) for entry in diagnostics],
            "attacks": [self._serialize_job(job) for job in jobs],
            "mapping_signature": mapping_signature,
        }

        metadata_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

        manipulation_results = structured.setdefault("manipulation_results", {})
        artifacts_section = manipulation_results.setdefault("artifacts", {})
        artifacts_section[method_key] = {
            "attacked_tex": self._relative_to_run(attacked_tex_path, run_id),
            "final_pdf": self._relative_to_run(final_pdf_path, run_id)
            if final_pdf_path.exists()
            else None,
            "compile_log": self._relative_to_run(compile_log_path, run_id),
        }
        debug_section = manipulation_results.setdefault("debug", {})
        debug_section[method_key] = {
            "diagnostics": [asdict(entry) for entry in diagnostics],
            "compile_summary": compile_summary,
            "attacks": [self._serialize_job(job) for job in jobs],
            "tex_source": tex_source_info,
        }
        enhanced_map = manipulation_results.setdefault("enhanced_pdfs", {})
        enhanced_map[method_key] = {
            "path": str(enhanced_pdf),
            "method": method_key,
            "effectiveness_score": None,
            "fonts_generated": sum(len(job.font_results) for job in jobs),
            "tex_source": tex_source_info,
        }

        self.structured_manager.save(run_id, structured)
        self.logger.info(
            "Completed LaTeX font attack",
            extra={
                "run_id": run_id,
                "method": method_key,
                "fonts_generated": sum(len(job.font_results) for job in jobs),
                "success": compile_summary.get("success"),
            },
        )
        return result_payload

    def _record_failure(
        self,
        *,
        run_id: str,
        artifacts_dir: Path,
        enhanced_pdf_path: Path,
        metadata_path: Path,
        structured: Dict[str, Any],
        mapping_signature: List[Dict[str, Any]],
        error_message: str,
        method_key: str,
        tex_path: Optional[Path] = None,
        tex_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        compile_summary = {"success": False, "error": error_message, "passes": []}
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        enhanced_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        enhanced_pdf_path.write_bytes(b"")

        tex_source_info: Optional[Dict[str, Any]] = None
        if tex_path is not None:
            try:
                resolved = str(tex_path.resolve())
            except Exception:
                resolved = str(tex_path)
            tex_source_info = {
                "path": resolved,
                "hash": tex_hash,
            }

        result_payload = {
            "run_id": run_id,
            "generated_at": isoformat(utc_now()),
            "artifacts": {
                "attacked_tex": None,
                "compile_log": None,
                "final_pdf": None,
                "fonts_dir": str(artifacts_dir / "fonts"),
            },
            "compile_summary": compile_summary,
            "diagnostics": [],
            "attacks": [],
            "mapping_signature": mapping_signature,
            "error": error_message,
        }
        if tex_source_info:
            result_payload["tex_source"] = tex_source_info

        metadata_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

        manipulation_results = structured.setdefault("manipulation_results", {})
        artifacts_section = manipulation_results.setdefault("artifacts", {})
        artifacts_section[method_key] = {
            "attacked_tex": None,
            "final_pdf": None,
            "compile_log": None,
        }
        debug_section = manipulation_results.setdefault("debug", {})
        debug_section[method_key] = {
            "diagnostics": [],
            "compile_summary": compile_summary,
            "attacks": [],
            "error": error_message,
            "tex_source": tex_source_info,
        }
        enhanced_map = manipulation_results.setdefault("enhanced_pdfs", {})
        enhanced_map[method_key] = {
            "path": str(enhanced_pdf_path),
            "method": method_key,
            "effectiveness_score": None,
            "fonts_generated": 0,
            "error": error_message,
            "tex_source": tex_source_info,
        }
        self.structured_manager.save(run_id, structured)
        return result_payload

    def _resolve_tex_path(self, manual_meta: Dict[str, Any], document_meta: Dict[str, Any]) -> Path:
        tex_path_str = manual_meta.get("tex_path") or document_meta.get("latex_path")
        if not tex_path_str:
            raise ValueError("LaTeX path not present in structured data")
        resolved = Path(tex_path_str)
        if not resolved.is_absolute():
            base_root = Path(current_app.config["PIPELINE_STORAGE_ROOT"])
            resolved = (base_root / resolved).resolve()
        return resolved

    def _read_tex(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")

    def _apply_font_attack(
        self,
        tex_content: str,
        questions: Sequence[QuestionManipulation],
        planner: ChunkPlanner,
        builder: FontAttackBuilder,
        fonts_dir: Path,
        cache: FontCache,
    ) -> Tuple[str, Sequence[AttackJob], Sequence[MappingDiagnostic]]:
        self._font_command_registry: Dict[str, set[str]] = {}

        replacements: List[Tuple[int, int, str, AttackJob]] = []
        occupied_ranges: List[Tuple[int, int, Optional[str]]] = []
        diagnostics: List[MappingDiagnostic] = []
        attack_jobs: List[AttackJob] = []
        counter = 0

        for question in questions:
            mappings = list(getattr(question, "substring_mappings", []) or [])
            if not mappings:
                continue

            for mapping in mappings:
                if not mapping.get("validated"):
                    continue
                original = str(mapping.get("original") or "")
                replacement = str(mapping.get("replacement") or "")
                if not original or not replacement:
                    continue

                location = self._locate_fragment(tex_content, mapping, original)
                diagnostic = MappingDiagnostic(
                    mapping_id=mapping.get("id"),
                    question_number=str(question.question_number or question.id or ""),
                    status="pending",
                    original=original,
                    replacement=replacement,
                )

                if not location:
                    diagnostic.status = "not_found"
                    diagnostics.append(diagnostic)
                    continue

                start, end = location

                overlap = self._find_range_overlap(occupied_ranges, start, end)
                if overlap:
                    diagnostic.status = "overlap_conflict"
                    conflict_id = overlap[2] or "unknown"
                    diagnostic.notes = (
                        f"Overlaps mapping {conflict_id} ({overlap[0]}-{overlap[1]})"
                    )
                    diagnostics.append(diagnostic)
                    continue

                try:
                    plan = planner.plan(replacement, original)
                except KeyError as exc:
                    diagnostic.status = "missing_glyph"
                    diagnostic.notes = str(exc)
                    diagnostics.append(diagnostic)
                    continue
                except ValueError as exc:
                    diagnostic.status = "invalid_mapping"
                    diagnostic.notes = str(exc)
                    diagnostics.append(diagnostic)
                    continue

                attack_id = f"fa{counter:04d}"
                counter += 1

                raw_font_results = builder.build_fonts(
                    plan, fonts_dir / attack_id, cache_lookup=cache
                )
                font_results: List[FontBuildResult] = []
                attack_font_dir = fonts_dir / attack_id
                attack_font_dir.mkdir(parents=True, exist_ok=True)
                for raw in raw_font_results:
                    target_name = f"{attack_id}_pos{raw.index}.ttf"
                    target_path = attack_font_dir / target_name
                    if raw.font_path != target_path:
                        shutil.copy2(raw.font_path, target_path)
                    font_results.append(
                        FontBuildResult(
                            index=raw.index,
                            hidden_char=raw.hidden_char,
                            visual_text=raw.visual_text,
                            font_path=target_path,
                            used_cache=raw.used_cache,
                        )
                    )
                latex_replacement = self._render_replacement(
                    attack_id, plan, font_results
                )

                replacements.append((start, end, latex_replacement, AttackJob(
                    attack_id=attack_id,
                    mapping_id=mapping.get("id"),
                    question_number=str(question.question_number or question.id or ""),
                    visual_text=original,
                    hidden_text=replacement,
                    plan=plan,
                    latex_replacement=latex_replacement,
                    font_results=font_results,
                )))

                occupied_ranges.append((start, end, mapping.get("id")))

                diagnostic.status = "replaced"
                diagnostic.location = location
                diagnostics.append(diagnostic)

        if not replacements:
            return tex_content, tuple(), tuple(diagnostics)

        mutated = tex_content
        for start, end, replacement_text, job in sorted(
            replacements, key=lambda item: item[0], reverse=True
        ):
            mutated = mutated[:start] + replacement_text + mutated[end:]
            attack_jobs.append(job)

        attack_jobs.reverse()

        mutated = self._normalize_tex_dependencies(mutated)
        mutated = self._ensure_preamble(mutated, attack_jobs)
        return mutated, tuple(attack_jobs), tuple(diagnostics)

    def _apply_prevention_font_attack(
        self,
        tex_content: str,
        structured: Dict[str, Any],
        planner: ChunkPlanner,
        builder: FontAttackBuilder,
        fonts_dir: Path,
        cache: FontCache,
    ) -> Tuple[str, Sequence[AttackJob], Sequence[MappingDiagnostic]]:
        """
        Prevention mode: Use pre-generated font library for instant font application.
        Falls back to runtime generation for characters not in library.
        All characters use universal hidden character 'a' for maximum font reuse.
        """
        # Load prevention font library
        library = get_prevention_font_library()
        UNIVERSAL_HIDDEN_CHAR = 'a'  # All characters map to 'a'

        self._font_command_registry: Dict[str, set[str]] = {}

        replacements: List[Tuple[int, int, str, AttackJob]] = []
        occupied_ranges: List[Tuple[int, int, Optional[str]]] = []
        diagnostics: List[MappingDiagnostic] = []
        attack_jobs: List[AttackJob] = []
        counter = 0

        # Track library hit/miss statistics
        library_hits = 0
        runtime_builds = 0

        # Get all question stems from structured data
        ai_questions = structured.get("ai_questions", [])

        for question in ai_questions:
            stem_text = question.get("stem_text", "")
            if not stem_text:
                continue

            question_number = str(question.get("question_number") or question.get("q_number") or "")

            # Find the stem in the LaTeX
            stem_index = tex_content.find(stem_text)
            if stem_index == -1:
                # Stem not found exactly, log diagnostic
                diagnostics.append(MappingDiagnostic(
                    mapping_id=None,
                    question_number=question_number,
                    status="stem_not_found",
                    original=stem_text[:50],  # First 50 chars
                    replacement="",
                    notes=f"Stem text not found in LaTeX for Q{question_number}"
                ))
                continue

            # Process each alphanumeric character in the stem
            for i, char in enumerate(stem_text):
                if not char.isalnum():
                    continue

                char_start = stem_index + i
                char_end = char_start + 1

                # Check for overlaps
                overlap = self._find_range_overlap(occupied_ranges, char_start, char_end)
                if overlap:
                    continue

                # Try library lookup first
                font_path_in_library = None
                if library and library.is_loaded():
                    font_path_in_library = library.get_font_for_char(char)

                try:
                    # Plan font attack using universal hidden character
                    # Hidden: 'a' (universal), Visual: original character
                    plan = planner.plan(UNIVERSAL_HIDDEN_CHAR, char)
                except (KeyError, ValueError) as exc:
                    diagnostics.append(MappingDiagnostic(
                        mapping_id=None,
                        question_number=question_number,
                        status="planning_failed",
                        original=char,
                        replacement=UNIVERSAL_HIDDEN_CHAR,
                        location=(char_start, char_end),
                        notes=str(exc)
                    ))
                    continue

                attack_id = f"pfa{counter:04d}"  # Prevention Font Attack ID
                counter += 1

                # Build or copy fonts
                font_results: List[FontBuildResult] = []
                attack_font_dir = fonts_dir / attack_id
                attack_font_dir.mkdir(parents=True, exist_ok=True)

                if font_path_in_library:
                    # LIBRARY HIT: Copy pre-generated font
                    for position in plan:
                        if not position.requires_font:
                            continue

                        target_name = f"{attack_id}_pos{position.index}.ttf"
                        target_path = attack_font_dir / target_name
                        shutil.copy2(font_path_in_library, target_path)

                        font_results.append(
                            FontBuildResult(
                                index=position.index,
                                hidden_char=position.hidden_char,
                                visual_text=position.visual_text,
                                font_path=target_path,
                                used_cache=True  # Library reuse
                            )
                        )

                    library_hits += 1
                else:
                    # LIBRARY MISS: Build at runtime (fallback)
                    try:
                        raw_font_results = builder.build_fonts(
                            plan, attack_font_dir, cache_lookup=cache
                        )
                        for raw in raw_font_results:
                            target_name = f"{attack_id}_pos{raw.index}.ttf"
                            target_path = attack_font_dir / target_name
                            if raw.font_path != target_path:
                                shutil.copy2(raw.font_path, target_path)
                            font_results.append(
                                FontBuildResult(
                                    index=raw.index,
                                    hidden_char=raw.hidden_char,
                                    visual_text=raw.visual_text,
                                    font_path=target_path,
                                    used_cache=raw.used_cache,
                                )
                            )
                        runtime_builds += 1
                    except FontBuildError as exc:
                        diagnostics.append(MappingDiagnostic(
                            mapping_id=None,
                            question_number=question_number,
                            status="font_build_failed",
                            original=char,
                            replacement=UNIVERSAL_HIDDEN_CHAR,
                            location=(char_start, char_end),
                            notes=str(exc)
                        ))
                        continue

                latex_replacement = self._render_replacement(attack_id, plan, font_results)

                replacements.append((char_start, char_end, latex_replacement, AttackJob(
                    attack_id=attack_id,
                    mapping_id=None,
                    question_number=question_number,
                    visual_text=char,
                    hidden_text=UNIVERSAL_HIDDEN_CHAR,
                    plan=plan,
                    latex_replacement=latex_replacement,
                    font_results=font_results,
                )))

                occupied_ranges.append((char_start, char_end, None))

                diagnostics.append(MappingDiagnostic(
                    mapping_id=None,
                    question_number=question_number,
                    status="replaced",
                    original=char,
                    replacement=UNIVERSAL_HIDDEN_CHAR,
                    location=(char_start, char_end)
                ))

        # Log statistics
        self.logger.info(
            f"Prevention font stats: {library_hits} library hits, "
            f"{runtime_builds} runtime builds, {counter} total characters"
        )

        if not replacements:
            return tex_content, tuple(), tuple(diagnostics)

        # Apply all replacements (reverse order to preserve indices)
        mutated = tex_content
        for start, end, replacement_text, job in sorted(
            replacements, key=lambda item: item[0], reverse=True
        ):
            mutated = mutated[:start] + replacement_text + mutated[end:]
            attack_jobs.append(job)

        attack_jobs.reverse()

        mutated = self._normalize_tex_dependencies(mutated)
        mutated = self._ensure_preamble(mutated, attack_jobs)
        return mutated, tuple(attack_jobs), tuple(diagnostics)

    def _render_replacement(
        self,
        attack_id: str,
        plan: AttackPlan,
        font_results: Sequence[FontBuildResult],
    ) -> str:
        font_lookup = {result.index: result for result in font_results}
        fragments: List[str] = []
        declarations: List[str] = []
        for position in plan:
            if position.requires_font:
                font_result = font_lookup.get(position.index)
                if not font_result:
                    raise FontBuildError(
                        f"No font generated for attack {attack_id} position {position.index}"
                    )
                macro_key = self._font_command_name(attack_id, position.index)
                font_basename = font_result.font_path.stem
                command_decl = self._newfontfamily_declaration(
                    macro_key, font_basename, attack_id
                )
                declarations.append(command_decl)
                char_code = f"\\char\"{ord(position.hidden_char):04X}"
                fragments.append(
                    f"{{\\csname {macro_key}\\endcsname{char_code}}}"
                )
            else:
                fragments.append(self._plain_hidden_char(position.hidden_char))

        for declaration in declarations:
            self._register_command(declaration, attack_id)

        return "".join(fragments)

    def _plain_hidden_char(self, char: str) -> str:
        return f"{{\\char\"{ord(char):04X}}}"

    def _register_command(self, declaration: str, attack_id: str) -> None:
        self._font_command_registry.setdefault(attack_id, set()).add(declaration)

    def _latex_package_available(self, package: str) -> bool:
        cached = self._tex_package_cache.get(package)
        if cached is not None:
            return cached
        try:
            result = subprocess.run(
                ["kpsewhich", f"{package}.sty"],
                capture_output=True,
                text=True,
                check=False,
            )
            available = result.returncode == 0 and bool(result.stdout.strip())
        except FileNotFoundError:
            available = False
        self._tex_package_cache[package] = available
        return available

    def _normalize_tex_dependencies(self, tex_content: str) -> str:
        if "\\usepackage{enumitem}" in tex_content and not self._latex_package_available("enumitem"):
            tex_content = tex_content.replace(
                "\\usepackage{enumitem}", "% enumitem package removed (not available)"
            )
            tex_content = re.sub(
                r"(\\begin\{enumerate\})\s*\[[^\]]*\]",
                r"\\begin{enumerate}",
                tex_content,
            )
            self._needs_enumitem_patch = True
        return tex_content

    def _ensure_preamble(
        self, tex_content: str, jobs: Sequence[AttackJob]
    ) -> str:
        preamble_parts: List[str] = []
        if "\\usepackage{fontspec}" not in tex_content:
            preamble_parts.append("\\usepackage{fontspec}")

        if "\\setmainfont" not in tex_content:
            preamble_parts.append(
                "\\setmainfont{Roboto-Regular}[Path=fonts/,Extension=.ttf]"
            )

        if "\\usepackage{xcolor}" not in tex_content and (
            "\\textcolor" in tex_content or "\\color{" in tex_content
        ):
            preamble_parts.append("\\usepackage{xcolor}")

        if self._needs_enumitem_patch:
            preamble_parts.extend(
                [
                    "\\setlength{\\leftmargini}{0pt}",
                    "\\setlength{\\leftmargin}{0pt}",
                    "\\setlength{\\labelsep}{0.5em}",
                ]
            )

        registry = getattr(self, "_font_command_registry", {})
        for declarations in registry.values():
            preamble_parts.extend(sorted(declarations))

        if not preamble_parts:
            return tex_content

        preamble_block = "\n".join(preamble_parts) + "\n"

        document_match = re.search(r"\\begin\{document\}", tex_content)
        if document_match:
            insert_at = document_match.start()
            return (
                tex_content[:insert_at] + preamble_block + tex_content[insert_at:]
            )
        return preamble_block + tex_content

    def _newfontfamily_declaration(
        self, macro_name: str, font_basename: str, attack_id: str
    ) -> str:
        return (
            f"\\expandafter\\newfontfamily\\csname {macro_name}\\endcsname"
            f"{{{font_basename}}}[\n"
            f"    Path=fonts/{attack_id}/,\n"
            "    Extension=.ttf\n"
            "]"
        )

    def _font_command_name(self, attack_id: str, index: int) -> str:
        safe = re.sub(r"[^A-Za-z0-9]", "", attack_id)
        if not safe:
            safe = "FA"
        if not safe[0].isalpha():
            safe = f"FA{safe}"
        return f"{safe}Font{index}"

    def _locate_fragment(
        self,
        tex_content: str,
        mapping: Dict[str, Any],
        original: str,
    ) -> Optional[Tuple[int, int]]:
        stem = mapping.get("latex_stem_text") or ""
        start_pos = mapping.get("start_pos")
        end_pos = mapping.get("end_pos")

        if stem and isinstance(start_pos, int) and isinstance(end_pos, int):
            stem_index = tex_content.find(stem)
            if stem_index != -1:
                local_segment = stem[start_pos:end_pos]
                if local_segment == original:
                    return stem_index + start_pos, stem_index + end_pos

        direct_index = tex_content.find(original)
        if direct_index != -1:
            return direct_index, direct_index + len(original)
        return None

    def _find_range_overlap(
        self,
        occupied_ranges: Sequence[Tuple[int, int, Optional[str]]],
        start: int,
        end: int,
    ) -> Optional[Tuple[int, int, Optional[str]]]:
        for existing_start, existing_end, mapping_id in occupied_ranges:
            if start < existing_end and end > existing_start:
                return (existing_start, existing_end, mapping_id)
        return None

    def _compile_tex(
        self,
        tex_path: Path,
        mutated_tex_path: Path,
        fonts_dir: Path,
        output_pdf: Path,
        log_path: Path,
    ) -> Dict[str, Any]:
        temp_dir = Path(tempfile.mkdtemp(prefix="latex_font_attack_"))
        try:
            working_tex = temp_dir / "document.tex"
            latex_source = mutated_tex_path.read_text(encoding="utf-8")
            working_tex.write_text(latex_source, encoding="utf-8")

            self._copy_graphic_assets(
                latex_source, tex_path.parent, temp_dir
            )

            local_fonts_dir = temp_dir / "fonts"
            local_fonts_dir.mkdir(parents=True, exist_ok=True)
            for font_file in fonts_dir.rglob("*.ttf"):
                relative = font_file.relative_to(fonts_dir)
                target = local_fonts_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(font_file, target)

            if self.base_font_path.exists():
                shutil.copy2(self.base_font_path, local_fonts_dir / self.base_font_path.name)

            passes = []
            success = True

            log_path.write_text("", encoding="utf-8")

            for iteration in range(2):
                proc = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "document.tex"],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                )
                passes.append(
                    {
                        "iteration": iteration + 1,
                        "return_code": proc.returncode,
                        "stdout": len(proc.stdout or ""),
                        "stderr": len(proc.stderr or ""),
                    }
                )
                with open(log_path, "a", encoding="utf-8") as handle:
                    handle.write(
                        f"--- Pass {iteration + 1} ---\n{proc.stdout}\n{proc.stderr}\n"
                    )
                if proc.returncode != 0:
                    success = False
                    break

            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            if success:
                compiled_pdf = temp_dir / "document.pdf"
                if compiled_pdf.exists():
                    shutil.copy2(compiled_pdf, output_pdf)
                else:
                    success = False

            return {
                "success": success,
                "passes": passes,
                "log_path": str(log_path),
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _copy_graphic_assets(
        self, tex_content: str, source_root: Path, temp_dir: Path
    ) -> None:
        graphic_dirs = []
        for raw_path in self._extract_graphic_paths(tex_content):
            normalized = self._normalize_graphic_path(raw_path)
            if normalized is None:
                continue
            source_dir = (source_root / normalized).resolve()
            if normalized == Path("."):
                graphic_dirs.append(normalized)
                continue
            if not source_dir.exists() or not source_dir.is_dir():
                continue
            target_dir = temp_dir / normalized
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            graphic_dirs.append(normalized)

        filenames = self._extract_graphic_filenames(tex_content)
        for filename in filenames:
            candidates = [(source_root / filename).resolve()]
            for directory in graphic_dirs:
                candidates.append((source_root / directory / filename).resolve())
            for candidate in candidates:
                if candidate.exists():
                    try:
                        target = temp_dir / candidate.relative_to(source_root.resolve())
                    except ValueError:
                        target = temp_dir / candidate.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate, target)
                    break

    def _extract_graphic_paths(self, tex_content: str) -> List[str]:
        pattern = re.compile(r"\\graphicspath\{\{([^}]*)\}\}")
        matches = pattern.findall(tex_content)
        paths: List[str] = []
        for match in matches:
            for candidate in match.split("}{"):
                cleaned = candidate.strip()
                if cleaned:
                    paths.append(cleaned)
        return paths

    def _extract_graphic_filenames(self, tex_content: str) -> List[str]:
        pattern = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
        files = {entry.strip() for entry in pattern.findall(tex_content) if entry.strip()}
        return sorted(files)

    def _normalize_graphic_path(self, path_str: str) -> Optional[Path]:
        normalized = (path_str or "").strip()
        if not normalized:
            return Path(".")
        normalized = normalized.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if not normalized or normalized == ".":
            return Path(".")
        if normalized.startswith("/"):
            return None
        return Path(normalized.rstrip("/"))

    def _serialize_job(self, job: AttackJob) -> Dict[str, Any]:
        return {
            "attack_id": job.attack_id,
            "mapping_id": job.mapping_id,
            "question_number": job.question_number,
            "visual_text": job.visual_text,
            "hidden_text": job.hidden_text,
            "plan": [
                {
                    "index": position.index,
                    "hidden_char": position.hidden_char,
                    "visual_text": position.visual_text,
                    "glyph_names": list(position.glyph_names),
                    "advance_width": position.advance_width,
                }
                for position in job.plan
            ],
            "fonts": [
                {
                    "index": font.index,
                    "font_path": str(font.font_path),
                    "visual_text": font.visual_text,
                    "used_cache": font.used_cache,
                }
                for font in job.font_results
            ],
        }

    def _load_questions(self, run_id: str) -> Sequence[QuestionManipulation]:
        questions = (
            QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
            .order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
            .all()
        )
        structured = self.structured_manager.load(run_id) or {}
        structured_questions = structured.get("questions") or []

        by_id = {
            entry.get("manipulation_id"): entry for entry in structured_questions if entry.get("manipulation_id")
        }
        by_seq = {
            entry.get("sequence_index"): entry for entry in structured_questions if entry.get("sequence_index") is not None
        }
        by_number = {
            str(entry.get("question_number") or entry.get("q_number") or ""): entry for entry in structured_questions
        }

        for question in questions:
            structured_entry = (
                by_id.get(question.id)
                or by_seq.get(getattr(question, "sequence_index", None))
                or by_number.get(str(question.question_number or ""))
            )
            if structured_entry:
                mappings = (structured_entry.get("manipulation") or {}).get("substring_mappings") or []
                if mappings:
                    question.substring_mappings = json.loads(json.dumps(mappings))

        return questions

    def _build_signature(
        self,
        questions: Sequence[QuestionManipulation],
        tex_hash: str,
        tex_path: Path,
    ) -> List[Dict[str, Any]]:
        signature: List[Dict[str, Any]] = []
        for question in questions:
            mappings = list(getattr(question, "substring_mappings", []) or [])
            for mapping in mappings:
                if not mapping.get("validated"):
                    continue
                signature.append(
                    {
                        "id": mapping.get("id"),
                        "original": mapping.get("original"),
                        "replacement": mapping.get("replacement"),
                        "question": str(question.question_number or question.id or ""),
                    }
                )
        try:
            resolved = str(tex_path.resolve())
        except Exception:
            resolved = str(tex_path)
        signature.append({"tex_path": resolved, "tex_hash": tex_hash})
        return signature

    def _relative_to_run(self, path: Path, run_id: str) -> str:
        try:
            return str(path.relative_to(run_directory(run_id)))
        except ValueError:
            return str(path)
