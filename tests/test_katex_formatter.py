from pathlib import Path

import pytest

from tools import katex_formatter


def test_render_creates_png_and_cleanup_removes_file() -> None:
    path = katex_formatter.render(r"\frac{a}{b}")
    try:
        assert isinstance(path, Path)
        assert path.exists()
        assert path.suffix == ".png"
    finally:
        katex_formatter.cleanup(path)

    assert not path.exists()


def test_render_blank_expression_raises() -> None:
    with pytest.raises(ValueError):
        katex_formatter.render("   ")


# ---------------------------------------------------------------------------
# parse_math_segments
# ---------------------------------------------------------------------------

def test_parse_math_segments_empty_string() -> None:
    assert katex_formatter.parse_math_segments("") == []


def test_parse_math_segments_no_math() -> None:
    segs = katex_formatter.parse_math_segments("Hello, world!")
    assert segs == [{"type": "text", "content": "Hello, world!"}]


def test_parse_math_segments_display_dollar_dollar() -> None:
    segs = katex_formatter.parse_math_segments(r"here $$\frac{a}{b}$$ end")
    assert len(segs) == 3
    assert segs[0] == {"type": "text", "content": "here "}
    assert segs[1] == {"type": "math", "expression": r"\frac{a}{b}"}
    assert segs[2] == {"type": "text", "content": " end"}


def test_parse_math_segments_display_backslash_bracket() -> None:
    segs = katex_formatter.parse_math_segments(r"before \[\sum_{n=1}^{\infty} x\] after")
    assert len(segs) == 3
    assert segs[1] == {"type": "math", "expression": r"\sum_{n=1}^{\infty} x"}


def test_parse_math_segments_inline_backslash_paren() -> None:
    segs = katex_formatter.parse_math_segments(r"Euler: \(e^{i\pi}+1=0\).")
    assert len(segs) == 3
    assert segs[1] == {"type": "math", "expression": r"e^{i\pi}+1=0"}


def test_parse_math_segments_inline_single_dollar() -> None:
    segs = katex_formatter.parse_math_segments(r"value $\sqrt{2}$ here")
    assert len(segs) == 3
    assert segs[1] == {"type": "math", "expression": r"\sqrt{2}"}


def test_parse_math_segments_double_dollar_not_parsed_as_two_singles() -> None:
    """$$…$$ must be consumed as one display-math block, not two bare $."""
    segs = katex_formatter.parse_math_segments(r"$$x^2$$")
    assert len(segs) == 1
    assert segs[0] == {"type": "math", "expression": "x^2"}


def test_parse_math_segments_multiline_display_math() -> None:
    text = "$$\n\\int_0^\\infty e^{-x^2}\\,dx = \\frac{\\sqrt{\\pi}}{2}\n$$"
    segs = katex_formatter.parse_math_segments(text)
    assert len(segs) == 1
    assert segs[0]["type"] == "math"
    assert "\\int" in segs[0]["expression"]


def test_parse_math_segments_mixed_text_and_math() -> None:
    text = r"Euler: \(e^{i\pi}+1=0\). Also $$\frac{a}{b}$$."
    segs = katex_formatter.parse_math_segments(text)
    math_segs = [s for s in segs if s["type"] == "math"]
    assert len(math_segs) == 2
    assert math_segs[0]["expression"] == r"e^{i\pi}+1=0"
    assert math_segs[1]["expression"] == r"\frac{a}{b}"


def test_parse_math_segments_multiple_inline_dollars() -> None:
    text = r"Let $a$ and $b$ be integers."
    segs = katex_formatter.parse_math_segments(text)
    math_segs = [s for s in segs if s["type"] == "math"]
    assert len(math_segs) == 2
    assert math_segs[0]["expression"] == "a"
    assert math_segs[1]["expression"] == "b"


def test_parse_math_segments_matrix_in_display_math() -> None:
    text = r"$$\begin{bmatrix} a & b \\ c & d \end{bmatrix}$$"
    segs = katex_formatter.parse_math_segments(text)
    assert len(segs) == 1
    assert segs[0]["type"] == "math"
    assert "bmatrix" in segs[0]["expression"]


def test_parse_math_segments_preserves_surrounding_text() -> None:
    text = r"**Sum:** $$\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}$$ done"
    segs = katex_formatter.parse_math_segments(text)
    assert segs[0] == {"type": "text", "content": "**Sum:** "}
    assert segs[1]["type"] == "math"
    assert segs[2] == {"type": "text", "content": " done"}
