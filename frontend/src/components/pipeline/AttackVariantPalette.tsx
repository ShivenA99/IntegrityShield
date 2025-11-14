import * as React from "react";
import clsx from "clsx";

import { ENHANCEMENT_METHOD_LABELS } from "@constants/enhancementMethods";

const LATEX_METHODS = [
  "latex_dual_layer",
  "latex_font_attack",
  "latex_icw",
  "latex_icw_dual_layer",
  "latex_icw_font_attack",
] as const;

type LatexMethod = (typeof LATEX_METHODS)[number];

interface AttackVariantPaletteProps {
  selected: string[];
  locked: boolean;
  isUpdating: boolean;
  onToggle: (method: LatexMethod) => Promise<void> | void;
  message?: string | null;
  error?: string | null;
}

const AttackVariantPalette: React.FC<AttackVariantPaletteProps> = ({
  selected,
  locked,
  isUpdating,
  onToggle,
  message,
  error,
}) => {
  const selectedSet = React.useMemo(() => new Set(selected), [selected]);

  return (
    <div className={clsx("attack-palette", locked && "attack-palette--locked")}>
      <header className="attack-palette__header">
        <span className="attack-palette__title">Variants</span>
        {locked ? <span className="attack-palette__lock">Locked</span> : null}
      </header>
      <div className="attack-palette__options">
        {LATEX_METHODS.map((method) => {
          const label = ENHANCEMENT_METHOD_LABELS[method] ?? method.replace(/_/g, " ");
          const active = selectedSet.has(method);
          const disabled = locked || (isUpdating && !active);
          return (
            <button
              key={method}
              type="button"
              className={clsx("attack-toggle", active && "attack-toggle--active")}
              aria-pressed={active}
              disabled={disabled}
              onClick={() => {
                if (disabled) return;
                onToggle(method);
              }}
            >
              <span className="attack-toggle__label">{label}</span>
            </button>
          );
        })}
      </div>
      {(message || error) ? (
        <div className={clsx("attack-palette__status", error ? "is-error" : "is-ok")}>
          {error ?? message}
        </div>
      ) : null}
    </div>
  );
};

export default AttackVariantPalette;
