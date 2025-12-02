from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple

from PyPDF2.generic import (
    ArrayObject,
    ByteStringObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)


Matrix = Tuple[float, float, float, float, float, float]


def _identity_matrix() -> Matrix:
    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _matrix_multiply(m1: Matrix, m2: Matrix) -> Matrix:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def combine_with_ctm(ctm: Matrix, text_matrix: Matrix) -> Matrix:
    return _matrix_multiply(ctm, text_matrix)


def _matrix_translate(matrix: Matrix, dx: float, dy: float) -> Matrix:
    translation = (1.0, 0.0, 0.0, 1.0, dx, dy)
    return _matrix_multiply(matrix, translation)


@dataclass
class TextGraphicsState:
    ctm: Matrix = field(default_factory=_identity_matrix)
    text_matrix: Matrix = field(default_factory=_identity_matrix)
    text_line_matrix: Matrix = field(default_factory=_identity_matrix)
    font_resource: Optional[str] = None
    font_size: float = 12.0
    char_spacing: float = 0.0
    word_spacing: float = 0.0
    horizontal_scaling: float = 100.0
    leading: float = 0.0
    text_rise: float = 0.0


@dataclass
class OperatorRecord:
    index: int
    operator: bytes
    operands: Tuple[Any, ...]
    graphics_depth: int
    text_depth: int
    ctm: Matrix
    text_matrix: Matrix
    text_line_matrix: Matrix
    font_resource: Optional[str]
    font_size: float
    char_spacing: float
    word_spacing: float
    horizontal_scaling: float
    leading: float
    text_rise: float
    text_fragments: Optional[List[str]] = None
    text_adjustments: Optional[List[float]] = None
    operand_types: Optional[List[str]] = None
    literal_kind: Optional[str] = None
    raw_bytes: Optional[List[bytes]] = None
    advance: Optional[float] = None
    post_text_matrix: Optional[Matrix] = None
    advance_direction: Optional[Tuple[float, float]] = None
    advance_start_projection: Optional[float] = None
    advance_end_projection: Optional[float] = None
    advance_delta: Optional[Tuple[float, float]] = None
    advance_error: Optional[float] = None
    advance_warning: Optional[str] = None
    world_start: Optional[Tuple[float, float]] = None
    world_end: Optional[Tuple[float, float]] = None
    suffix_matrix_error: Optional[float] = None


class ContentStateTracker:
    """Capture operator-level state for PDF text streams."""

    TEXT_SHOW_OPERATORS = {b"Tj", b"TJ", b"'", b'"'}

    def __init__(
        self,
        advance_resolver: Optional[
            Callable[[OperatorRecord, TextGraphicsState], Optional[float]]
        ] = None,
    ) -> None:
        self.records: List[OperatorRecord] = []
        self.advance_resolver = advance_resolver

    def walk(self, content_operations: Sequence[Tuple[Sequence[Any], bytes | str]]) -> List[OperatorRecord]:
        state_stack: List[TextGraphicsState] = [TextGraphicsState()]
        graphics_depth = 0
        text_depth = 0
        inside_text = False

        for index, (operands, operator) in enumerate(content_operations):
            op_bytes = operator if isinstance(operator, bytes) else operator.encode()
            current_state = state_stack[-1]

            record = OperatorRecord(
                index=index,
                operator=op_bytes,
                operands=tuple(operands),
                graphics_depth=graphics_depth,
                text_depth=text_depth,
                ctm=current_state.ctm,
                text_matrix=current_state.text_matrix,
                text_line_matrix=current_state.text_line_matrix,
                font_resource=current_state.font_resource,
                font_size=current_state.font_size,
                char_spacing=current_state.char_spacing,
                word_spacing=current_state.word_spacing,
                horizontal_scaling=current_state.horizontal_scaling,
                leading=current_state.leading,
                text_rise=current_state.text_rise,
            )

            if op_bytes in self.TEXT_SHOW_OPERATORS and inside_text:
                self._capture_text_payload(record, operands, op_bytes)

            self.records.append(record)

            # mutate state for next operator
            if op_bytes == b"q":
                graphics_depth += 1
                state_stack.append(self._clone_state(current_state))
            elif op_bytes == b"Q":
                if graphics_depth > 0 and len(state_stack) > 1:
                    graphics_depth -= 1
                    state_stack.pop()
                    current_state = state_stack[-1]
                    inside_text = False
                    text_depth = max(text_depth - 1, 0)
            elif op_bytes == b"cm":
                matrix = self._to_matrix(operands)
                current_state.ctm = _matrix_multiply(current_state.ctm, matrix)
            elif op_bytes == b"BT":
                inside_text = True
                text_depth += 1
                current_state.text_matrix = _identity_matrix()
                current_state.text_line_matrix = _identity_matrix()
                current_state.char_spacing = 0.0
                current_state.word_spacing = 0.0
                current_state.horizontal_scaling = 100.0
                current_state.text_rise = 0.0
            elif op_bytes == b"ET":
                inside_text = False
                text_depth = max(text_depth - 1, 0)
            elif op_bytes == b"Tf" and inside_text:
                if operands:
                    font_name = operands[0]
                    if isinstance(font_name, NameObject):
                        font_name = font_name.get_object() if hasattr(font_name, "get_object") else font_name
                    current_state.font_resource = str(font_name)
                if len(operands) >= 2:
                    current_state.font_size = float(operands[1])
            elif op_bytes == b"Tc" and inside_text:
                current_state.char_spacing = float(operands[0]) if operands else 0.0
            elif op_bytes == b"Tw" and inside_text:
                current_state.word_spacing = float(operands[0]) if operands else 0.0
            elif op_bytes == b"Tz" and inside_text:
                current_state.horizontal_scaling = float(operands[0]) if operands else 100.0
            elif op_bytes == b"TL" and inside_text:
                current_state.leading = float(operands[0]) if operands else 0.0
            elif op_bytes == b"Ts" and inside_text:
                current_state.text_rise = float(operands[0]) if operands else 0.0
            elif op_bytes == b"Tm" and inside_text:
                matrix = self._to_matrix(operands)
                current_state.text_matrix = matrix
                current_state.text_line_matrix = matrix
            elif op_bytes in {b"Td", b"TD"} and inside_text:
                tx = float(operands[0]) if operands else 0.0
                ty = float(operands[1]) if len(operands) > 1 else 0.0
                translation = (1.0, 0.0, 0.0, 1.0, tx, ty)
                current_state.text_matrix = _matrix_multiply(current_state.text_line_matrix, translation)
                current_state.text_line_matrix = current_state.text_matrix
                if op_bytes == b"TD":
                    current_state.leading = -ty
            elif op_bytes == b"T*" and inside_text:
                translation = (1.0, 0.0, 0.0, 1.0, 0.0, -current_state.leading)
                current_state.text_matrix = _matrix_multiply(current_state.text_line_matrix, translation)
                current_state.text_line_matrix = current_state.text_matrix
            elif op_bytes == b"'" and inside_text:
                translation = (1.0, 0.0, 0.0, 1.0, 0.0, -current_state.leading)
                current_state.text_matrix = _matrix_multiply(current_state.text_line_matrix, translation)
                current_state.text_line_matrix = current_state.text_matrix
            elif op_bytes == b'"' and inside_text:
                if len(operands) >= 2:
                    current_state.char_spacing = float(operands[0])
                    current_state.word_spacing = float(operands[1])
                translation = (1.0, 0.0, 0.0, 1.0, 0.0, -current_state.leading)
                current_state.text_matrix = _matrix_multiply(current_state.text_line_matrix, translation)
                current_state.text_line_matrix = current_state.text_matrix

            if op_bytes in self.TEXT_SHOW_OPERATORS and inside_text:
                advance = self._resolve_advance(record, current_state)
                if advance is not None:
                    record.advance = advance
                    translation = (1.0, 0.0, 0.0, 1.0, advance, 0.0)
                    current_state.text_matrix = _matrix_multiply(current_state.text_matrix, translation)
                    current_state.text_line_matrix = current_state.text_matrix
                    record.post_text_matrix = current_state.text_matrix

        return self.records

    def _clone_state(self, state: TextGraphicsState) -> TextGraphicsState:
        return TextGraphicsState(
            ctm=state.ctm,
            text_matrix=state.text_matrix,
            text_line_matrix=state.text_line_matrix,
            font_resource=state.font_resource,
            font_size=state.font_size,
            char_spacing=state.char_spacing,
            word_spacing=state.word_spacing,
            horizontal_scaling=state.horizontal_scaling,
            leading=state.leading,
            text_rise=state.text_rise,
        )

    def _capture_text_payload(self, record: OperatorRecord, operands: Sequence[Any], operator: bytes) -> None:
        fragments: List[str] = []
        adjustments: List[float] = []
        operand_types: List[str] = []
        raw_bytes: List[bytes] = []

        if operator == b"Tj" and operands:
            fragment, raw, literal_kind = self._decode_string_operand(operands[0])
            fragments.append(fragment)
            operand_types.append("string")
            raw_bytes.append(raw)
            record.literal_kind = literal_kind
        elif operator == b"TJ" and operands:
            array = operands[0] if isinstance(operands[0], ArrayObject) else ArrayObject()
            for entry in array:  # type: ignore [iteration-over-ArrayObject]
                if isinstance(entry, NumberObject):
                    adjustments.append(float(entry))
                    operand_types.append("number")
                else:
                    fragment, raw, literal_kind = self._decode_string_operand(entry)
                    fragments.append(fragment)
                    operand_types.append(f"string:{literal_kind}")
                    raw_bytes.append(raw)
            record.literal_kind = "array"
        elif operator in {b"'", b'"'} and operands:
            operand = operands[-1]
            fragment, raw, literal_kind = self._decode_string_operand(operand)
            fragments.append(fragment)
            operand_types.append("string")
            raw_bytes.append(raw)
            record.literal_kind = literal_kind

        record.text_fragments = fragments or None
        record.text_adjustments = adjustments or None
        record.operand_types = operand_types or None
        record.raw_bytes = raw_bytes or None

    def _decode_string_operand(self, operand: Any) -> Tuple[str, bytes, str]:
        literal_kind = "unknown"
        raw_bytes: bytes = b""
        value = ""

        if isinstance(operand, TextStringObject):
            value = str(operand)
            raw_bytes = getattr(operand, "original_bytes", b"") or value.encode("latin-1", errors="ignore")
            literal_kind = "text"
        elif isinstance(operand, ByteStringObject):
            raw_bytes = bytes(operand)
            try:
                value = raw_bytes.decode("latin-1")
            except Exception:
                value = ""
            literal_kind = "byte"
        else:
            value = str(operand)
            literal_kind = operand.__class__.__name__

        return value, raw_bytes, literal_kind

    def _to_matrix(self, operands: Sequence[Any]) -> Matrix:
        values = [float(op) for op in operands[:6]]
        if len(values) != 6:
            values = values + [0.0] * (6 - len(values))
        return tuple(values[:6])  # type: ignore[return-value]

    def _resolve_advance(
        self,
        record: OperatorRecord,
        state: TextGraphicsState,
    ) -> Optional[float]:
        if not record.text_fragments and not record.text_adjustments:
            return 0.0

        advance: Optional[float] = None

        if self.advance_resolver is not None:
            try:
                advance = self.advance_resolver(record, state)
            except Exception:
                advance = None

        if advance is None:
            advance = self._naive_advance(record, state)

        return advance

    def _naive_advance(
        self,
        record: OperatorRecord,
        state: TextGraphicsState,
    ) -> float:
        fragments = record.text_fragments or []
        text = "".join(fragments)
        if not text:
            return 0.0

        scale = state.horizontal_scaling / 100.0 if state.horizontal_scaling else 1.0

        base_width = len(text) * state.font_size * 0.5 * scale
        char_spacing = state.char_spacing * max(len(text) - 1, 0) * scale
        word_spacing = state.word_spacing * text.count(" ") * scale

        adjustment = 0.0
        if record.text_adjustments:
            adjustment = sum((adj / 1000.0) * state.font_size * scale for adj in record.text_adjustments)

        return base_width + char_spacing + word_spacing - adjustment
