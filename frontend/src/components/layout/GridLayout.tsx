import React from "react";
import { View } from "@instructure/ui-view";
import { Grid } from "@instructure/ui-grid";

interface GridLayoutProps {
  children: React.ReactNode;
  columns?: 1 | 2 | 3 | 4;
  gap?: "none" | "small" | "medium" | "large";
  colSpacing?: "none" | "small" | "medium" | "large";
  rowSpacing?: "none" | "small" | "medium" | "large";
}

/**
 * GridLayout - Responsive grid container using InstUI Grid
 *
 * Features:
 * - Responsive columns (auto-collapses on small screens)
 * - Configurable gap spacing
 * - Proper alignment and spacing
 */
export const GridLayout: React.FC<GridLayoutProps> = ({
  children,
  columns = 2,
  gap = "medium",
  colSpacing,
  rowSpacing,
}) => {
  const childArray = React.Children.toArray(children);

  return (
    <Grid
      colSpacing={colSpacing ?? gap}
      rowSpacing={rowSpacing ?? gap}
      vAlign="top"
    >
      {childArray.map((child, index) => (
        <Grid.Row key={index}>
          <Grid.Col width={columns === 1 ? 12 : columns === 2 ? { small: 12, medium: 6, large: 6 } : columns === 3 ? { small: 12, medium: 6, large: 4 } : { small: 12, medium: 6, large: 3 }}>
            {child}
          </Grid.Col>
        </Grid.Row>
      ))}
    </Grid>
  );
};
