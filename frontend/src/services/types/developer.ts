export interface LogEntry {
  timestamp: string | null;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  stage: string;
  component?: string | null;
  message: string;
  metadata?: Record<string, unknown>;
}

export interface PerformanceMetricRecord {
  stage: string;
  metric_name: string;
  metric_value: number;
  metric_unit?: string | null;
  recorded_at?: string | null;
  metadata?: Record<string, unknown>;
}
