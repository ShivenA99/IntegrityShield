"""Configuration for GPT-5 mapping generation service."""

import os

# GPT-5 API Configuration
GPT5_MODEL = os.getenv("GPT5_MODEL", "gpt-4o")  # Use GPT-4o as fallback if GPT-5 not available
GPT5_MAX_TOKENS = int(os.getenv("GPT5_MAX_TOKENS", "4000"))
GPT5_TEMPERATURE = float(os.getenv("GPT5_TEMPERATURE", "0.3"))
MAPPINGS_PER_QUESTION = int(os.getenv("MAPPINGS_PER_QUESTION", "5"))  # k value

# Validation Configuration
VALIDATION_MODEL = os.getenv("VALIDATION_MODEL", "openai:fusion")
VALIDATION_TIMEOUT = int(os.getenv("VALIDATION_TIMEOUT", "30"))  # seconds

# Retry Configuration
MAX_RETRIES = int(os.getenv("MAPPING_GENERATION_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("MAPPING_GENERATION_RETRY_DELAY", "1.0"))  # seconds

