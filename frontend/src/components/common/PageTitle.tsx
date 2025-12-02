import React from "react";

interface PageTitleProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Styled page title component with minimal accent border design.
 * Replaces plain <h1> tags in panel headers with themed styling.
 */
const PageTitle: React.FC<PageTitleProps> = ({ children, className = "" }) => {
  return (
    <h1 className={`page-title ${className}`.trim()}>
      {children}
    </h1>
  );
};

export default PageTitle;
