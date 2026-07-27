"""Pilot-тесты ReceivePanel и OverwriteConflictModal с mock CrocRunner (Task 10)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Button, Checkbox, Input, Label, ProgressBar

from pycroc.core.events import (
    AcceptPromptEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    ProgressEvent,
    TransferStartEvent,
)
from pycroc.core.options import CrocOptions
from pycroc.storage.config import ConfigStore, Profile
from pycroc.storage.history import TransferRecord
from pycroc.ui.widgets.overwrite_modal import OverwriteConflictModal
from pycroc.ui.widgets.receive_panel import (
    _CONNECT_FAILED_HINT,
    HistoryCodeSuggester,
    ReceivePanel,
    _failure_message,
)

# --- Fakes -----------------------------------------------------------------


class FakeRunner:
    """Отдаёт заскриптованные события; hold=True — ждёт respond()/cancel()."""

    def __init__(self, events: list[Event], hold: bool = False) -> None:
        self.received: list[tuple[str, CrocOptions]] = []
        self.responses: list[bool] = []
        self.cancel_called = False
        self._events = list(events)
        self._hold = hold
        self._release = asyncio.Event()

    async def receive(self, code: str, options: CrocOptions) -> AsyncIterator[Event]:
        self.received.append((code, options))
        for event in self._events:
            yield event
            await asyncio.sleep(0)
        if self._hold:
            await self._release.wait()

    async def respond(self, accept: bool) -> None:
        self.responses.append(accept)
        self._release.set()

    async def cancel(self) -> None:
        self.cancel_called = True
        self._release.set()


class FakeHistory:
    def __init__(self, records: list[TransferRecord] | None = None) -> None:
        self.records: list[TransferRecord] = list(records or [])

    async def add(self, record: TransferRecord) -> int:
        self.records.append(record)
        return len(self.records)

    async def list(
        self, limit: int = 200, query: str | None = None
    ) -> list[TransferRecord]:
        return list(reversed(self.records))[:limit]  # новые — раньше


def _record(code: str) -> TransferRecord:
    return TransferRecord(
        id=None,
        direction="receive",
        filename="file.txt",
        size_bytes=None,
        code=code,
        status="done",
        started_at=datetime(2026, 7, 13, 12, 0),
        finished_at=None,
        error_message=None,
    )


class PanelApp(App[None]):
    def __init__(self, panel: ReceivePanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def make_panel(
    tmp_path: Path, runner: Any, history: FakeHistory | None = None
) -> ReceivePanel:
    return ReceivePanel(
        runner=runner,
        history=history or FakeHistory(),
        config=ConfigStore(tmp_path / "config.toml"),
    )


async def wait_transfer(panel: ReceivePanel) -> None:
    assert panel.transfer_worker is not None
    await panel.transfer_worker.wait()


async def wait_for_modal(pilot: Pilot[None], app: App[None]) -> None:
    for _ in range(20):
        if isinstance(app.screen, OverwriteConflictModal):
            return
        await pilot.pause()
    raise AssertionError("модалка не открылась")


# --- Запуск приёма ------------------------------------------------------------


async def test_receive_called_with_code_and_form_options(tmp_path: Path) -> None:
    runner = FakeRunner([DoneEvent()])
    panel = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(100, 35)):
        panel.query_one("#receive-code", Input).value = " slow-tomato-almond "
        panel.query_one("#receive-out", Input).value = "C:/downloads"
        panel.query_one("#receive-auto-accept", Checkbox).value = False
        panel.action_receive()
        await wait_transfer(panel)

    [(code, options)] = runner.received
    assert code == "slow-tomato-almond"  # нормализован strip-ом
    assert options.out_dir == "C:/downloads"
    assert options.auto_accept is False


async def test_receive_button_click_triggers_transfer(tmp_path: Path) -> None:
    runner = FakeRunner([DoneEvent()])
    panel = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(100, 35)) as pilot:
        panel.query_one("#receive-code", Input).value = "a-b-c"
        await pilot.click("#receive-button")
        await wait_transfer(panel)
    assert len(runner.received) == 1


async def test_empty_code_warns_and_does_not_run(tmp_path: Path) -> None:
    runner = FakeRunner([DoneEvent()])
    panel = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(100, 35)) as pilot:
        panel.query_one("#receive-code", Input).value = "   "
        panel.action_receive()
        await pilot.pause()
    assert runner.received == []


async def test_profile_options_flow_into_receive(tmp_path: Path) -> None:
    config = ConfigStore(tmp_path / "config.toml")
    config.save_profile(
        Profile("work", CrocOptions(relay="work.relay:9009", out_dir="D:/incoming"))
    )
    config.set_active_profile_name("work")
    runner = FakeRunner([DoneEvent()])
    panel = ReceivePanel(runner=runner, history=FakeHistory(), config=config)
    async with PanelApp(panel).run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        # out_dir профиля предзаполнил поле
        assert panel.query_one("#receive-out", Input).value == "D:/incoming"
        panel.query_one("#receive-code", Input).value = "a-b-c"
        panel.action_receive()
        await wait_transfer(panel)

    [(_, options)] = runner.received
    assert options.relay == "work.relay:9009"  # из профиля, поля на панели нет
    assert options.out_dir == "D:/incoming"


# --- Обновление UI по событиям ---------------------------------------------------


async def test_progress_events_update_widgets_and_buttons(tmp_path: Path) -> None:
    runner = FakeRunner(
        [ProgressEvent(direction="Receiving", filename="file.txt", percent=42, rate="2.1 MB/s")],
        hold=True,
    )
    panel = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(100, 35)) as pilot:
        panel.query_one("#receive-code", Input).value = "a-b-c"
        panel.action_receive()
        await pilot.pause()

        assert panel.query_one("#receive-progress", ProgressBar).progress == 42
        assert str(panel.query_one("#receive-rate", Label).render()) == "2.1 MB/s"
        assert panel.query_one("#receive-button", Button).disabled is True
        assert panel.query_one("#receive-cancel-button", Button).disabled is False

        panel.action_cancel()
        await wait_transfer(panel)
    assert runner.cancel_called


# --- OverwriteConflictModal --------------------------------------------------------


async def test_accept_prompt_opens_modal_and_no_sends_reject(tmp_path: Path) -> None:
    runner = FakeRunner(
        [AcceptPromptEvent(filename="file.txt", size="116 B")], hold=True
    )
    panel = make_panel(tmp_path, runner)
    app = PanelApp(panel)
    async with app.run_test(size=(100, 35)) as pilot:
        panel.query_one("#receive-code", Input).value = "a-b-c"
        panel.query_one("#receive-auto-accept", Checkbox).value = False
        panel.action_receive()
        await wait_for_modal(pilot, app)
        await pilot.click("#modal-no")
        await wait_transfer(panel)

    # respond(False) — на уровне CrocRunner это n\n в stdin (тест Task 4)
    assert runner.responses == [False]


async def test_accept_prompt_yes_sends_accept(tmp_path: Path) -> None:
    runner = FakeRunner(
        [AcceptPromptEvent(filename="file.txt", size="116 B")], hold=True
    )
    panel = make_panel(tmp_path, runner)
    app = PanelApp(panel)
    async with app.run_test(size=(100, 35)) as pilot:
        panel.query_one("#receive-code", Input).value = "a-b-c"
        panel.query_one("#receive-auto-accept", Checkbox).value = False
        panel.action_receive()
        await wait_for_modal(pilot, app)
        await pilot.click("#modal-yes")
        await wait_transfer(panel)

    assert runner.responses == [True]


# --- Запись в историю ---------------------------------------------------------------


async def test_done_event_records_receive_history(tmp_path: Path) -> None:
    history = FakeHistory()
    runner = FakeRunner(
        [
            ProgressEvent(direction="Receiving", filename="report.pdf", percent=100, rate="1 MB/s"),
            DoneEvent(),
        ]
    )
    panel = make_panel(tmp_path, runner, history)
    async with PanelApp(panel).run_test(size=(100, 35)):
        panel.query_one("#receive-code", Input).value = "slow-tomato-almond"
        panel.action_receive()
        await wait_transfer(panel)

    [record] = history.records
    assert record.direction == "receive"
    assert record.status == "done"
    assert record.filename == "report.pdf"
    assert record.code == "slow-tomato-almond"


async def test_transfer_start_size_stored_in_receive_history(tmp_path: Path) -> None:
    """Пункт 9 конспекта: размер из TransferStartEvent попадает в size_bytes."""
    history = FakeHistory()
    runner = FakeRunner(
        [TransferStartEvent(filename="report.pdf", size="2.1 MB"), DoneEvent()]
    )
    panel = make_panel(tmp_path, runner, history)
    async with PanelApp(panel).run_test(size=(100, 35)):
        panel.query_one("#receive-code", Input).value = "a-b-c"
        panel.action_receive()
        await wait_transfer(panel)

    [record] = history.records
    assert record.size_bytes == 2_100_000  # 2.1 MB (SI)


async def test_error_before_connect_shows_friendly_hint(tmp_path: Path) -> None:
    """Пункт 13: ошибка ДО подключения → понятная подсказка, не сырой croc."""
    history = FakeHistory()
    runner = FakeRunner([ErrorEvent(message="connecting...\nsecuring channel...")])
    panel = make_panel(tmp_path, runner, history)
    app = PanelApp(panel)
    async with app.run_test(size=(100, 35)):
        panel.query_one("#receive-code", Input).value = "a-b-c"
        panel.action_receive()
        await wait_transfer(panel)

    [record] = history.records
    assert record.status == "error"
    assert record.error_message == _CONNECT_FAILED_HINT
    assert any(_CONNECT_FAILED_HINT in n.message for n in app._notifications)


async def test_error_after_connect_keeps_raw_message(tmp_path: Path) -> None:
    """Если обмен уже начался, показываем реальную ошибку croc, не подсказку."""
    history = FakeHistory()
    runner = FakeRunner([
        ProgressEvent(direction="Receiving", filename="f.bin", percent=40, rate="1 MB/s"),
        ErrorEvent(message="write error: disk full"),
    ])
    panel = make_panel(tmp_path, runner, history)
    async with PanelApp(panel).run_test(size=(100, 35)):
        panel.query_one("#receive-code", Input).value = "a-b-c"
        panel.action_receive()
        await wait_transfer(panel)

    [record] = history.records
    assert record.status == "error"
    assert record.error_message == "write error: disk full"


def test_failure_message_helper() -> None:
    assert _failure_message("connecting...", connected=False) == _CONNECT_FAILED_HINT
    assert _failure_message("disk full", connected=True) == "disk full"


# --- Автодополнение из истории --------------------------------------------------------


async def test_suggester_completes_from_history_newest_first() -> None:
    history = FakeHistory(
        [_record("slow-old-code"), _record("slow-tomato-almond")]  # второй новее
    )
    suggester = HistoryCodeSuggester(history)  # type: ignore[arg-type]
    assert await suggester.get_suggestion("slow") == "slow-tomato-almond"
    assert await suggester.get_suggestion("slow-old") == "slow-old-code"
    assert await suggester.get_suggestion("zzz") is None
    assert await suggester.get_suggestion("") is None
    # полностью введённый код не подсказывается сам собой
    assert await suggester.get_suggestion("slow-tomato-almond") is None
