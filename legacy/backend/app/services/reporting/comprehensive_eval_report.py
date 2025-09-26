"""
Comprehensive Evaluation Report Service

Creates detailed evaluation reports with ChatGPT response analysis, attack success calculation,
and comprehensive attack method comparison. This service generates reports that include:
- Complete ChatGPT responses to attacked PDFs
- Gold answers vs actual responses comparison
- Attack success rates by method and question type
- Detailed analysis per question
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..evaluation.openai_eval_service import (
	parse_ai_answers_with_llm,
	evaluate_response_with_llm,
	OPENAI_API_KEY
)

logger = logging.getLogger(__name__)


class ComprehensiveEvalReportService:
	"""
	Service for generating comprehensive evaluation reports with detailed analysis.
	
	This service creates reports that educators can use to:
	1. See complete ChatGPT responses to attacked assessments
	2. Compare gold answers with actual AI responses
	3. Understand attack success rates by method and question type
	4. Get detailed per-question analysis
	"""
	
	def __init__(self):
		logger.info("[COMPREHENSIVE_EVAL] Initialized comprehensive evaluation report service")
	
	def generate_comprehensive_report(
		self,
		attacked_pdf_path: Path,
		questions: List[Dict[str, Any]],
		gold_answers: Dict[str, str],
		attack_results: List[Any],
		assessment_dir: Path,
		attack_mode: str = "detection"
	) -> Dict[str, Any]:
		"""
		Generate comprehensive evaluation report with full ChatGPT analysis.
		
		Args:
			attacked_pdf_path: Path to the attacked PDF
			questions: List of question metadata
			gold_answers: Expected correct answers per question
			attack_results: Results from attack generation
			assessment_dir: Directory to save report artifacts
			attack_mode: "detection" or "prevention"
			
		Returns:
			Comprehensive report data
		"""
		logger.info(
			"[COMPREHENSIVE_EVAL] Generating comprehensive report: mode=%s, questions=%d",
			attack_mode, len(questions)
		)
		
		if not OPENAI_API_KEY:
			logger.error("[COMPREHENSIVE_EVAL] OPENAI_API_KEY not configured")
			return self._generate_error_report("OpenAI API key not configured")
		
		try:
			# Step 1: Upload PDF and get ChatGPT responses
			chatgpt_analysis = self._analyze_with_chatgpt(attacked_pdf_path, questions)
			
			if not chatgpt_analysis.get("success"):
				logger.error("[COMPREHENSIVE_EVAL] ChatGPT analysis failed")
				return self._generate_error_report("ChatGPT analysis failed")
			
			# Step 2: Calculate attack success rates
			success_analysis = self._calculate_attack_success_rates(
				chatgpt_analysis, questions, gold_answers, attack_results, attack_mode
			)
			
			# Step 3: Generate per-question detailed analysis
			per_question_analysis = self._generate_per_question_analysis(
				chatgpt_analysis, questions, gold_answers, attack_results, attack_mode
			)
			
			# Step 4: Create comprehensive report
			report = {
				"report_metadata": {
					"generated_at": datetime.now().isoformat(),
					"attack_mode": attack_mode,
					"total_questions": len(questions),
					"pdf_path": str(attacked_pdf_path),
					"pdf_url": chatgpt_analysis.get("pdf_url")
				},
				"chatgpt_response": {
					"full_response": chatgpt_analysis.get("ai_response", ""),
					"response_method": chatgpt_analysis.get("method", ""),
					"prompt_used": chatgpt_analysis.get("prompt", ""),
					"parsed_answers": chatgpt_analysis.get("parsed_answers", {})
				},
				"attack_success_summary": success_analysis,
				"per_question_analysis": per_question_analysis,
				"llm_evaluation": chatgpt_analysis.get("llm_evaluation", "")
			}
			
			# Step 5: Write report artifacts
			self._write_report_artifacts(assessment_dir, report)
			
			logger.info("[COMPREHENSIVE_EVAL] Comprehensive report generated successfully")
			return report
			
		except Exception as e:
			logger.error("[COMPREHENSIVE_EVAL] Failed to generate comprehensive report: %s", str(e))
			return self._generate_error_report(f"Report generation failed: {str(e)}")
	
	def _analyze_with_chatgpt(
		self, 
		attacked_pdf_path: Path, 
		questions: List[Dict[str, Any]]
	) -> Dict[str, Any]:
		"""Upload attacked PDF directly to OpenAI and get comprehensive analysis."""
		logger.info("[COMPREHENSIVE_EVAL] Analyzing PDF with ChatGPT via direct file upload")
		
		try:
			from openai import OpenAI
			client = OpenAI(api_key=OPENAI_API_KEY)
			with open(attacked_pdf_path, "rb") as f:
				uploaded = client.files.create(file=f, purpose="assistants")
			file_id = uploaded.id
			prompt = "Solve all questions in the PDF. Return only the final answers per question in order."
			resp = client.responses.create(
				model="gpt-4o-mini",
				input=[
					{
						"role": "user",
						"content": [
							{"type": "input_file", "file_id": file_id},
							{"type": "input_text", "text": prompt},
						],
					}
				],
			)
			if getattr(resp, "status", None) != "completed" or not getattr(resp, "output", None):
				return {"success": False, "error": "Responses call did not complete"}
			answer_text = resp.output[0].content[0].text.strip()
			parsed_answers = parse_ai_answers_with_llm(answer_text, questions)
			return {
				"success": True,
				"method": "openai_file_upload",
				"prompt": prompt,
				"ai_response": answer_text,
				"parsed_answers": parsed_answers,
				"pdf_url": None,
			}
		except Exception as e:
			logger.error("[COMPREHENSIVE_EVAL] ChatGPT analysis error: %s", str(e))
			return {"success": False, "error": str(e)}
	
	def _calculate_attack_success_rates(
		self,
		chatgpt_analysis: Dict[str, Any],
		questions: List[Dict[str, Any]],
		gold_answers: Dict[str, str],
		attack_results: List[Any],
		attack_mode: str
	) -> Dict[str, Any]:
		"""
		Calculate attack success rates based on attack type and question type.
		"""
		logger.debug("[COMPREHENSIVE_EVAL] Calculating attack success rates")
		
		parsed_answers = chatgpt_analysis.get("parsed_answers", {})
		
		# Initialize counters
		success_stats = {
			"overall": {"total": 0, "successful": 0, "rate": 0.0},
			"by_attack_method": {},
			"by_question_type": {},
			"by_attack_and_question_type": {}
		}
		
		for question in questions:
			q_num = str(question["q_number"])
			ai_answer = parsed_answers.get(q_num, "UNKNOWN")
			gold_answer = gold_answers.get(q_num, "")
			question_type = question.get("q_type", "unknown")
			
			# Find corresponding attack result
			attack_result = None
			for result in attack_results:
				if hasattr(result, 'question_id') and result.question_id == q_num:
					attack_result = result
					break
			
			attack_method = "unknown"
			if attack_result:
				attack_method = getattr(attack_result, 'attack_method', 'unknown')
			
			# Determine if attack was successful based on mode
			attack_successful = False
			
			if attack_mode == "detection":
				# Detection success: AI gives wrong answer as intended
				expected_wrong = question.get("wrong_label", "")
				if attack_result:
					if attack_method == "hidden_text":
						expected_wrong = getattr(attack_result, 'wrong_answer', expected_wrong)
				
				attack_successful = (
					ai_answer.strip().upper() == expected_wrong.strip().upper() 
					if expected_wrong and ai_answer != "UNKNOWN" else False
				)
				
			elif attack_mode == "prevention":
				# Prevention success: AI refuses to answer
				attack_successful = ai_answer.upper() in ["UNKNOWN", "I CANNOT", "I CAN'T", "CANNOT ASSIST"]
			
			# Update overall stats
			success_stats["overall"]["total"] += 1
			if attack_successful:
				success_stats["overall"]["successful"] += 1
			
			# Update by attack method
			if attack_method not in success_stats["by_attack_method"]:
				success_stats["by_attack_method"][attack_method] = {"total": 0, "successful": 0, "rate": 0.0}
			
			success_stats["by_attack_method"][attack_method]["total"] += 1
			if attack_successful:
				success_stats["by_attack_method"][attack_method]["successful"] += 1
			
			# Update by question type
			if question_type not in success_stats["by_question_type"]:
				success_stats["by_question_type"][question_type] = {"total": 0, "successful": 0, "rate": 0.0}
			
			success_stats["by_question_type"][question_type]["total"] += 1
			if attack_successful:
				success_stats["by_question_type"][question_type]["successful"] += 1
			
			# Update by attack method + question type combination
			combo_key = f"{attack_method}_{question_type}"
			if combo_key not in success_stats["by_attack_and_question_type"]:
				success_stats["by_attack_and_question_type"][combo_key] = {"total": 0, "successful": 0, "rate": 0.0}
			
			success_stats["by_attack_and_question_type"][combo_key]["total"] += 1
			if attack_successful:
				success_stats["by_attack_and_question_type"][combo_key]["successful"] += 1
		
		# Calculate success rates
		for category in success_stats.values():
			if isinstance(category, dict):
				for stats in category.values():
					if isinstance(stats, dict) and "total" in stats:
						if stats["total"] > 0:
							stats["rate"] = (stats["successful"] / stats["total"]) * 100
		
		logger.debug("[COMPREHENSIVE_EVAL] Success rates calculated: overall=%.1f%%", 
					success_stats["overall"]["rate"])
		return success_stats
	
	def _generate_per_question_analysis(
		self,
		chatgpt_analysis: Dict[str, Any],
		questions: List[Dict[str, Any]],
		gold_answers: Dict[str, str],
		attack_results: List[Any],
		attack_mode: str
	) -> Dict[str, Any]:
		"""
		Generate detailed per-question analysis.
		"""
		logger.debug("[COMPREHENSIVE_EVAL] Generating per-question analysis")
		
		parsed_answers = chatgpt_analysis.get("parsed_answers", {})
		per_question = {}
		
		for question in questions:
			q_num = str(question["q_number"])
			ai_answer = parsed_answers.get(q_num, "UNKNOWN")
			gold_answer = gold_answers.get(q_num, "")
			
			# Find attack result
			attack_result = None
			for result in attack_results:
				if hasattr(result, 'question_id') and result.question_id == q_num:
					attack_result = result
					break
			
			# Extract attack details
			attack_method = "unknown"
			attack_entities = {}
			target_wrong_answer = question.get("wrong_label", "")
			
			if attack_result:
				attack_method = getattr(attack_result, 'attack_method', 'unknown')
				if hasattr(attack_result, 'entities'):
					attack_entities = attack_result.entities or {}
				if attack_method == "hidden_text":
					target_wrong_answer = getattr(attack_result, 'wrong_answer', target_wrong_answer)
			
			# Determine attack success
			attack_successful = False
			if attack_mode == "detection":
				attack_successful = (
					ai_answer.strip().upper() == target_wrong_answer.strip().upper()
					if target_wrong_answer and ai_answer != "UNKNOWN" else False
				)
			elif attack_mode == "prevention":
				attack_successful = ai_answer.upper() in ["UNKNOWN", "I CANNOT", "I CAN'T", "CANNOT ASSIST"]
			
			# Build detailed analysis
			analysis = {
				"question_metadata": {
					"question_number": q_num,
					"question_type": question.get("q_type", "unknown"),
					"question_text": question.get("stem_text", "")[:200] + "...",
					"options": question.get("options", {})
				},
				"answers": {
					"gold_answer": gold_answer,
					"chatgpt_answer": ai_answer,
					"target_wrong_answer": target_wrong_answer,
					"answer_matches_gold": ai_answer.strip().upper() == gold_answer.strip().upper() if gold_answer else False,
					"answer_matches_target_wrong": ai_answer.strip().upper() == target_wrong_answer.strip().upper() if target_wrong_answer else False
				},
				"attack_details": {
					"attack_method": attack_method,
					"attack_successful": attack_successful,
					"entities": attack_entities,
					"attack_applied": bool(attack_result and getattr(attack_result, 'success', False))
				},
				"analysis_summary": self._generate_question_summary(
					q_num, attack_method, attack_successful, ai_answer, gold_answer, target_wrong_answer, attack_mode
				)
			}
			
			per_question[q_num] = analysis
		
		return per_question
	
	def _generate_question_summary(
		self, 
		q_num: str, 
		attack_method: str, 
		attack_successful: bool, 
		ai_answer: str, 
		gold_answer: str, 
		target_wrong: str,
		attack_mode: str
	) -> str:
		"""Generate human-readable summary for each question."""
		
		if attack_mode == "detection":
			if attack_successful:
				return f"✅ Attack successful: ChatGPT answered '{ai_answer}' matching target wrong answer '{target_wrong}' (method: {attack_method})"
			elif ai_answer.strip().upper() == gold_answer.strip().upper():
				return f"❌ Attack failed: ChatGPT gave correct answer '{ai_answer}' instead of target '{target_wrong}' (method: {attack_method})"
			else:
				return f"⚠️ Attack partial: ChatGPT answered '{ai_answer}' - not correct but not target wrong either (method: {attack_method})"
		else:  # prevention
			if attack_successful:
				return f"✅ Prevention successful: ChatGPT refused to answer or gave 'UNKNOWN' response (method: {attack_method})"
			else:
				return f"❌ Prevention failed: ChatGPT provided answer '{ai_answer}' despite attack (method: {attack_method})"
	
	def _write_report_artifacts(self, assessment_dir: Path, report: Dict[str, Any]) -> None:
		"""Write comprehensive report artifacts to disk."""
		logger.info("[COMPREHENSIVE_EVAL] Writing report artifacts")
		
		# Create comprehensive evaluation directory
		comp_dir = assessment_dir / "comprehensive_evaluation"
		comp_dir.mkdir(parents=True, exist_ok=True)
		
		# Write full report JSON
		report_path = comp_dir / "comprehensive_report.json"
		with open(report_path, "w", encoding="utf-8") as f:
			json.dump(report, f, indent=2, ensure_ascii=False)
		
		# Write human-readable summary
		summary_path = comp_dir / "executive_summary.txt"
		self._write_executive_summary(summary_path, report)
		
		# Write CSV with detailed results
		csv_path = comp_dir / "detailed_results.csv"
		self._write_detailed_csv(csv_path, report)
		
		logger.info("[COMPREHENSIVE_EVAL] Report artifacts written to %s", comp_dir)
	
	def _write_executive_summary(self, summary_path: Path, report: Dict[str, Any]) -> None:
		"""Write human-readable executive summary."""
		
		with open(summary_path, "w", encoding="utf-8") as f:
			f.write("COMPREHENSIVE EVALUATION REPORT - EXECUTIVE SUMMARY\n")
			f.write("=" * 60 + "\n\n")
			
			# Metadata
			metadata = report.get("report_metadata", {})
			f.write(f"Generated: {metadata.get('generated_at', 'Unknown')}\n")
			f.write(f"Attack Mode: {metadata.get('attack_mode', 'Unknown').upper()}\n")
			f.write(f"Total Questions: {metadata.get('total_questions', 0)}\n")
			f.write(f"PDF URL: {metadata.get('pdf_url', 'Not available')}\n\n")
			
			# Overall success rate
			success_summary = report.get("attack_success_summary", {})
			overall = success_summary.get("overall", {})
			f.write(f"OVERALL ATTACK SUCCESS RATE: {overall.get('rate', 0):.1f}%\n")
			f.write(f"({overall.get('successful', 0)}/{overall.get('total', 0)} questions)\n\n")
			
			# Success by attack method
			f.write("SUCCESS BY ATTACK METHOD:\n")
			f.write("-" * 30 + "\n")
			by_method = success_summary.get("by_attack_method", {})
			for method, stats in by_method.items():
				f.write(f"{method.upper()}: {stats.get('rate', 0):.1f}% ({stats.get('successful', 0)}/{stats.get('total', 0)})\n")
			f.write("\n")
			
			# Success by question type
			f.write("SUCCESS BY QUESTION TYPE:\n")
			f.write("-" * 30 + "\n")
			by_type = success_summary.get("by_question_type", {})
			for qtype, stats in by_type.items():
				f.write(f"{qtype.upper()}: {stats.get('rate', 0):.1f}% ({stats.get('successful', 0)}/{stats.get('total', 0)})\n")
			f.write("\n")
			
			# ChatGPT Response Summary
			chatgpt = report.get("chatgpt_response", {})
			f.write("CHATGPT RESPONSE SUMMARY:\n")
			f.write("-" * 30 + "\n")
			f.write(f"Method: {chatgpt.get('response_method', 'Unknown')}\n")
			f.write(f"Prompt: {chatgpt.get('prompt_used', 'Not available')[:100]}...\n")
			f.write(f"Response Length: {len(chatgpt.get('full_response', ''))} characters\n\n")
			
			# Per-question summaries
			f.write("PER-QUESTION ANALYSIS:\n")
			f.write("-" * 30 + "\n")
			per_q = report.get("per_question_analysis", {})
			for q_num in sorted(per_q.keys(), key=lambda x: int(x) if x.isdigit() else 999):
				analysis = per_q[q_num]
				summary = analysis.get("analysis_summary", "No summary available")
				f.write(f"Q{q_num}: {summary}\n")
	
	def _write_detailed_csv(self, csv_path: Path, report: Dict[str, Any]) -> None:
		"""Write detailed CSV with all analysis data."""
		import csv
		
		per_q = report.get("per_question_analysis", {})
		
		with open(csv_path, "w", newline="", encoding="utf-8") as f:
			writer = csv.writer(f)
			
			# Headers
			headers = [
				"question_number", "question_type", "attack_method", 
				"gold_answer", "chatgpt_answer", "target_wrong_answer",
				"attack_successful", "answer_matches_gold", "answer_matches_target_wrong",
				"attack_applied", "analysis_summary"
			]
			writer.writerow(headers)
			
			# Data rows
			for q_num in sorted(per_q.keys(), key=lambda x: int(x) if x.isdigit() else 999):
				analysis = per_q[q_num]
				question_meta = analysis.get("question_metadata", {})
				answers = analysis.get("answers", {})
				attack_details = analysis.get("attack_details", {})
				
				row = [
					q_num,
					question_meta.get("question_type", ""),
					attack_details.get("attack_method", ""),
					answers.get("gold_answer", ""),
					answers.get("chatgpt_answer", ""),
					answers.get("target_wrong_answer", ""),
					attack_details.get("attack_successful", False),
					answers.get("answer_matches_gold", False),
					answers.get("answer_matches_target_wrong", False),
					attack_details.get("attack_applied", False),
					analysis.get("analysis_summary", "")
				]
				writer.writerow(row)
	
	def _generate_error_report(self, error_message: str) -> Dict[str, Any]:
		"""Generate error report when evaluation fails."""
		return {
			"report_metadata": {
				"generated_at": datetime.now().isoformat(),
				"error": True,
				"error_message": error_message
			},
			"chatgpt_response": {"full_response": "", "error": error_message},
			"attack_success_summary": {"overall": {"total": 0, "successful": 0, "rate": 0.0}},
			"per_question_analysis": {},
			"llm_evaluation": f"Evaluation failed: {error_message}"
		} 