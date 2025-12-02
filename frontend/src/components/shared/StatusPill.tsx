import React from "react";
import { Pill } from "@instructure/ui-pill";

interface StatusPillProps {
  status: "pending" | "running" | "completed" | "failed";
  text?: string;
}

/**
 * StatusPill - Consistent status indicator using InstUI Pill
 *
 * Features:
 * - Color-coded by status (pending, running, completed, failed)
 * - Uses InstUI Pill for consistency
 * - Optional custom text override
 */
export const StatusPill: React.FC<StatusPillProps> = ({ status, text }) => {
  const statusConfig = {
    pending: { color: "info" as const, label: "Pending" },
    running: { color: "warning" as const, label: "Running" },
    completed: { color: "success" as const, label: "Completed" },
    failed: { color: "danger" as const, label: "Failed" },
  };

  // Fallback to "info" color and status text if invalid status provided
  const config = statusConfig[status] || { color: "info" as const, label: status };
  const displayText = text || config.label;

  return <Pill color={config.color}>{displayText}</Pill>;
};
