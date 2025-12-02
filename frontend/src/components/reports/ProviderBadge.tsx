import * as React from "react";

interface ProviderBadgeProps {
  provider: string;
  size?: "small" | "medium" | "large";
}

const ProviderBadge: React.FC<ProviderBadgeProps> = ({ provider, size = "medium" }) => {
  const normalizedProvider = provider.toLowerCase();

  // Determine provider icon and details
  let iconSrc = "";
  let providerClass = "";
  let fallbackGlyph = "";

  if (normalizedProvider.includes("openai") || normalizedProvider.includes("gpt")) {
    iconSrc = "/icons/openai.svg";
    providerClass = "provider-badge--openai";
    fallbackGlyph = "O";
  } else if (normalizedProvider.includes("anthropic") || normalizedProvider.includes("claude")) {
    iconSrc = "/icons/claude_app_icon.png";
    providerClass = "provider-badge--anthropic";
    fallbackGlyph = "A";
  } else if (normalizedProvider.includes("google") || normalizedProvider.includes("gemini")) {
    iconSrc = "/icons/gemini.png";
    providerClass = "provider-badge--google";
    fallbackGlyph = "G";
  } else if (normalizedProvider.includes("grok") || normalizedProvider.includes("xai") || normalizedProvider.includes("x.ai")) {
    iconSrc = "/icons/grok--v2.jpg";
    providerClass = "provider-badge--grok";
    fallbackGlyph = "X";
  } else {
    providerClass = "provider-badge--generic";
    fallbackGlyph = provider.charAt(0).toUpperCase();
  }

  // Size dimensions in pixels
  const sizeMap = {
    small: 20,
    medium: 24,
    large: 32
  };
  const iconSize = sizeMap[size];
  const sizeClass = `provider-badge--${size}`;

  // Determine if we need a background for better contrast
  const needsBackground = providerClass === "provider-badge--openai";

  return (
    <div
      className={`provider-badge ${providerClass} ${sizeClass}`}
      title={provider}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: `${iconSize}px`,
        height: `${iconSize}px`,
        borderRadius: '0.25rem',
        overflow: 'hidden',
        backgroundColor: needsBackground ? '#ffffff' : 'transparent',
        padding: needsBackground ? '2px' : '0'
      }}
    >
      {iconSrc ? (
        <img
          src={iconSrc}
          alt={provider}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain'
          }}
          onError={(e) => {
            // Fallback to text glyph if image fails to load
            const target = e.target as HTMLImageElement;
            target.style.display = 'none';
            if (target.nextSibling) {
              (target.nextSibling as HTMLElement).style.display = 'block';
            }
          }}
        />
      ) : null}
      <span
        style={{
          display: iconSrc ? 'none' : 'block',
          fontSize: size === 'small' ? '0.75rem' : size === 'large' ? '1.25rem' : '1rem',
          fontWeight: 600
        }}
      >
        {fallbackGlyph}
      </span>
    </div>
  );
};

export default ProviderBadge;
