"""
Report Generator for LLM responses
Formats the results into a readable report
"""
from typing import Dict, List
from datetime import datetime


class ReportGenerator:
    """Generate formatted reports from LLM responses"""
    
    def generate(self, results: Dict, output_path: str = "report.txt"):
        """Generate formatted report from structured results"""
        doc = results.get("document", {})
        questions = results.get("questions", {}).get("items", [])
        
        with open(output_path, "w", encoding="utf-8") as f:
            # Header
            f.write("=" * 80 + "\n")
            f.write("ASSESSMENT REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            # Assessment details
            asses_details = doc.get("asses_details", {})
            f.write(f"Assessment Name: {doc.get('id', 'N/A')}\n")
            f.write(f"Domain: {asses_details.get('dom', 'N/A')}\n")
            f.write(f"Subject: {asses_details.get('sub', 'N/A')}\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Question-wise report
            f.write("=" * 80 + "\n")
            f.write("QUESTION-WISE REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            for q_item in questions:
                qid = q_item.get('qid', 'N/A')
                q_text = q_item.get('q', 'N/A')
                
                f.write(f"\nQuestion {qid}\n")
                f.write("-" * 80 + "\n")
                f.write(f"Question Text: {q_text}\n\n")
                
                # Group answers by model and prompt
                answers_by_model = {}
                for answer in q_item.get("answers", []):
                    model = answer.get("model_name", "UNKNOWN")
                    prompt_used = answer.get("prompt", "")
                    
                    if model not in answers_by_model:
                        answers_by_model[model] = {}
                    if prompt_used not in answers_by_model[model]:
                        answers_by_model[model][prompt_used] = []
                    
                    if answer.get("success", False) and answer.get("answer"):
                        answers_by_model[model][prompt_used].append(answer.get("answer"))
                    elif not answer.get("success"):
                        answers_by_model[model][prompt_used].append(
                            f"Error: {answer.get('error', 'Unknown error')}"
                        )
                
                # Write answers grouped by model
                for model in ["OPENAI", "ANTHROPIC", "GOOGLE"]:
                    model_key = model.lower() if model == "OPENAI" else (
                        "anthropic" if model == "ANTHROPIC" else "google"
                    )
                    
                    if model_key in answers_by_model:
                        f.write(f"{model:15} ")
                        # Aggregate all responses for this model
                        all_responses = []
                        for prompt_responses in answers_by_model[model_key].values():
                            all_responses.extend(prompt_responses)
                        
                        # Show up to 3 responses or aggregate
                        if all_responses:
                            # Take first response or combine
                            response_text = str(all_responses[0])
                            if len(response_text) > 200:
                                response_text = response_text[:200] + "..."
                            f.write(f"{response_text}\n")
                        else:
                            f.write("N/A\n")
                    else:
                        f.write(f"{model:15} N/A\n")
                
                f.write("\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 80 + "\n")

