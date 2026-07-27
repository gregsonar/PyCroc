"""Тесты форматирования и разбора размеров (пункт 9 конспекта)."""

from __future__ import annotations

import pytest

from pycroc.core.units import format_size, parse_size

# --- format_size (SI, база 1000, как у croc) ---------------------------------


def test_format_size_none_is_dash() -> None:
    assert format_size(None) == "—"


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (0, "0 B"),
        (116, "116 B"),
        (999, "999 B"),
        (6200, "6.2 kB"),
        (512_000, "512.0 kB"),
        (2_100_000, "2.1 MB"),
        (3_000_000_000, "3.0 GB"),
        (1_500_000_000_000, "1.5 TB"),
    ],
)
def test_format_size_units(size_bytes: int, expected: str) -> None:
    assert format_size(size_bytes) == expected


# --- parse_size (обратный разбор строк croc) ---------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("116 B", 116),
        ("6.2 kB", 6200),
        ("512.0 kB", 512_000),
        ("2.1 MB", 2_100_000),
        ("5.0 kB", 5000),
        ("1.5 GB", 1_500_000_000),
        ("116B", 116),  # без пробела
        (" 6.2 kB ", 6200),  # с пробелами по краям
    ],
)
def test_parse_size_known_formats(text: str, expected: int) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "неизвестно", "5 QB", "abc kB", None])
def test_parse_size_bad_input_returns_none(text: str | None) -> None:
    assert parse_size(text) is None


# --- round-trip: строка croc -> байты -> та же строка ------------------------


@pytest.mark.parametrize("text", ["116 B", "6.2 kB", "512.0 kB", "2.1 MB", "3.0 GB"])
def test_parse_then_format_round_trips_to_croc_string(text: str) -> None:
    # размер, разобранный из строки croc и заново отформатированный, совпадает
    # с исходной строкой croc — история покажет ровно то, что croc показал
    parsed = parse_size(text)
    assert parsed is not None
    assert format_size(parsed) == text
