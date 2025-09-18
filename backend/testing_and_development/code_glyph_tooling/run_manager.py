#!/usr/bin/env python3
"""
Run Manager for Malicious Font Pipeline
Handles run organization, output management, and file naming.
"""

import os
import sys
import datetime
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class RunOutput:
    """Information about a pipeline run output."""
    run_id: str
    input_string: str
    input_entity: str
    output_entity: str
    pdf_path: str
    metadata_path: str
    font_paths: List[str]
    timestamp: str
    strategy_type: str
    fonts_created: int

class RunManager:
    """
    Manages pipeline runs and organizes outputs.
    """
    
    def __init__(self):
        self.runs_dir = "output/runs"
        self.ensure_runs_directory()
    
    def ensure_runs_directory(self) -> None:
        """Ensure the runs directory exists."""
        os.makedirs(self.runs_dir, exist_ok=True)
        logger.info(f"✓ Runs directory ensured: {self.runs_dir}")
    
    def create_run_id(self) -> str:
        """
        Create a unique run identifier.
        
        Returns:
            str: Unique run ID
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}"
        logger.info(f"Created run ID: {run_id}")
        return run_id
    
    def create_run_directory(self, run_id: str) -> str:
        """
        Create directory structure for a run.
        
        Args:
            run_id (str): Unique run identifier
            
        Returns:
            str: Path to the run directory
        """
        run_dir = os.path.join(self.runs_dir, run_id)
        os.makedirs(run_dir, exist_ok=True)
        
        # Create subdirectories
        subdirs = ["fonts", "pdfs", "metadata"]
        for subdir in subdirs:
            os.makedirs(os.path.join(run_dir, subdir), exist_ok=True)
        
        logger.info(f"✓ Created run directory structure: {run_dir}")
        return run_dir
    
    def organize_outputs(self, run_id: str, files: List[str]) -> RunOutput:
        """
        Organize output files for a run.
        
        Args:
            run_id (str): Unique run identifier
            files (List[str]): List of generated file paths
            
        Returns:
            RunOutput: Organized run output information
        """
        # This would be called after the pipeline completes
        # For now, we'll create a placeholder
        run_output = RunOutput(
            run_id=run_id,
            input_string="",  # Will be filled by pipeline
            input_entity="",  # Will be filled by pipeline
            output_entity="",  # Will be filled by pipeline
            pdf_path="",  # Will be filled by pipeline
            metadata_path="",  # Will be filled by pipeline
            font_paths=files,
            timestamp=datetime.datetime.now().isoformat(),
            strategy_type="",  # Will be filled by pipeline
            fonts_created=len([f for f in files if f.endswith('.ttf')])
        )
        
        logger.info(f"✓ Organized outputs for run {run_id}: {len(files)} file(s)")
        return run_output
    
    def generate_run_summary(self, run_output: RunOutput) -> Dict:
        """
        Generate a summary of a pipeline run.
        
        Args:
            run_output (RunOutput): The run output information
            
        Returns:
            Dict: Run summary
        """
        summary = {
            "run_id": run_output.run_id,
            "timestamp": run_output.timestamp,
            "input_string": run_output.input_string,
            "input_entity": run_output.input_entity,
            "output_entity": run_output.output_entity,
            "strategy_type": run_output.strategy_type,
            "fonts_created": run_output.fonts_created,
            "files": {
                "pdf": run_output.pdf_path,
                "metadata": run_output.metadata_path,
                "fonts": run_output.font_paths
            },
            "visual_result": run_output.input_string.replace(run_output.input_entity, run_output.output_entity),
            "actual_result": run_output.input_string
        }
        
        return summary
    
    def list_runs(self) -> List[Dict]:
        """
        List all pipeline runs.
        
        Returns:
            List[Dict]: List of run information
        """
        runs = []
        
        if not os.path.exists(self.runs_dir):
            return runs
        
        for run_id in os.listdir(self.runs_dir):
            run_dir = os.path.join(self.runs_dir, run_id)
            if os.path.isdir(run_dir):
                run_info = self._get_run_info(run_id, run_dir)
                if run_info:
                    runs.append(run_info)
        
        # Sort by timestamp (newest first)
        runs.sort(key=lambda x: x["timestamp"], reverse=True)
        
        logger.info(f"Found {len(runs)} run(s)")
        return runs
    
    def _get_run_info(self, run_id: str, run_dir: str) -> Optional[Dict]:
        """
        Get information about a specific run.
        
        Args:
            run_id (str): The run ID
            run_dir (str): Path to the run directory
            
        Returns:
            Optional[Dict]: Run information, or None if invalid
        """
        try:
            # Check for metadata files
            metadata_dir = os.path.join(run_dir, "metadata")
            if not os.path.exists(metadata_dir):
                return None
            
            metadata_files = [f for f in os.listdir(metadata_dir) if f.endswith('.json')]
            if not metadata_files:
                return None
            
            # Use the first metadata file
            metadata_path = os.path.join(metadata_dir, metadata_files[0])
            
            import json
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Count files
            fonts_dir = os.path.join(run_dir, "fonts")
            pdfs_dir = os.path.join(run_dir, "pdfs")
            
            font_count = len([f for f in os.listdir(fonts_dir) if f.endswith('.ttf')]) if os.path.exists(fonts_dir) else 0
            pdf_count = len([f for f in os.listdir(pdfs_dir) if f.endswith('.pdf')]) if os.path.exists(pdfs_dir) else 0
            
            run_info = {
                "run_id": run_id,
                "timestamp": metadata.get("timestamp", ""),
                "input_entity": metadata.get("input_entity", ""),
                "output_entity": metadata.get("output_entity", ""),
                "fonts_created": font_count,
                "pdfs_created": pdf_count,
                "strategy_type": metadata.get("font_configs", [{}])[0].get("description", ""),
                "run_dir": run_dir
            }
            
            return run_info
            
        except Exception as e:
            logger.warning(f"Failed to get info for run {run_id}: {e}")
            return None
    
    def get_run_details(self, run_id: str) -> Optional[Dict]:
        """
        Get detailed information about a specific run.
        
        Args:
            run_id (str): The run ID
            
        Returns:
            Optional[Dict]: Detailed run information, or None if not found
        """
        run_dir = os.path.join(self.runs_dir, run_id)
        if not os.path.exists(run_dir):
            return None
        
        return self._get_run_info(run_id, run_dir)
    
    def cleanup_old_runs(self, days_to_keep: int = 30) -> int:
        """
        Clean up old runs to save disk space.
        
        Args:
            days_to_keep (int): Number of days to keep runs
            
        Returns:
            int: Number of runs cleaned up
        """
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_to_keep)
        cleaned_count = 0
        
        for run_info in self.list_runs():
            try:
                run_timestamp = datetime.datetime.fromisoformat(run_info["timestamp"].replace('Z', '+00:00'))
                if run_timestamp < cutoff_date:
                    run_dir = run_info["run_dir"]
                    import shutil
                    shutil.rmtree(run_dir)
                    logger.info(f"Cleaned up old run: {run_info['run_id']}")
                    cleaned_count += 1
            except Exception as e:
                logger.warning(f"Failed to clean up run {run_info['run_id']}: {e}")
        
        logger.info(f"✓ Cleaned up {cleaned_count} old run(s)")
        return cleaned_count

def create_run_manager() -> RunManager:
    """
    Create a run manager instance.
    
    Returns:
        RunManager: Run manager instance
    """
    return RunManager()

if __name__ == "__main__":
    # Test the run manager
    manager = create_run_manager()
    
    # List existing runs
    runs = manager.list_runs()
    print(f"Found {len(runs)} existing run(s)")
    
    for run in runs:
        print(f"  {run['run_id']}: {run['input_entity']} → {run['output_entity']} ({run['fonts_created']} fonts)")
    
    # Create a new run
    run_id = manager.create_run_id()
    run_dir = manager.create_run_directory(run_id)
    print(f"Created new run: {run_id}")
    print(f"Run directory: {run_dir}") 