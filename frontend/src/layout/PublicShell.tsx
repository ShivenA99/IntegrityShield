import React, { useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { View } from "@instructure/ui-view";
import { Flex } from "@instructure/ui-flex";
import { Heading } from "@instructure/ui-heading";
import { Text } from "@instructure/ui-text";
import { Button } from "@instructure/ui-buttons";
import { IconExternalLinkLine } from "@instructure/ui-icons";

const NAV_ITEMS = [
  { label: "Home", to: "/" },
  { label: "Try it", to: "/try" },
  { label: "Video demo", to: "/video" },
  { label: "Code repository", href: "https://github.com/fairtest-ai" },
];

interface PublicShellProps {
  children: React.ReactNode;
  hideNav?: boolean;
}

const PublicShell: React.FC<PublicShellProps> = ({ children, hideNav }) => {
  const location = useLocation();

  useEffect(() => {
    document.body.classList.add("light-theme");
    return () => {
      document.body.classList.remove("light-theme");
    };
  }, []);

  const renderNavButton = (item: (typeof NAV_ITEMS)[number]) => {
    if (item.href) {
      return (
        <Button
          key={item.label}
          href={item.href}
          target="_blank"
          rel="noreferrer"
          color="secondary"
          withBackground={false}
          renderIcon={<IconExternalLinkLine />}
          iconPlacement="end"
          size="small"
        >
          {item.label}
        </Button>
      );
    }
    const isActive = location.pathname === item.to;
    return (
      <Button
        key={item.label}
        as={NavLink}
        to={item.to}
        size="small"
        color={isActive ? "primary" : "secondary"}
        withBackground={isActive}
        margin="0 x-small 0 0"
      >
        {item.label}
      </Button>
    );
  };

  return (
    <View as="div" className="public-shell" background="primary" minHeight="100vh">
      {!hideNav ? (
        <View as="header" className="public-shell__nav" background="secondary" padding="small" shadow="resting">
          <Flex alignItems="center" justifyItems="space-between" wrap="wrap" gap="medium">
            <Flex alignItems="center" gap="small">
              <View as="div" padding="x-small" background="brand" borderRadius="medium" aria-hidden="true">
                <Heading level="h3" color="primary-inverse" margin="0">
                  IS
                </Heading>
              </View>
              <div>
                <Text size="small" color="secondary" fontWeight="bold" transform="uppercase" letterSpacing="expanded">
                  IntegrityShield
                </Text>
              </div>
            </Flex>
            <Flex alignItems="center" gap="small" wrap="wrap">
              {NAV_ITEMS.map((item) => renderNavButton(item))}
            </Flex>
          </Flex>
        </View>
      ) : (
        <View as="header" className="public-shell__nav hero-top">
          <div className="hero-logo" aria-hidden="true">
            IS
          </div>
          <Heading level="h1" margin="small 0" textAlign="center">
            IntegrityShield
          </Heading>
          <Flex alignItems="center" gap="small" wrap="wrap" justifyItems="center">
            {NAV_ITEMS.map((item) => renderNavButton(item))}
          </Flex>
        </View>
      )}
      <View as="main" className="public-shell__content" padding="large">
        <View maxWidth="80rem" margin="0 auto">
          {children}
        </View>
      </View>
    </View>
  );
};

export default PublicShell;
