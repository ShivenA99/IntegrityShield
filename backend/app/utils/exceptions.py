from __future__ import annotations


class PipelineError(Exception):
    """Base class for pipeline-related errors."""


class StageAlreadyCompleted(PipelineError):
    pass


class StageExecutionFailed(PipelineError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"Stage '{stage}' failed: {message}")
        self.stage = stage
        self.message = message


class InvalidStageTransition(PipelineError):
    pass


class ResourceNotFound(PipelineError):
    pass


class ExternalServiceError(PipelineError):
    pass
