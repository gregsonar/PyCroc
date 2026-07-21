"""Интеграционные тесты CrocRunner против заглушки fake_croc.py (Task 4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pycroc.core.events import (
    AcceptPromptEvent,
    CodeEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    ProgressEvent,
    TransferStartEvent,
)
from pycroc.core.exceptions import CrocNotFoundError, TransferInProgressError
from pycroc.core.options import CrocOptions
from pycroc.core.runner import CrocRunner

FAKE_CROC = str(Path(__file__).parent.parent / "fixtures" / "fake_croc.py")


def _progress(percent: int, suffix: str = "") -> str:
    return (
        f"Sending (->1.2.3.4:9009) file.txt {percent:3d}% |██        | "
        f"({percent}/100 B, 1.5 kB/s) [0s:0s]{suffix}"
    )


def _write_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    steps: list[dict[str, Any]],
    exit_code: int = 0,
    stdin_capture: Path | None = None,
    invocation_capture: Path | None = None,
) -> None:
    scenario: dict[str, Any] = {"steps": steps, "exit_code": exit_code}
    if stdin_capture is not None:
        scenario["stdin_capture"] = str(stdin_capture)
    if invocation_capture is not None:
        scenario["invocation_capture"] = str(invocation_capture)
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    monkeypatch.setenv("PYCROC_FAKE_CROC_SCENARIO", str(scenario_path))


# --- Успешный сценарий: порядок событий -----------------------------------------


async def test_send_success_yields_events_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_scenario(
        tmp_path,
        monkeypatch,
        [
            {"line": "Sending 'file.txt' (116 B)"},
            {"line": "Code is: slow-tomato-almond"},
            {"line": _progress(10), "end": "\r", "delay": 0.01},
            {"line": _progress(55), "end": "\r", "delay": 0.01},
            {"line": _progress(100, " ✔️"), "delay": 0.01},
        ],
    )
    runner = CrocRunner(binary_path=FAKE_CROC)
    events = [event async for event in runner.send(["file.txt"], CrocOptions())]

    assert events[0] == TransferStartEvent(filename="file.txt", size="116 B")
    assert events[1] == CodeEvent(code="slow-tomato-almond")
    percents = [e.percent for e in events if isinstance(e, ProgressEvent)]
    assert percents == [10, 55, 100]
    assert isinstance(events[-1], DoneEvent)


# --- Ошибки ----------------------------------------------------------------------


async def test_unrecognized_failure_falls_back_to_stderr_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_scenario(
        tmp_path,
        monkeypatch,
        [
            {"line": "panic: something exploded in a new format"},
            {"line": "goroutine 1 [running]:"},
        ],
        exit_code=1,
    )
    runner = CrocRunner(binary_path=FAKE_CROC)
    events = [event async for event in runner.send(["file.txt"], CrocOptions())]

    assert isinstance(events[-1], ErrorEvent)
    assert "panic: something exploded in a new format" in events[-1].message
    assert "goroutine 1 [running]:" in events[-1].message


async def test_explicit_error_line_is_not_duplicated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_scenario(
        tmp_path,
        monkeypatch,
        [{"line": "Error: could not connect to relay"}],
        exit_code=1,
    )
    runner = CrocRunner(binary_path=FAKE_CROC)
    events = [event async for event in runner.send(["file.txt"], CrocOptions())]

    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert errors == [ErrorEvent(message="Error: could not connect to relay")]


# --- Отмена ----------------------------------------------------------------------


async def test_cancel_during_transfer_ends_generator_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_scenario(
        tmp_path,
        monkeypatch,
        [
            {"line": _progress(10)},
            {"delay": 30},
            {"line": _progress(100)},
        ],
    )
    runner = CrocRunner(binary_path=FAKE_CROC)
    events: list[Event] = []
    async for event in runner.send(["file.txt"], CrocOptions()):
        events.append(event)
        if isinstance(event, ProgressEvent):
            await runner.cancel()

    assert [e.percent for e in events if isinstance(e, ProgressEvent)] == [10]
    assert not any(isinstance(e, ErrorEvent | DoneEvent) for e in events)


# --- Параллельный запуск ----------------------------------------------------------


async def test_second_transfer_while_active_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_scenario(
        tmp_path,
        monkeypatch,
        [{"line": "Code is: x-y-z"}, {"delay": 30}],
    )
    runner = CrocRunner(binary_path=FAKE_CROC)
    first_gen = runner.send(["file.txt"], CrocOptions())
    assert await anext(first_gen) == CodeEvent(code="x-y-z")

    second_gen = runner.receive("a-b-c", CrocOptions())
    with pytest.raises(TransferInProgressError):
        await anext(second_gen)

    await runner.cancel()
    assert [event async for event in first_gen] == []


# --- Отсутствие бинарника ----------------------------------------------------------


async def test_check_binary_missing_raises() -> None:
    runner = CrocRunner(binary_path="definitely-missing-croc-binary-xyz")
    with pytest.raises(CrocNotFoundError):
        await runner.check_binary()


async def test_send_with_missing_binary_raises() -> None:
    runner = CrocRunner(binary_path="definitely-missing-croc-binary-xyz")
    with pytest.raises(CrocNotFoundError):
        await anext(runner.send(["file.txt"], CrocOptions()))


async def test_check_binary_returns_version() -> None:
    assert await CrocRunner(binary_path=FAKE_CROC).check_binary() == "v10.0.0-fake"


# --- Автоответ на Accept-prompt -----------------------------------------------------

_ACCEPT_STEPS: list[dict[str, Any]] = [
    # croc печатает prompt без перевода строки и блокируется на stdin
    {"line": "Accept 'file.txt' (116 B)? (y/n) ", "end": ""},
    {"wait_stdin": True},
]


async def test_auto_accept_writes_y_and_suppresses_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "stdin_capture.txt"
    receiving = (
        "Receiving (<-1.2.3.4:9009) file.txt 100% |████| (116/116 B, 1 kB/s) [0s:0s] ✔️"
    )
    _write_scenario(
        tmp_path,
        monkeypatch,
        [*_ACCEPT_STEPS, {"line": receiving}],
        stdin_capture=capture,
    )
    runner = CrocRunner(binary_path=FAKE_CROC)
    events = [
        event async for event in runner.receive("a-b-c", CrocOptions(auto_accept=True))
    ]

    assert capture.read_text(encoding="utf-8") == "y\n"
    assert not any(isinstance(e, AcceptPromptEvent) for e in events)
    assert [e.percent for e in events if isinstance(e, ProgressEvent)] == [100]
    assert isinstance(events[-1], DoneEvent)


async def test_manual_reject_writes_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "stdin_capture.txt"
    _write_scenario(tmp_path, monkeypatch, _ACCEPT_STEPS, stdin_capture=capture)
    runner = CrocRunner(binary_path=FAKE_CROC)
    events: list[Event] = []
    async for event in runner.receive("a-b-c", CrocOptions(auto_accept=False)):
        events.append(event)
        if isinstance(event, AcceptPromptEvent):
            await runner.respond(accept=False)

    assert capture.read_text(encoding="utf-8") == "n\n"
    assert events[0] == AcceptPromptEvent(filename="file.txt", size="116 B")


# --- CROC_SECRET: кодовая фраза через окружение, не через argv -------------------


async def test_send_code_passed_via_env_not_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invocation = tmp_path / "invocation.json"
    _write_scenario(
        tmp_path,
        monkeypatch,
        [{"line": "Code is: slow-tomato-almond"}],
        invocation_capture=invocation,
    )
    runner = CrocRunner(binary_path=FAKE_CROC)
    async for _ in runner.send(["file.txt"], CrocOptions(code="slow-tomato-almond")):
        pass

    captured = json.loads(invocation.read_text(encoding="utf-8"))
    assert captured["croc_secret"] == "slow-tomato-almond"
    assert "slow-tomato-almond" not in captured["argv"]
    assert "--code" not in captured["argv"]


async def test_receive_code_passed_via_env_not_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invocation = tmp_path / "invocation.json"
    _write_scenario(tmp_path, monkeypatch, [], invocation_capture=invocation)
    runner = CrocRunner(binary_path=FAKE_CROC)
    async for _ in runner.receive("slow-tomato-almond", CrocOptions()):
        pass

    captured = json.loads(invocation.read_text(encoding="utf-8"))
    assert captured["croc_secret"] == "slow-tomato-almond"
    assert "slow-tomato-almond" not in captured["argv"]


async def test_send_without_custom_code_sets_no_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CROC_SECRET", raising=False)  # чистое окружение теста
    invocation = tmp_path / "invocation.json"
    _write_scenario(
        tmp_path,
        monkeypatch,
        [{"line": "Code is: generated-by-croc"}],
        invocation_capture=invocation,
    )
    runner = CrocRunner(binary_path=FAKE_CROC)
    async for _ in runner.send(["file.txt"], CrocOptions()):
        pass

    # без своего кода CROC_SECRET не выставляется — croc генерирует фразу сам
    captured = json.loads(invocation.read_text(encoding="utf-8"))
    assert captured["croc_secret"] is None
