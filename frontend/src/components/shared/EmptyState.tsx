import React from "react";
import { View } from "@instructure/ui-view";
import { Flex } from "@instructure/ui-flex";
import { Heading } from "@instructure/ui-heading";
import { Text } from "@instructure/ui-text";
import { SVGIcon } from "@instructure/ui-svg-images";

interface EmptyStateProps {
  icon?: React.ComponentType<any>;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

/**
 * EmptyState - Consistent empty state component
 *
 * Features:
 * - Optional icon for visual context
 * - Title and description for explanation
 * - Optional action button (e.g., "Create first item")
 * - Centered layout with proper spacing
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  action,
}) => {
  return (
    <View
      as="div"
      textAlign="center"
      padding="x-large"
      background="secondary"
      borderRadius="medium"
      borderWidth="small"
      borderColor="primary"
    >
      <Flex direction="column" alignItems="center" gap="medium">
        {Icon && (
          <View
            as="div"
            padding="small"
            background="primary"
            borderRadius="circle"
            display="inline-flex"
          >
            <Icon size="large" color="secondary" />
          </View>
        )}
        <View>
          <Heading level="h3" margin="0 0 x-small">
            {title}
          </Heading>
          {description && (
            <Text color="secondary" size="medium">
              {description}
            </Text>
          )}
        </View>
        {action && <View margin="small 0 0">{action}</View>}
      </Flex>
    </View>
  );
};
