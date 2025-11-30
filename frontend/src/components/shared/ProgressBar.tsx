import React from "react";
import { View } from "@instructure/ui-view";
import { ProgressBar as InstUIProgressBar } from "@instructure/ui-progress";
import { Text } from "@instructure/ui-text";
import { Flex } from "@instructure/ui-flex";

interface ProgressBarProps {
  label: string;
  valueNow: number;
  valueMax?: number;
  formatDisplayedValue?: (valueNow: number, valueMax: number) => string;
  showLabel?: boolean;
  size?: "x-small" | "small" | "medium" | "large";
  color?: "primary" | "brand" | "success" | "info" | "warning" | "danger" | "alert";
}

/**
 * ProgressBar - Accessible progress indicator using InstUI
 *
 * Features:
 * - Screen reader accessible with proper ARIA labels
 * - Customizable colors and sizes (maps to InstUI's palette)
 * - Optional percentage display with custom formatting
 * - Smooth animations with reduced motion support
 * - ASU Orange branding (#FF7F32) via theme.meterColorBrand
 *
 * Color Mapping:
 * - "brand"/"primary" → ASU Orange fill (via theme['ic-brand-primary'])
 * - "success" → Green fill
 * - "info" → Blue fill
 * - "warning" → Orange fill
 * - "danger" → Red fill
 * - "alert" → Blue fill
 *
 * Technical:
 * - Track color: Always "primary" (light gray background)
 * - Meter color: Mapped from prop → themed fill color
 */
export const ProgressBar: React.FC<ProgressBarProps> = ({
  label,
  valueNow,
  valueMax = 100,
  formatDisplayedValue,
  showLabel = true,
  size = "medium",
  color = "brand",
}) => {
  const percentage = Math.round((valueNow / valueMax) * 100);

  // Map semantic colors to InstUI's API
  // color prop: track/background (only accepts "primary" | "primary-inverse")
  const trackColor: "primary" | "primary-inverse" = "primary";

  // meterColor prop: progress fill (accepts "brand" | "success" | etc.)
  // "brand" uses theme.meterColorBrand → ASU Orange (#FF7F32)
  const meterColor: "brand" | "success" | "info" | "warning" | "danger" | "alert" =
    (color === "primary" || color === "brand") ? "brand" :
    (color === "primary-inverse") ? "info" :
    color as "success" | "info" | "warning" | "danger" | "alert";

  return (
    <View>
      {showLabel && (
        <View as="div" margin="0 0 x-small">
          <Flex justifyItems="space-between">
            <Text size="small" weight="normal">
              {label}
            </Text>
            <Text size="small" weight="bold" color="brand">
              {formatDisplayedValue
                ? formatDisplayedValue(valueNow, valueMax)
                : `${percentage}%`}
            </Text>
          </Flex>
        </View>
      )}
      <div style={{
        padding: '0.25rem',
        backgroundColor: '#ffffff',
        borderRadius: '0.5rem',
        border: '1px solid #e0e0e0'
      }}>
        <InstUIProgressBar
          screenReaderLabel={label}
          valueNow={valueNow}
          valueMax={valueMax}
          size={size}
          color={trackColor}
          meterColor={meterColor}
          shouldAnimate
          renderValue={() => null}
        />
      </div>
    </View>
  );
};
