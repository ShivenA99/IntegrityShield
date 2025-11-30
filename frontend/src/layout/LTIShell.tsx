import React, { useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { View } from "@instructure/ui-view";
import { Flex } from "@instructure/ui-flex";
import { Heading } from "@instructure/ui-heading";
import { Text } from "@instructure/ui-text";
import { Button } from "@instructure/ui-buttons";
import { Avatar } from "@instructure/ui-avatar";

const TOOL_NAV = [
  { label: "Dashboard", to: "/dashboard" },
  { label: "History", to: "/history" },
  { label: "Files", to: "/files" },
  { label: "Reports", to: "/reports" },
  { label: "Settings", to: "/settings" },
];

interface LTIShellProps {
  title: string;
  subtitle?: string;
  actionSlot?: React.ReactNode;
  children: React.ReactNode;
}

const LTIShell: React.FC<LTIShellProps> = ({ title, subtitle, actionSlot, children }) => {
  const location = useLocation();

  useEffect(() => {
    document.body.classList.add("light-theme");
    return () => {
      document.body.classList.remove("light-theme");
    };
  }, []);

  return (
    <View as="div" className="lti-shell" background="primary" minHeight="100vh">
      <View as="header" className="lti-header" background="secondary" padding="small" shadow="resting">
        <Flex alignItems="center" justifyItems="space-between" wrap="wrap" gap="medium">
          <Flex alignItems="center" gap="small">
            <Avatar name="IntegrityShield" size="small" />
            <div>
              <Text size="small" color="secondary" fontWeight="bold" transform="uppercase" letterSpacing="expanded">
                IntegrityShield
              </Text>
            </div>
          </Flex>
          <Flex alignItems="center" gap="small">
            <Button color="secondary" withBackground={false}>
              Help
            </Button>
            <Button color="secondary" withBackground={false}>
              Docs
            </Button>
            <Avatar name="IS" size="small" />
          </Flex>
        </Flex>
      </View>
      <Flex className="lti-body" alignItems="stretch">
        <View as="aside" className="tool-nav" background="secondary" padding="medium" minWidth="15rem">
          <View margin="0 0 medium">
            <Text size="small" color="secondary" fontWeight="bold">
              IntegrityShield
            </Text>
          </View>
          <Flex as="nav" direction="column" gap="x-small" aria-label="IntegrityShield navigation">
            {TOOL_NAV.map((item) => {
              const isSelected = location.pathname.startsWith(item.to);
              return (
                <Button
                  key={item.label}
                  as={NavLink}
                  to={item.to}
                  color={isSelected ? "primary" : "secondary"}
                  withBackground={isSelected}
                  display="block"
                  textAlign="start"
                  size="small"
                >
                  {item.label}
                </Button>
              );
            })}
          </Flex>
        </View>
        <View as="main" className="tool-content" padding="large" width="100%">
          <View as="header" className="tool-content__header" margin="0 0 large">
            <Flex alignItems="flex-start" justifyItems="space-between" wrap="wrap" gap="medium">
              <div>
                <Text size="small" color="secondary" transform="uppercase" letterSpacing="expanded">
                  IntegrityShield / {title}
                </Text>
                <Heading level="h1" margin="x-small 0 0 0">
                  {title}
                </Heading>
                {subtitle ? (
                  <View margin="xx-small 0 0 0">
                    <Text color="secondary">{subtitle}</Text>
                  </View>
                ) : null}
              </div>
              {actionSlot ? <View className="tool-header__actions">{actionSlot}</View> : null}
            </Flex>
          </View>
          <View className="tool-content__inner">{children}</View>
        </View>
      </Flex>
    </View>
  );
};

export default LTIShell;
