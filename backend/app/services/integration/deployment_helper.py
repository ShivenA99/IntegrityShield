from __future__ import annotations

from dataclasses import dataclass


data_class = dataclass  # alias for potential future setups


@dataclass
class DeploymentConfig:
    backend_url: str
    frontend_url: str
    storage_bucket: str | None = None


def summarize(config: DeploymentConfig) -> dict:
    return {
        "backend_url": config.backend_url,
        "frontend_url": config.frontend_url,
        "storage_bucket": config.storage_bucket,
    }
