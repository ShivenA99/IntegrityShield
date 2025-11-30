import React from "react";
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

/**
 * PublicShell - Layout for public-facing pages (Landing, Login, Video)
 *
 * Features:
 * - Clean navigation with IntegrityShield branding
 * - Responsive design (stacks on mobile)
 * - ASU Orange brand color via InstUI theme
 * - No brittle body class toggles (uses unified theme)
 */
const PublicShell: React.FC<PublicShellProps> = ({ children, hideNav }) => {
  const location = useLocation();


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
    <View
      as="div"
      background="primary"
      minHeight="100vh"
      display="flex"
      flexDirection="column"
    >
      {!hideNav ? (
        <View
          as="header"
          background="secondary"
          padding="small medium"
          shadow="resting"
          borderWidth="0 0 small 0"
        >
          <Flex
            alignItems="center"
            justifyItems="space-between"
            wrap="wrap"
            gap="medium"
            maxWidth="80rem"
            margin="0 auto"
            width="100%"
          >
            <Flex alignItems="center" gap="small">
              <View
                as="div"
                padding="x-small"
                background="brand"
                borderRadius="medium"
                aria-hidden="true"
              >

                <Heading level="h3" color="primary-inverse" margin="0">
                  IS
                </Heading>
              </View>
              <View>
                <Text
                  size="small"
                  color="secondary"
                  fontWeight="bold"
                  transform="uppercase"
                  letterSpacing="expanded"
                >
                  IntegrityShield
                </Text>
              </View>
            </Flex>
            <Flex
              as="nav"
              alignItems="center"
              gap="small"
              wrap="wrap"
              role="navigation"
              aria-label="Main navigation"
            >

              {NAV_ITEMS.map((item) => renderNavButton(item))}
            </Flex>
          </Flex>
        </View>
      ) : (
        <View
          as="header"
          padding="large"
          textAlign="center"
        >
          <View
            as="div"
            padding="small"
            background="brand"
            borderRadius="large"
            display="inline-block"
            margin="0 0 medium"
            aria-hidden="true"
          >
            <Heading level="h2" color="primary-inverse" margin="0">
              IS
            </Heading>
          </View>
          <Heading level="h1" margin="0 0 medium">
            IntegrityShield
          </Heading>
          <Flex
            as="nav"
            alignItems="center"
            gap="small"
            wrap="wrap"
            justifyItems="center"
            role="navigation"
            aria-label="Main navigation"
          >

            {NAV_ITEMS.map((item) => renderNavButton(item))}
          </Flex>
        </View>
      )}
      <View
        as="main"
        padding="large"
        display="flex"
        flexDirection="column"
        flexGrow={1}
      >
        <View maxWidth="80rem" margin="0 auto" width="100%">

          {children}
        </View>
      </View>
    </View>
  );
};

export default PublicShell;
