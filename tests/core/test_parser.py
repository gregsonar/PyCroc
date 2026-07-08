"""Тесты парсера stderr croc (Task 3)."""

from __future__ import annotations

from pathlib import Path

from pycroc.core.events import (
    AcceptPromptEvent,
    CodeEvent,
    ErrorEvent,
    ProgressEvent,
    TransferStartEvent,
)
from pycroc.core.parser import parse_line, split_stream_chunks

FIXTURES = Path(__file__).parent.parent / "fixtures"

# --- Одиночные строки (тест-кейсы из плана) -------------------------------------


def test_code_line() -> None:
    assert parse_line("Code is: slow-tomato-almond") == CodeEvent(code="slow-tomato-almond")


def test_receiving_progress_line_with_checkmark() -> None:
    line = (
        "Receiving (<-192.168.225.37:9009) file.txt 100% "
        "|████████████████████| (116/116 B, 32.966 kB/s) [0s:0s] ✔️"
    )
    assert parse_line(line) == ProgressEvent(
        direction="Receiving", filename="file.txt", percent=100, rate="32.966 kB/s"
    )


def test_sending_progress_line_without_checkmark() -> None:
    line = "Sending (->192.168.0.5:9009) report.pdf  42% |████      | (49/116 MB, 2.1 MB/s) [1s:2s]"
    assert parse_line(line) == ProgressEvent(
        direction="Sending", filename="report.pdf", percent=42, rate="2.1 MB/s"
    )


def test_sending_init_line() -> None:
    assert parse_line("Sending 'file.txt' (116 B)") == TransferStartEvent(
        filename="file.txt", size="116 B"
    )


def test_accept_prompt_line() -> None:
    assert parse_line("Accept 'file.txt' (116 B)? (y/n) ") == AcceptPromptEvent(
        filename="file.txt", size="116 B"
    )


def test_error_lines() -> None:
    assert parse_line("Error: could not connect to relay") == ErrorEvent(
        message="Error: could not connect to relay"
    )
    assert parse_line("failed to connect: dial tcp: i/o timeout") == ErrorEvent(
        message="failed to connect: dial tcp: i/o timeout"
    )


def test_unknown_line_returns_none() -> None:
    assert parse_line("some future unknown croc output format") is None


def test_blank_line_returns_none() -> None:
    assert parse_line("") is None
    assert parse_line("   ") is None


def test_multifile_progress_matches_each_filename() -> None:
    lines = [
        "Receiving (<-10.0.0.2:9009) a.jpg 100% |████| (2.1/2.1 MB, 8.4 MB/s) [1s:0s] ✔️",
        "Receiving (<-10.0.0.2:9009) b.jpg  47% |██  | (1.0/2.1 MB, 7.9 MB/s) [0s:1s]",
    ]
    events = [parse_line(line) for line in lines]
    assert [e.filename for e in events if isinstance(e, ProgressEvent)] == ["a.jpg", "b.jpg"]


# --- Корпус зафиксированных строк ------------------------------------------------


def test_fixture_corpus_event_sequence() -> None:
    """Каждая строка фикстуры разбирается в ожидаемый тип события (или None)."""
    lines = (FIXTURES / "croc_stderr_samples.txt").read_text(encoding="utf-8").splitlines()
    expected: list[type | None] = [
        TransferStartEvent,  # Sending 'file.txt' (116 B)
        CodeEvent,  # Code is: slow-tomato-almond
        None,  # On the other computer run
        None,  # (пустая строка)
        None,  # croc slow-tomato-almond
        ProgressEvent,  # 0%
        ProgressEvent,  # 50%
        ProgressEvent,  # 100% ✔️
        AcceptPromptEvent,
        ProgressEvent,  # Receiving 100% ✔️
        ProgressEvent,  # IMG_0001.jpg 100%
        ProgressEvent,  # IMG_0002.jpg 47%
        ErrorEvent,
        ErrorEvent,
        None,  # неизвестный будущий формат
    ]
    assert len(lines) == len(expected), "фикстура и список ожиданий рассинхронизированы"
    got = [type(e) if (e := parse_line(line)) is not None else None for line in lines]
    assert got == expected


def test_fixture_progress_percents_grow_within_file() -> None:
    lines = (FIXTURES / "croc_stderr_samples.txt").read_text(encoding="utf-8").splitlines()
    events = [parse_line(line) for line in lines]
    send_percents = [
        e.percent
        for e in events
        if isinstance(e, ProgressEvent) and e.direction == "Sending" and e.filename == "file.txt"
    ]
    assert send_percents == [0, 50, 100]


# --- split_stream_chunks: буферизация по \r/\n ------------------------------------


def _drain(raw: bytes, chunk_size: int) -> list[str]:
    """Эмулирует цикл CrocRunner: кормит буфер кусками, по EOF сливает остаток."""
    lines: list[str] = []
    buffer = b""
    for start in range(0, len(raw), chunk_size):
        buffer += raw[start : start + chunk_size]
        complete, buffer = split_stream_chunks(buffer)
        lines.extend(complete)
    if buffer:
        lines.append(buffer.decode("utf-8", errors="replace"))
    return lines


def test_cr_separated_progress_without_newline_keeps_final_update() -> None:
    """Прогресс перерисовывается через \\r без единого \\n до конца передачи."""
    raw = (
        "Sending (->1.2.3.4:9009) f.txt  10% |█   | (12/116 B, 1 kB/s) [0s:0s]\r"
        "Sending (->1.2.3.4:9009) f.txt  55% |██  | (64/116 B, 1 kB/s) [0s:0s]\r"
        "Sending (->1.2.3.4:9009) f.txt 100% |████| (116/116 B, 1 kB/s) [0s:0s] ✔️"
    ).encode()
    # chunk_size=7 гарантирует разрезы посреди строк и мультибайтовых символов
    lines = _drain(raw, chunk_size=7)
    percents = [e.percent for e in map(parse_line, lines) if isinstance(e, ProgressEvent)]
    assert percents == [10, 55, 100]


def test_crlf_split_across_chunk_boundary() -> None:
    """\\r в конце чанка не даёт ложной пустой строки, если следом придёт \\n."""
    first, remainder = split_stream_chunks(b"abc\r")
    assert first == []
    assert remainder == b"abc\r"
    lines, remainder = split_stream_chunks(remainder + b"\ndef\n")
    assert lines == ["abc", "def"]
    assert remainder == b""


def test_lone_cr_flushed_on_next_data() -> None:
    lines, remainder = split_stream_chunks(b"abc\r" + b"xyz")
    assert lines == ["abc"]
    assert remainder == b"xyz"


def test_incomplete_line_stays_in_remainder() -> None:
    lines, remainder = split_stream_chunks(b"Code is: slow-tom")
    assert lines == []
    assert remainder == b"Code is: slow-tom"
