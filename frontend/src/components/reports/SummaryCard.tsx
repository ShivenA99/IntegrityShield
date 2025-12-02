import * as React from "react";

interface SummaryCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  variant?: "default" | "success" | "warning" | "danger";
  children?: React.ReactNode;
}

const SummaryCard: React.FC<SummaryCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  variant = "default",
  children
}) => {
  return (
    <div className={`summary-card summary-card--${variant}`}>
      {icon && <div className="summary-card__icon">{icon}</div>}
      <div className="summary-card__content">
        <h3 className="summary-card__value">{value}</h3>
        <p className="summary-card__title">{title}</p>
        {subtitle && <span className="summary-card__subtitle">{subtitle}</span>}
        {children}
      </div>
    </div>
  );
};

export default SummaryCard;
