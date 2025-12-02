import * as React from "react";

interface ReportHeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  mode?: string;
}

const ReportHeader: React.FC<ReportHeaderProps> = ({
  title,
  subtitle,
  actions,
  mode
}) => {
  return (
    <div className="report-header">
      <div className="report-header__content">
        <div className="report-header__title-group">
          {mode && (
            <span className="mode-badge">
              {mode === "prevention" ? "🛡️ Prevention Mode" : "🔍 Detection Mode"}
            </span>
          )}
          <h1>{title}</h1>
          {subtitle && <p className="report-header__subtitle">{subtitle}</p>}
        </div>
      </div>
      {actions && (
        <div className="report-header__actions">
          {actions}
        </div>
      )}
    </div>
  );
};

export default ReportHeader;
