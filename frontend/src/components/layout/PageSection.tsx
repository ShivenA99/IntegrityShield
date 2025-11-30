import React from "react";
import { View } from "@instructure/ui-view";
import { Flex } from "@instructure/ui-flex";
import { Heading } from "@instructure/ui-heading";
import { Text } from "@instructure/ui-text";

interface PageSectionProps {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  padding?: "none" | "small" | "medium" | "large";
  background?: "primary" | "secondary" | "transparent";
  shadow?: boolean;
  borderRadius?: "none" | "small" | "medium" | "large";
}

/**
 * PageSection - Consistent section wrapper with optional header
 *
 * Features:
 * - Optional title and subtitle with proper typography
 * - Action slot for buttons or controls
 * - Configurable padding, background, shadow
 * - Responsive layout
 */
export const PageSection: React.FC<PageSectionProps> = ({
  title,
  subtitle,
  actions,
  children,
  padding = "medium",
  background = "secondary",
  shadow = true,
  borderRadius = "medium",
}) => {
  return (
    <View
      as="section"
      background={background}
      padding={padding}
      shadow={shadow ? "resting" : "none"}
      borderRadius={borderRadius}
      borderWidth="small"
    >
      {(title || subtitle || actions) && (
        <div style={{
          marginBottom: '1rem',
          paddingBottom: '0.75rem',
          borderBottom: '1px solid #e0e0e0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.75rem'
        }}>
          {(title || subtitle) && (
            <div>
              {title && (
                <h3 style={{
                  margin: 0,
                  marginBottom: subtitle ? '0.25rem' : 0,
                  fontSize: '1.125rem',
                  fontWeight: '500',
                  color: '#333333',
                  letterSpacing: '-0.01em'
                }}>
                  {title}
                </h3>
              )}
              {subtitle && (
                <Text color="secondary" size="small">
                  {subtitle}
                </Text>
              )}
            </div>
          )}
          {actions && <div>{actions}</div>}
        </div>
      )}
      <View>{children}</View>
    </View>
  );
};
