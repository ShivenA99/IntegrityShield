from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.services.pipeline.font_attack import ChunkPlanner, FontAttackBuilder, FontCache
from backend.app.services.pipeline.latex_font_attack_service import LatexFontAttackService

BASE_FONT = Path("backend/resources/fonts/Roboto-Regular.ttf")


def _build_planner():
    builder = FontAttackBuilder(BASE_FONT)
    planner = ChunkPlanner(builder.glyph_lookup)
    return builder, planner


def test_chunk_planner_handles_length_mismatch():
    _, planner = _build_planner()
    hidden = "hi"
    visual = "hello"

    plan = planner.plan(hidden, visual)
    assert len(plan.positions) == len(hidden)
    reconstructed = "".join(position.visual_text for position in plan)
    assert reconstructed == visual
    assert plan.positions[0].requires_font is True
    assert plan.positions[1].visual_text.endswith("o")


def test_chunk_planner_zero_width_tail():
    _, planner = _build_planner()
    hidden = "valueX"
    visual = "value"

    plan = planner.plan(hidden, visual)
    assert len(plan.positions) == len(hidden)
    last = plan.positions[-1]
    assert last.visual_text == ""
    assert last.is_zero_width is True
    assert last.requires_font is True


def test_font_builder_creates_cached_fonts(tmp_path: Path):
    builder, planner = _build_planner()
    cache = FontCache(tmp_path / "cache")
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    plan = planner.plan("40", "50")
    results_first = builder.build_fonts(plan, fonts_dir, cache_lookup=cache)
    assert results_first
    for result in results_first:
        assert result.font_path.exists()
        assert result.used_cache is False

    results_second = builder.build_fonts(plan, fonts_dir, cache_lookup=cache)
    assert results_second
    for result in results_second:
        assert result.used_cache is True


def test_latex_font_attack_mutation(tmp_path: Path):
    builder, planner = _build_planner()
    service = LatexFontAttackService(base_font_path=BASE_FONT)
    fonts_dir = tmp_path / "fonts"
    cache = FontCache(tmp_path / ".cache")

    tex_source = "The value is 50."
    mapping = {
        "id": "map-1",
        "original": "50",
        "replacement": "40",
        "validated": True,
        "latex_stem_text": "The value is 50.",
        "start_pos": 12,
        "end_pos": 14,
    }
    question = SimpleNamespace(question_number=1, id=1, substring_mappings=[mapping])

    mutated, jobs, diagnostics = service._apply_font_attack(
        tex_source,
        [question],
        planner,
        builder,
        fonts_dir,
        cache,
    )

    assert '\\char"0034' in mutated
    assert '\\char"0030' in mutated
    assert "50" not in mutated
    assert jobs
    assert diagnostics and diagnostics[0].status == "replaced"
