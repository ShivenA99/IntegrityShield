"""Tests for stream analysis diagnostics and fallback behaviour."""

from PyPDF2.generic import ByteStringObject, FloatObject, NameObject

from app.services.pipeline.enhancement_methods.stream_analysis import analyze_page_content


class _EmptyPage:
    """Minimal stub page returning no span data."""

    def get_text(self, mode):
        return {}


def test_stream_analysis_reports_single_warning_when_spans_missing():
    operations = [
        ([], b"BT"),
        ([ByteStringObject(b"Hello")], b"Tj"),
        ([], b"ET"),
    ]

    records, spans, alignment = analyze_page_content(operations, _EmptyPage(), 0)

    warnings = [rec for rec in records if rec.advance_warning]

    assert spans == []
    assert len(warnings) == 1
    assert warnings[0].advance_warning == "span extraction unavailable; using naive advance"
    assert alignment == {}


class _PartialSpanPage:
    """Stub page that returns spans unrelated to the target text."""

    _RAWDICT = {
        "blocks": [
            {
                "lines": [
                    {
                        "spans": [
                            {
                                "chars": [
                                    {
                                        "c": "A",
                                        "bbox": [0.0, 0.0, 1.0, 1.0],
                                        "synthetic": False,
                                    },
                                ],
                                "font": "F1",
                                "size": 12.0,
                                "bbox": [0.0, 0.0, 1.0, 1.0],
                                "origin": [0.0, 0.0],
                                "dir": [1.0, 0.0],
                                "ascender": 0.8,
                                "descender": -0.2,
                            }
                        ],
                        "wmode": 0,
                        "dir": [1.0, 0.0],
                        "bbox": [0.0, 0.0, 1.0, 1.0],
                    }
                ]
            }
        ]
    }

    def get_text(self, mode):
        if mode == "rawdict":
            return self._RAWDICT
        return {}


def test_stream_analysis_synthesizes_metrics_for_unaligned_text():
    operations = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12)], b"Tf"),
        ([FloatObject(100), FloatObject(700)], b"Td"),
        ([ByteStringObject(b"(c) Make it")], b"Tj"),
        ([], b"ET"),
    ]

    records, spans, alignment = analyze_page_content(operations, _PartialSpanPage(), 0)

    warnings = [rec.advance_warning for rec in records if rec.advance_warning]

    assert warnings == []

    target = next(
        rec for rec in records if (rec.text_fragments and "".join(rec.text_fragments) == "(c) Make it")
    )

    assert target.advance is not None and target.advance > 0
    assert target.advance_direction is not None
    assert alignment.get(target.index) is None
