import React from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

import type { PerformanceMetricRecord } from "@services/types/developer";

interface PerformanceMetricsProps {
  metrics: PerformanceMetricRecord[];
}

const PerformanceMetrics: React.FC<PerformanceMetricsProps> = ({ metrics }) => {
  return (
    <div className="performance-metrics">
      <h3>Performance Metrics</h3>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={metrics}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="recorded_at" hide />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="metric_value" stroke="#2563eb" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default PerformanceMetrics;
