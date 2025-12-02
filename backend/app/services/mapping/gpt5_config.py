"""Configuration for GPT-5 mapping generation service."""

import os

# GPT-5 API Configuration
GPT5_MODEL = (
    os.getenv("GPT5_MODEL")
    or os.getenv("INTEGRITYSHIELD_MAPPING_MODEL")
    or "gpt-5.1"
)  # Use GPT-5.1 as default
GPT5_MAX_TOKENS = int(os.getenv("GPT5_MAX_TOKENS", "4000"))
GPT5_TEMPERATURE = float(os.getenv("GPT5_TEMPERATURE", "0.3"))
GPT5_REASONING_EFFORT = os.getenv("GPT5_REASONING_EFFORT", os.getenv("INTEGRITYSHIELD_MAPPING_REASONING", "high"))
MAPPINGS_PER_QUESTION = int(os.getenv("MAPPINGS_PER_QUESTION", "1"))  # default k value now single-pass

# Validation Configuration
VALIDATION_MODEL = (
    os.getenv("VALIDATION_MODEL")
    or os.getenv("INTEGRITYSHIELD_MAPPING_VALIDATION_MODEL")
    or "gpt-5.1"
)
VALIDATION_REASONING_EFFORT = os.getenv(
    "VALIDATION_REASONING_EFFORT",
    os.getenv("INTEGRITYSHIELD_MAPPING_VALIDATION_REASONING", "medium"),
)
VALIDATION_TIMEOUT = int(os.getenv("VALIDATION_TIMEOUT", "30"))  # seconds

# Generation-specific Configuration
GPT5_GENERATION_REASONING_EFFORT = os.getenv("GPT5_GENERATION_REASONING_EFFORT", "low")
MAPPING_MAX_CONCURRENT = int(os.getenv("MAPPING_MAX_CONCURRENT", "10"))
VALIDATION_MAX_CONCURRENT = int(os.getenv("VALIDATION_MAX_CONCURRENT", "5"))
API_TIMEOUT = int(os.getenv("MAPPING_API_TIMEOUT", "120"))  # seconds

# Retry Configuration
MAX_RETRIES = int(os.getenv("MAPPING_GENERATION_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("MAPPING_GENERATION_RETRY_DELAY", "1.0"))  # seconds
