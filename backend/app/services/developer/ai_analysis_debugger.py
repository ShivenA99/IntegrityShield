from __future__ import annotations

import json
from typing import Dict, Any, List, Optional

from ..ai_clients.base_ai_client import AIExtractionResult
from ...utils.logging import get_logger
from .live_logging_service import live_logging_service


class AIAnalysisDebugger:
    """Debug and analyze AI extraction results for quality and consistency."""

    def __init__(self):
        self.logger = get_logger(__name__)

    def debug_extraction_results(
        self,
        run_id: str,
        pymupdf_data: Dict[str, Any],
        ai_results: Dict[str, AIExtractionResult],
        fusion_result: Optional[AIExtractionResult] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive debugging analysis of AI extraction results.

        Args:
            run_id: Pipeline run ID
            pymupdf_data: Raw PyMuPDF extraction data
            ai_results: Results from individual AI sources
            fusion_result: Final fused result

        Returns:
            Debug analysis report
        """
        debug_report = {
            "run_id": run_id,
            "timestamp": self._get_timestamp(),
            "source_analysis": {},
            "cross_validation": {},
            "quality_assessment": {},
            "recommendations": []
        }

        # Analyze each source
        for source, result in ai_results.items():
            debug_report["source_analysis"][source] = self._analyze_source_result(source, result)

        # Cross-validate between sources
        debug_report["cross_validation"] = self._cross_validate_sources(ai_results)

        # Quality assessment
        debug_report["quality_assessment"] = self._assess_overall_quality(
            pymupdf_data, ai_results, fusion_result
        )

        # Generate recommendations
        debug_report["recommendations"] = self._generate_recommendations(debug_report)

        # Log for real-time monitoring
        live_logging_service.emit(
            run_id,
            "ai_debugger",
            "INFO",
            "AI extraction debugging completed",
            context={
                "sources_analyzed": list(ai_results.keys()),
                "total_questions": sum(len(r.questions) for r in ai_results.values()),
                "quality_score": debug_report["quality_assessment"].get("overall_score", 0),
                "critical_issues": len([r for r in debug_report["recommendations"] if r.get("severity") == "critical"])
            }
        )

        return debug_report

    def _analyze_source_result(self, source: str, result: AIExtractionResult) -> Dict[str, Any]:
        """Analyze individual source result."""
        analysis = {
            "source": source,
            "configured": result.error != "not configured",
            "success": result.error is None,
            "confidence": result.confidence,
            "questions_found": len(result.questions),
            "processing_time_ms": result.processing_time_ms,
            "cost_cents": result.cost_cents,
            "error": result.error,
            "question_types": {},
            "completeness_score": 0.0,
            "consistency_score": 0.0,
            "issues": []
        }

        if result.questions:
            # Analyze question types
            for question in result.questions:
                q_type = question.get('question_type', 'unknown')
                analysis["question_types"][q_type] = analysis["question_types"].get(q_type, 0) + 1

            # Assess completeness
            analysis["completeness_score"] = self._calculate_completeness_score(result.questions)

            # Check for consistency issues
            issues = self._find_consistency_issues(result.questions)
            analysis["issues"] = issues
            analysis["consistency_score"] = max(0, 1.0 - len(issues) * 0.1)

        return analysis

    def _cross_validate_sources(self, ai_results: Dict[str, AIExtractionResult]) -> Dict[str, Any]:
        """Cross-validate results between different AI sources."""
        validation = {
            "question_count_agreement": {},
            "type_classification_agreement": {},
            "text_similarity": {},
            "conflicts": []
        }

        sources = list(ai_results.keys())
        if len(sources) < 2:
            return validation

        # Compare question counts
        question_counts = {source: len(result.questions) for source, result in ai_results.items()}
        validation["question_count_agreement"] = question_counts

        # Find conflicts in question numbers/types
        for i, source1 in enumerate(sources):
            for source2 in sources[i + 1:]:
                conflicts = self._find_conflicts_between_sources(
                    ai_results[source1].questions,
                    ai_results[source2].questions
                )
                if conflicts:
                    validation["conflicts"].append({
                        "sources": [source1, source2],
                        "conflicts": conflicts
                    })

        return validation

    def _assess_overall_quality(
        self,
        pymupdf_data: Dict[str, Any],
        ai_results: Dict[str, AIExtractionResult],
        fusion_result: Optional[AIExtractionResult]
    ) -> Dict[str, Any]:
        """Assess overall extraction quality."""
        assessment = {
            "overall_score": 0.0,
            "pymupdf_baseline": {},
            "ai_enhancement": {},
            "fusion_quality": {},
            "coverage_analysis": {}
        }

        # Analyze PyMuPDF baseline
        content_elements = pymupdf_data.get("content_elements", [])
        text_elements = [elem for elem in content_elements if elem.get("type") == "text"]

        assessment["pymupdf_baseline"] = {
            "total_elements": len(content_elements),
            "text_elements": len(text_elements),
            "pages": pymupdf_data.get("document", {}).get("pages", 0),
            "fonts_detected": len(pymupdf_data.get("assets", {}).get("fonts", []))
        }

        # Assess AI enhancement
        if ai_results:
            total_ai_questions = sum(len(r.questions) for r in ai_results.values())
            avg_confidence = sum(r.confidence for r in ai_results.values()) / len(ai_results) if ai_results else 0

            assessment["ai_enhancement"] = {
                "total_questions_found": total_ai_questions,
                "average_confidence": round(avg_confidence, 2),
                "sources_successful": len([r for r in ai_results.values() if not r.error]),
                "enhancement_factor": total_ai_questions / max(len(text_elements), 1)
            }

        # Assess fusion quality if available
        if fusion_result:
            assessment["fusion_quality"] = {
                "confidence": fusion_result.confidence,
                "questions_fused": len(fusion_result.questions),
                "processing_time_ms": fusion_result.processing_time_ms,
                "fusion_effectiveness": self._calculate_fusion_effectiveness(ai_results, fusion_result)
            }

        # Calculate overall score
        scores = []
        if ai_results:
            scores.append(sum(r.confidence for r in ai_results.values()) / len(ai_results))
        if fusion_result:
            scores.append(fusion_result.confidence)

        assessment["overall_score"] = sum(scores) / len(scores) if scores else 0.0

        return assessment

    def _generate_recommendations(self, debug_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on debug analysis."""
        recommendations = []

        # Check for missing API keys
        for source, analysis in debug_report["source_analysis"].items():
            if not analysis["configured"]:
                recommendations.append({
                    "severity": "warning",
                    "category": "configuration",
                    "message": f"{source} is not configured - set API key to enable",
                    "action": f"Set {source.upper()}_API_KEY environment variable"
                })

        # Check for low confidence
        for source, analysis in debug_report["source_analysis"].items():
            if analysis["confidence"] < 0.5:
                recommendations.append({
                    "severity": "warning",
                    "category": "quality",
                    "message": f"{source} has low confidence ({analysis['confidence']:.2f})",
                    "action": "Review extraction prompts or try different model"
                })

        # Check for no questions found
        total_questions = sum(
            analysis["questions_found"]
            for analysis in debug_report["source_analysis"].values()
        )

        if total_questions == 0:
            recommendations.append({
                "severity": "critical",
                "category": "extraction",
                "message": "No questions found by any AI source",
                "action": "Check PDF content, improve prompts, or verify AI service connectivity"
            })

        # Check for conflicts
        conflicts = debug_report["cross_validation"].get("conflicts", [])
        if conflicts:
            recommendations.append({
                "severity": "info",
                "category": "consistency",
                "message": f"Found {len(conflicts)} conflicts between AI sources",
                "action": "Review fusion logic or manually validate conflicting extractions"
            })

        return recommendations

    def _calculate_completeness_score(self, questions: List[Dict[str, Any]]) -> float:
        """Calculate completeness score for questions."""
        if not questions:
            return 0.0

        complete_questions = 0
        for question in questions:
            has_number = bool(question.get('question_number'))
            has_stem = bool(question.get('stem_text', '').strip())
            has_type = question.get('question_type') != 'unknown'

            # For MCQ questions, check for options
            if question.get('question_type', '').startswith('mcq'):
                has_options = bool(question.get('options', {}))
                is_complete = has_number and has_stem and has_type and has_options
            else:
                is_complete = has_number and has_stem and has_type

            if is_complete:
                complete_questions += 1

        return complete_questions / len(questions)

    def _find_consistency_issues(self, questions: List[Dict[str, Any]]) -> List[str]:
        """Find consistency issues within a set of questions."""
        issues = []

        # Check for duplicate question numbers
        question_numbers = [q.get('question_number') for q in questions if q.get('question_number')]
        if len(question_numbers) != len(set(question_numbers)):
            issues.append("Duplicate question numbers detected")

        # Check for empty stems
        empty_stems = sum(1 for q in questions if not q.get('stem_text', '').strip())
        if empty_stems > 0:
            issues.append(f"{empty_stems} questions have empty stem text")

        # Check for inconsistent option formats
        mcq_questions = [q for q in questions if q.get('question_type', '').startswith('mcq')]
        if mcq_questions:
            option_formats = set()
            for q in mcq_questions:
                options = q.get('options', {})
                if options:
                    option_formats.add(tuple(sorted(options.keys())))

            if len(option_formats) > 1:
                issues.append("Inconsistent option labeling across MCQ questions")

        return issues

    def _find_conflicts_between_sources(
        self,
        questions1: List[Dict[str, Any]],
        questions2: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find conflicts between two sets of questions."""
        conflicts = []

        # Create maps by question number for comparison
        q1_map = {q.get('question_number'): q for q in questions1 if q.get('question_number')}
        q2_map = {q.get('question_number'): q for q in questions2 if q.get('question_number')}

        common_numbers = set(q1_map.keys()) & set(q2_map.keys())

        for q_num in common_numbers:
            q1, q2 = q1_map[q_num], q2_map[q_num]

            # Check for type conflicts
            if q1.get('question_type') != q2.get('question_type'):
                conflicts.append({
                    "question_number": q_num,
                    "type": "question_type_mismatch",
                    "values": [q1.get('question_type'), q2.get('question_type')]
                })

            # Check for stem text significant differences
            stem1 = q1.get('stem_text', '').strip()
            stem2 = q2.get('stem_text', '').strip()
            if stem1 and stem2 and self._text_similarity(stem1, stem2) < 0.7:
                conflicts.append({
                    "question_number": q_num,
                    "type": "stem_text_difference",
                    "similarity": self._text_similarity(stem1, stem2)
                })

        return conflicts

    def _calculate_fusion_effectiveness(
        self,
        ai_results: Dict[str, AIExtractionResult],
        fusion_result: AIExtractionResult
    ) -> float:
        """Calculate how effective the fusion process was."""
        if not ai_results or not fusion_result.questions:
            return 0.0

        total_source_questions = sum(len(r.questions) for r in ai_results.values())
        fusion_questions = len(fusion_result.questions)

        if total_source_questions == 0:
            return 0.0

        # Effectiveness = (fused questions) / (average source questions)
        avg_source_questions = total_source_questions / len(ai_results)
        effectiveness = fusion_questions / max(avg_source_questions, 1)

        return min(1.0, effectiveness)

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity (Jaccard similarity of words)."""
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _get_timestamp(self) -> str:
        """Get current timestamp for reports."""
        from ...utils.time import isoformat, utc_now
        return isoformat(utc_now())

    def export_debug_report(self, debug_report: Dict[str, Any], file_path: str) -> None:
        """Export debug report to JSON file."""
        try:
            with open(file_path, 'w') as f:
                json.dump(debug_report, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Debug report exported to {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to export debug report: {e}")

    def get_debug_summary(self, debug_report: Dict[str, Any]) -> Dict[str, Any]:
        """Get a concise summary of debug report for quick overview."""
        return {
            "run_id": debug_report.get("run_id"),
            "overall_quality": debug_report.get("quality_assessment", {}).get("overall_score", 0),
            "sources_analyzed": len(debug_report.get("source_analysis", {})),
            "total_questions": sum(
                analysis.get("questions_found", 0)
                for analysis in debug_report.get("source_analysis", {}).values()
            ),
            "critical_issues": len([
                r for r in debug_report.get("recommendations", [])
                if r.get("severity") == "critical"
            ]),
            "warnings": len([
                r for r in debug_report.get("recommendations", [])
                if r.get("severity") == "warning"
            ]),
            "top_recommendation": (
                debug_report.get("recommendations", [{}])[0].get("message", "No issues found")
                if debug_report.get("recommendations") else "No issues found"
            )
        }