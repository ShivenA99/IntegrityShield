"""Test script for StreamlinedMappingService with mock data."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
from app.extensions import db
from app.config import get_config
from app.services.mapping.streamlined_mapping_service import StreamlinedMappingService
from app.models import QuestionManipulation, PipelineRun
from app.utils.logging import get_logger

logger = get_logger(__name__)


def setup_app():
    """Set up Flask app for testing."""
    app = Flask(__name__)
    config = get_config("testing")
    app.config.from_object(config)
    
    db.init_app(app)
    
    return app


async def test_streamlined_service():
    """Test the streamlined mapping service with mock data."""
    app = setup_app()
    
    with app.app_context():
        # Find a test run with structured data
        test_run_id = "79eb0ccf-8388-4df8-8297-479708b0073f"
        structured_path = Path(f"data/pipeline_runs/{test_run_id}/structured.json")
        
        if not structured_path.exists():
            logger.error(f"Test data not found: {structured_path}")
            return
        
        # Load structured data
        with open(structured_path, "r") as f:
            structured = json.load(f)
        
        logger.info(f"Loaded structured data for run {test_run_id}")
        logger.info(f"Questions in structured data: {len(structured.get('questions', []))}")
        
        # Check if run exists in DB
        run = PipelineRun.query.get(test_run_id)
        if not run:
            logger.warning(f"Run {test_run_id} not found in DB, creating test run...")
            run = PipelineRun(
                id=test_run_id,
                status="running",
                pipeline_config={"enhancement_methods": ["latex_dual_layer"]},
            )
            db.session.add(run)
            db.session.commit()
        
        # Get questions for this run
        questions = QuestionManipulation.query.filter_by(
            pipeline_run_id=test_run_id
        ).all()
        
        logger.info(f"Found {len(questions)} questions in DB")
        
        if not questions:
            logger.warning("No questions found in DB. Cannot test generation.")
            return
        
        # Test single question generation
        logger.info("Testing single question generation...")
        service = StreamlinedMappingService()
        
        # Test with first question
        test_question = questions[0]
        logger.info(f"Testing with question {test_question.question_number} (ID: {test_question.id})")
        
        try:
            result = await service.generate_mappings_for_single_question(
                run_id=test_run_id,
                question_id=test_question.id,
            )
            
            logger.info(f"Generation result: {result.get('status')}")
            if result.get("status") == "success":
                logger.info(f"✓ Successfully generated mapping for question {test_question.question_number}")
                logger.info(f"  Valid mapping: {result.get('valid_mapping') is not None}")
            else:
                logger.warning(f"✗ Generation failed: {result.get('error')}")
                logger.warning(f"  Failure rationales: {result.get('failure_rationales', [])}")
            
            # Check status
            status = service.get_question_status(test_run_id, test_question.id)
            if status:
                logger.info(f"Status for question {test_question.question_number}:")
                logger.info(f"  Status: {status.status}")
                logger.info(f"  Retry count: {status.retry_count}")
                logger.info(f"  Mapping sets generated: {len(status.mapping_sets_generated)}")
                logger.info(f"  Validation outcomes: {len(status.validation_outcomes)}")
                logger.info(f"  Failure rationales: {len(status.failure_rationales)}")
            
        except Exception as e:
            logger.error(f"Error testing single question: {e}", exc_info=True)
        
        # Test status retrieval
        logger.info("\nTesting status retrieval...")
        all_statuses = service.get_all_statuses(test_run_id)
        logger.info(f"Found {len(all_statuses)} question statuses")
        
        for q_id, status in all_statuses.items():
            logger.info(f"  Question {status.question_number}: {status.status}")
        
        logger.info("\n✓ Test completed!")


if __name__ == "__main__":
    # Set up environment
    os.environ.setdefault("FLASK_ENV", "testing")
    
    # Run async test
    asyncio.run(test_streamlined_service())









