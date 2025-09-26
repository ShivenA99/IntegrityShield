import React from "react";

export const LoadingSpinner: React.FC = () => <div className="loading-spinner">Loading…</div>;

export const EmptyState: React.FC<{ message: string }> = ({ message }) => (
  <div className="empty-state">{message}</div>
);
