#!/usr/bin/env bash
# Quick env for Code Glyph overlay + selective redaction
# Usage: source ./cg_env.sh

# Current settings
export CG_OVERLAY_MODE=true
export CG_SELECTIVE_WORDS_ONLY=true
export CG_REDACTION_EXPAND_PX=1.0
export CG_REDACTION_VERIFY_EXPAND_PX=0.5
export CG_USE_ACTUALTEXT=false
export CG_BASELINE_NUDGE_PX=0.0

# Common toggles (uncomment to adjust)
# export CODE_GLYPH_FONT_MODE=prebuilt
# export CG_TOKEN_FONT_PT=11
# export CG_MIN_FONT_PT=9
# export CG_FIT_WIDTH=false       # keep drawing bounded by rect; disable to avoid width tweaks
# export CG_ALIGN_MODE=xheight    # xheight|capheight (if size normalization enabled)

# Baseline selection (planned)
# export CG_BASELINE_SOURCE=stored   # stored|span|line|rect (prefer order)
# export CG_BASELINE_VTOL_PX=2.0     # vertical tolerance when picking nearest baseline
# export CG_SPAN_OVERLAP_THRESH=0.30 # require >=30% vertical overlap with token rect
# export CG_SEARCH_PAD_PX=2.0        # expand token rect for local span search
# export CG_DEBUG_BASELINE=true      # verbose per-token baseline diagnostics 