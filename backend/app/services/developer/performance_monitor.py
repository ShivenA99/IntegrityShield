from __future__ import annotations

from ...extensions import db
from ...models import PerformanceMetric


from typing import Optional


def record_metric(run_id: str, stage: str, name: str, value: float, unit: Optional[str] = None, details: Optional[dict] = None) -> None:
    metric = PerformanceMetric(
        pipeline_run_id=run_id,
        stage=stage,
        metric_name=name,
        metric_value=value,
        metric_unit=unit,
        details=details or {},
    )
    db.session.add(metric)
    db.session.commit()
