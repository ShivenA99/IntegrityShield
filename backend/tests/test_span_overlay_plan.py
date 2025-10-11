from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Dict

import pytest


def _install_backend_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject lightweight stand-ins for heavy optional dependencies."""

    # orjson substitute using stdlib json
    orjson_module = types.ModuleType("orjson")
    orjson_module.loads = lambda payload: json.loads(payload if isinstance(payload, str) else payload.decode())

    def _orjson_dumps(data, option=None):
        return json.dumps(data).encode()

    orjson_module.dumps = _orjson_dumps
    orjson_module.OPT_INDENT_2 = None
    monkeypatch.setitem(sys.modules, "orjson", orjson_module)

    # logging dependencies
    jsonlogger_module = types.ModuleType("pythonjsonlogger.jsonlogger")

    class _JsonFormatter:
        def __init__(self, *args, **kwargs):
            pass

        def format(self, record) -> str:
            return ""

    jsonlogger_module.JsonFormatter = _JsonFormatter
    pythonjsonlogger_module = types.ModuleType("pythonjsonlogger")
    pythonjsonlogger_module.jsonlogger = jsonlogger_module
    monkeypatch.setitem(sys.modules, "pythonjsonlogger", pythonjsonlogger_module)
    monkeypatch.setitem(sys.modules, "pythonjsonlogger.jsonlogger", jsonlogger_module)

    structlog_module = types.ModuleType("structlog")

    class _StructLogger:
        def bind(self, **kwargs):
            return self

        def info(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

    structlog_module.get_logger = lambda *args, **kwargs: _StructLogger()
    monkeypatch.setitem(sys.modules, "structlog", structlog_module)

    # flask and extensions
    class _DummyLogger:
        def exception(self, *args, **kwargs):
            pass

    class _DummyFlask:
        def __init__(self, name: str):
            self.config: Dict[str, object] = {}
            self.logger = _DummyLogger()
            self.json = None

        def errorhandler(self, _code):
            def decorator(func):
                return func

            return decorator

        def shell_context_processor(self, func):
            return func

    flask_module = types.ModuleType("flask")
    flask_module.Flask = _DummyFlask
    flask_module.jsonify = lambda *args, **kwargs: {}
    flask_module.current_app = types.SimpleNamespace(config={}, logger=_DummyLogger())
    monkeypatch.setitem(sys.modules, "flask", flask_module)

    class _DummySession:
        def add(self, *args, **kwargs):
            pass

        def commit(self, *args, **kwargs):
            pass

    class _DummySQLAlchemy:
        def __init__(self, *args, **kwargs):
            self.session = _DummySession()
            self.Model = type("Model", (), {})
            self.String = lambda *a, **k: None
            self.Text = lambda *a, **k: None
            self.Integer = lambda *a, **k: None
            self.Float = lambda *a, **k: None
            self.Boolean = lambda *a, **k: None
            self.DateTime = lambda *a, **k: None
            self.JSON = lambda *a, **k: None

        def init_app(self, *args, **kwargs):
            pass

        def Column(self, *args, **kwargs):
            return None

        def ForeignKey(self, *args, **kwargs):
            return None

    flask_sqlalchemy_module = types.ModuleType("flask_sqlalchemy")
    flask_sqlalchemy_module.SQLAlchemy = _DummySQLAlchemy
    monkeypatch.setitem(sys.modules, "flask_sqlalchemy", flask_sqlalchemy_module)

    for module_name, class_name in [
        ("flask_migrate", "Migrate"),
        ("flask_sock", "Sock"),
        ("flask_cors", "CORS"),
    ]:
        module = types.ModuleType(module_name)

        class _Ext:
            def __init__(self, *args, **kwargs):
                pass

            def init_app(self, *args, **kwargs):
                pass

        setattr(module, class_name, _Ext)
        monkeypatch.setitem(sys.modules, module_name, module)

    # minimal sqlalchemy surface used during imports
    sqlalchemy_module = types.ModuleType("sqlalchemy")

    class _JSON:
        def with_variant(self, other, dialect):
            return self

    sqlalchemy_module.JSON = _JSON

    class _Func:
        def now(self):
            return "now"

    sqlalchemy_module.func = _Func()
    sqlalchemy_module.text = lambda value: value

    sqlalchemy_orm_module = types.ModuleType("sqlalchemy.orm")

    class Mapped:  # pragma: no cover - typing placeholder
        pass

    sqlalchemy_orm_module.Mapped = Mapped
    sqlalchemy_orm_module.mapped_column = lambda *a, **k: None
    sqlalchemy_orm_module.relationship = lambda *a, **k: None
    sqlalchemy_module.orm = sqlalchemy_orm_module

    sqlalchemy_dialects_module = types.ModuleType("sqlalchemy.dialects")
    sqlalchemy_dialects_pg = types.ModuleType("sqlalchemy.dialects.postgresql")

    class _JSONB:
        pass

    sqlalchemy_dialects_pg.JSONB = _JSONB

    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy_module)
    monkeypatch.setitem(sys.modules, "sqlalchemy.orm", sqlalchemy_orm_module)
    monkeypatch.setitem(sys.modules, "sqlalchemy.dialects", sqlalchemy_dialects_module)
    monkeypatch.setitem(sys.modules, "sqlalchemy.dialects.postgresql", sqlalchemy_dialects_pg)

    # Expose backend/app as package without executing its __init__
    app_module = types.ModuleType("app")
    app_module.__path__ = [str((Path.cwd() / "backend" / "app").resolve())]
    monkeypatch.setitem(sys.modules, "app", app_module)


@pytest.fixture(autouse=True)
def backend_stub_env(monkeypatch: pytest.MonkeyPatch):
    _install_backend_stubs(monkeypatch)
    yield


def _make_span_record(text: str) -> "SpanRecord":
    from app.services.pipeline.enhancement_methods.span_extractor import SpanRecord

    characters = [(ch, (0.0, 0.0, 1.0, 1.0)) for ch in text]

    return SpanRecord(
        page_index=0,
        block_index=0,
        line_index=0,
        span_index=0,
        text=text,
        font="TestFont",
        font_size=9.0,
        bbox=(0.0, 0.0, 100.0, 10.0),
        origin=(0.0, 0.0),
        direction=(1.0, 0.0),
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        ascent=0.0,
        descent=0.0,
        characters=characters,
        normalized_text=text,
        normalized_chars=characters,
        grapheme_slices=[(ch, idx, idx + 1) for idx, ch in enumerate(text)],
        normalized_to_raw_indices=[(idx, idx + 1) for idx in range(len(text))],
    )


def _make_operator(text: str) -> "OperatorRecord":
    from PyPDF2.generic import ByteStringObject
    from app.services.pipeline.enhancement_methods.content_state_tracker import OperatorRecord

    return OperatorRecord(
        index=0,
        operator=b"Tj",
        operands=(ByteStringObject(text.encode("latin-1")),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=9.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=12.0,
        text_rise=0.0,
        text_fragments=[text],
        text_adjustments=None,
        operand_types=["string:text"],
        literal_kind="text",
        raw_bytes=[text.encode("latin-1")],
        advance=None,
        post_text_matrix=(1.0, 0.0, 0.0, 1.0, float(len(text)), 0.0),
        advance_direction=None,
        advance_start_projection=None,
        advance_end_projection=None,
        advance_delta=None,
        advance_error=None,
        advance_warning=None,
        world_start=None,
        world_end=None,
        suffix_matrix_error=None,
    )


def test_collect_span_plan_allocates_tail_insert_correctly():
    from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer
    from app.services.pipeline.enhancement_methods.match_planner import (
        build_replacement_plan,
    )
    from app.services.pipeline.enhancement_methods.span_alignment import SpanSlice
    from app.services.pipeline.enhancement_methods.span_rewrite_plan import SpanRewriteAccumulator

    renderer = BaseRenderer()
    BaseRenderer._span_key = lambda self, span: (span.block_index, span.line_index, span.span_index)

    original_text = (
        "WhyistheforgetgatebiasinLSTMsofteninitializedtoahighvalue(e.g.,2or3)?"
        "Explainitseffectonlong-term"
    )
    replacement_text = (
        "WhyistheoutputgatebiasinLLMsseldominitializedtoahighvalue(e.g.,2or3)?"
        "Explainitseffectonshort-term"
    )

    span_record = _make_span_record(original_text)
    operator_record = _make_operator(original_text)

    alignment = {
        operator_record.index: [
            SpanSlice(
                span=span_record,
                span_start=0,
                span_end=len(original_text),
            )
        ]
    }

    plan = build_replacement_plan(
        page_index=0,
        target_text=original_text,
        replacement_text=replacement_text,
        operator_sequence=[operator_record],
        alignment=alignment,
    )

    assert plan is not None

    context = {
        "original": original_text,
        "replacement": replacement_text,
        "q_number": "5",
        "entry_index": 0,
    }

    span_lookup = {(0, 0, 0): span_record}
    accumulators: Dict[tuple[int, int, int], SpanRewriteAccumulator] = {}

    captured = renderer._collect_span_rewrite_from_plan(plan, context, span_lookup, accumulators)
    assert captured is True

    assert (0, 0, 0) in accumulators, "Accumulator for span not created"
    accumulator = accumulators[(0, 0, 0)]

    entry = accumulator.build_entry(
        page_index=0,
        measure_width=lambda text, *args, **kwargs: float(len(text)),
        char_map={},
        doc_page=None,
    )

    assert entry is not None
    assert entry.overlay_fallback is False
    assert entry.requires_scaling is True
    assert entry.scale_factor <= 1.0
    rewritten = entry.replacement_text
    assert "effectonshort-term" in rewritten
    assert "effectoshort-termm" not in rewritten
    assert "seldom" in rewritten


def test_operator_rewrite_streams_fragment_plan_without_truncation():
    from PyPDF2.generic import TextStringObject
    from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer
    from app.services.pipeline.enhancement_methods.match_planner import build_replacement_plan
    from app.services.pipeline.enhancement_methods.span_alignment import SpanSlice

    renderer = BaseRenderer()
    BaseRenderer._span_key = lambda self, span: (span.block_index, span.line_index, span.span_index)

    original_text = "long-term"
    replacement_text = "short-term"

    record = _make_operator(original_text)
    span_record = _make_span_record(original_text)

    alignment = {
        record.index: [
            SpanSlice(
                span=span_record,
                span_start=0,
                span_end=len(original_text),
            )
        ]
    }

    plan = build_replacement_plan(
        page_index=0,
        target_text=original_text,
        replacement_text=replacement_text,
        operator_sequence=[record],
        alignment=alignment,
    )

    assert plan is not None

    context = {
        "original": original_text,
        "replacement": replacement_text,
        "q_number": "1",
        "entry_index": 0,
    }

    span_lookup = {(0, 0, 0): span_record}
    accumulators: Dict[tuple[int, int, int], SpanRewriteAccumulator] = {}

    renderer._collect_span_rewrite_from_plan(plan, context, span_lookup, accumulators)
    accumulator = accumulators[(0, 0, 0)]
    entry = accumulator.build_entry(
        page_index=0,
        measure_width=lambda text, *args, **kwargs: float(len(text)),
        char_map={},
        doc_page=None,
    )

    assert entry is not None

    operator_entry = ([TextStringObject(original_text)], b"Tj")
    rewritten_ops = renderer._build_span_operator_rewrite(
        operator_entry,
        entry,
        record,
    )

    assert rewritten_ops
    text_ops = [item for item in rewritten_ops if item[1] == b"Tj"]
    assert text_ops, "Expected at least one Tj operation"
    operands, operator = text_ops[0]
    assert operator == b"Tj"
    assert operands
    assert str(operands[0]) == replacement_text


def test_multi_operator_tj_replacement_merges_literals_cleanly():
    from PyPDF2.generic import ArrayObject, ByteStringObject, NumberObject, TextStringObject

    from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer

    renderer = BaseRenderer()

    tj_array = ArrayObject(
        [
            ByteStringObject(b"Q2"),
            NumberObject(-120),
            ByteStringObject(b"ints"),
            NumberObject(-30),
            TextStringObject(" trailing"),
        ]
    )

    segment = {
        "index": 0,
        "start": 0,
        "end": len("Q2 ints trailing"),
        "text": "Q2 ints trailing",
        "kern_map": {3: -120.0, 7: -30.0},
        "operands": [tj_array],
        "operator": b"TJ",
        "modified": False,
        "font_context": {"font": "/F1", "fontsize": 10.0},
    }

    replacements = [
        {
            "start": 0,
            "end": 7,
            "replacement": "Question 2",
            "context": {"original": "Q2 ints"},
        }
    ]

    operations = renderer._process_tj_replacements([tj_array], b"TJ", segment, replacements)

    assert operations, "Expected rewritten operations"
    operands, op_code = operations[0]
    assert op_code == b"TJ"
    rebuilt_array = operands[0]

    text_literals = [
        (item, item.decode("latin-1") if isinstance(item, ByteStringObject) else str(item))
        for item in rebuilt_array
        if isinstance(item, (TextStringObject, ByteStringObject))
    ]
    combined_text = "".join(text for _, text in text_literals)

    assert combined_text.startswith("Question 2"), combined_text
    assert combined_text == "Question 2 trailing"
    assert "ints" not in combined_text

    first_literal_obj, first_literal_text = text_literals[0]
    assert isinstance(first_literal_obj, ByteStringObject)
    assert first_literal_text == "Question 2"

    trailing_literal_obj, trailing_literal_text = text_literals[-1]
    assert isinstance(trailing_literal_obj, TextStringObject)
    assert trailing_literal_text == " trailing"

    kerning_values = [float(item) for item in rebuilt_array if isinstance(item, NumberObject)]
    assert -120.0 not in kerning_values
    assert any(abs(value + 30.0) < 1e-6 for value in kerning_values)

    assert segment["text"] == "Question 2 trailing"
    assert segment["kern_map"] == {10: -30.0}
    assert segment["modified"] is True
    assert segment["operands"][0] is rebuilt_array


def test_span_rewrite_accumulator_rejects_misaligned_slice():
    from app.services.pipeline.enhancement_methods.span_rewrite_plan import (
        SpanMappingRef,
        SpanRewriteAccumulator,
    )

    span_record = _make_span_record("worst-case")

    accumulator = SpanRewriteAccumulator(span=span_record)
    mapping_ref_bad = SpanMappingRef(
        q_number="1",
        original="worst-case",
        replacement="best-case",
        start=1,
        end=len("worst-case"),
        operator_index=125,
    )
    accumulator.add_replacement(
        1,
        len("worst-case"),
        "best-case",
        mapping_ref_bad,
        metadata={"operator_index": 125},
    )

    rejected_entry = accumulator.build_entry(
        page_index=0,
        measure_width=lambda text, *args, **kwargs: float(len(text)),
        char_map={},
        doc_page=None,
    )

    assert rejected_entry is None
    assert accumulator.validation_failures, "Expected validation failure for mismatched slice"
    failure = accumulator.validation_failures[0]
    assert failure["expected"] == "worst-case"
    assert failure["observed"].startswith("orst"), failure["observed"]

    good_accumulator = SpanRewriteAccumulator(span=span_record)
    mapping_ref_good = SpanMappingRef(
        q_number="1",
        original="worst-case",
        replacement="best-case",
        start=0,
        end=len("worst-case"),
        operator_index=125,
    )
    good_accumulator.add_replacement(
        0,
        len("worst-case"),
        "best-case",
        mapping_ref_good,
        metadata={"operator_index": 125},
    )

    entry = good_accumulator.build_entry(
        page_index=0,
        measure_width=lambda text, *args, **kwargs: float(len(text)),
        char_map={},
        doc_page=None,
    )

    assert entry is not None
    assert not entry.validation_failures


def test_remap_fragments_by_diff_handles_inserts_cleanly():
    from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer

    renderer = BaseRenderer()

    fragments = ["effect", "on", "long-term"]
    result = renderer._remap_fragments_by_diff(
        original_fragments=fragments,
        original_text="".join(fragments),
        replacement_text="effectonshort-term",
    )

    assert result is not None
    outputs, inserts_before, inserts_after = result
    assert outputs == ["effect", "on", "short-term"]
    assert inserts_before == {}
    assert inserts_after == {}


def test_collect_span_rewrite_from_context_matches_without_glyph_path():
    from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer
    from app.services.pipeline.enhancement_methods.span_rewrite_plan import SpanRewriteAccumulator

    renderer = BaseRenderer()

    span_text = "WhyistheoutputgatebiasinLLMsofteninitializedtoahighvalue"
    span_record = _make_span_record(span_text)

    context = {
        "original": "often",
        "replacement": "seldom",
        "prefix": "LLMs",
        "suffix": "initialized",
        "start_pos": 29,
        "q_number": "5",
        "entry_index": 1,
    }

    accumulators: Dict[tuple[int, int, int], SpanRewriteAccumulator] = {}
    renderer._collect_span_rewrite_from_context(
        context,
        {(0, 0, 0): span_record},
        accumulators,
    )

    accumulator = accumulators[(0, 0, 0)]
    replacements = {(item.start, item.end, item.replacement) for item in accumulator.replacements}
    assert any(repl == "seldom" for _, _, repl in replacements)
