"""End-to-end Pilot-тесты собранного приложения с mock CrocRunner (Task 13)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from textual.pilot import Pilot
from textual.widgets import Button, DataTable, Input, Label, TabbedContent

from pycroc.core.events import CodeEvent, DoneEvent, ErrorEvent, Event
from pycroc.core.exceptions import CrocNotFoundError
from pycroc.core.options import CrocOptions
from pycroc.storage.config import ConfigStore
from pycroc.storage.history import HistoryRepository, TransferRecord
from pycroc.ui.app import PyCrocApp
from pycroc.ui.widgets.file_picker import MultiSelectDirectoryTree
from pycroc.ui.widgets.history_panel import HistoryPanel
from pycroc.ui.widgets.receive_panel import ReceivePanel
from pycroc.ui.widgets.send_panel import SendPanel
from pycroc.ui.widgets.settings_panel import SettingsPanel

FAKE_CROC = str(Path(__file__).parent.parent / "fixtures" / "fake_croc.py")


class FakeRunner:
    """Mock CrocRunner для сквозных тестов приложения."""

    def __init__(self, events: list[Event], *, fail_check: bool = False) -> None:
        self.sent: list[tuple[list[str], CrocOptions]] = []
        self.received: list[tuple[str, CrocOptions]] = []
        self.binary: str | None = None
        self._events = list(events)
        self._fail_check = fail_check

    async def check_binary(self) -> str:
        if self._fail_check:
            raise CrocNotFoundError("нет такого бинарника")
        return "v10.0.0-fake"

    def set_binary(self, binary_path: str) -> None:
        self.binary = binary_path

    async def send(self, paths: list[str], options: CrocOptions) -> AsyncIterator[Event]:
        self.sent.append((list(paths), options))
        for event in self._events:
            yield event
            await asyncio.sleep(0)

    async def receive(self, code: str, options: CrocOptions) -> AsyncIterator[Event]:
        self.received.append((code, options))
        for event in self._events:
            yield event
            await asyncio.sleep(0)

    async def cancel(self) -> None:
        pass

    async def respond(self, accept: bool) -> None:
        pass


def make_app(tmp_path: Path, runner: FakeRunner) -> PyCrocApp:
    return PyCrocApp(
        config=ConfigStore(tmp_path / "config.toml"),
        history=HistoryRepository(tmp_path / "history.db"),
        runner=runner,  # type: ignore[arg-type]
        send_start_path=tmp_path,
    )


async def _open_history_and_wait(app: PyCrocApp, pilot: Pilot[None]) -> HistoryPanel:
    """Переключается на History и ждёт worker обновления таблицы (on_show)."""
    history_panel = app.query_one(HistoryPanel)
    history_panel.ops_worker = None
    app.query_one(TabbedContent).active = "history"
    for _ in range(20):
        await pilot.pause()
        if history_panel.ops_worker is not None:
            break
    assert history_panel.ops_worker is not None, "on_show не запустил обновление таблицы"
    await history_panel.ops_worker.wait()
    await pilot.pause()
    return history_panel


# --- Полный цикл: Send -> DoneEvent -> запись видна в History ---------------------


async def test_full_send_cycle_record_visible_in_history(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello", encoding="utf-8")
    runner = FakeRunner([CodeEvent(code="slow-tomato-almond"), DoneEvent()])
    app = make_app(tmp_path, runner)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        send_panel = app.query_one(SendPanel)
        send_panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        send_panel.query_one("#opt-relay", Input).value = "my.relay:9009"
        send_panel.action_send()
        assert send_panel.transfer_worker is not None
        await send_panel.transfer_worker.wait()

        history_panel = await _open_history_and_wait(app, pilot)
        table = history_panel.query_one(DataTable)
        assert table.row_count == 1
        row = table.get_row_at(0)
        assert row[1] == "file.txt"
        assert row[4] == "done"

    [(paths, options)] = runner.sent
    assert paths == [str(file_path)]
    assert options.relay == "my.relay:9009"


# --- Блокировка вкладок без croc и разблокировка из Settings ------------------------


async def test_settings_check_reenables_tabs_and_swaps_runner(tmp_path: Path) -> None:
    runner = FakeRunner([], fail_check=True)
    app = make_app(tmp_path, runner)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        tabbed = app.query_one(TabbedContent)
        assert tabbed.get_tab("send").disabled is True
        assert tabbed.active == "settings"

        settings_panel = app.query_one(SettingsPanel)
        settings_panel.query_one("#binary-path", Input).value = FAKE_CROC
        settings_panel.query_one("#binary-check", Button).press()
        for _ in range(20):
            await pilot.pause()
            if settings_panel.ops_worker is not None:
                break
        assert settings_panel.ops_worker is not None
        await settings_panel.ops_worker.wait()
        await pilot.pause()

        assert app.croc_version == "v10.0.0-fake"
        assert runner.binary == FAKE_CROC  # раннер переключён на новый путь
        assert tabbed.get_tab("send").disabled is False
        assert tabbed.get_tab("receive").disabled is False


# --- Повторить из History -------------------------------------------------------------


def _history_record(direction: str, code: str) -> TransferRecord:
    return TransferRecord(
        id=None,
        direction=direction,  # type: ignore[arg-type]
        filename="file.txt",
        size_bytes=116,
        code=code,
        status="done",
        started_at=datetime(2026, 7, 13, 12, 0),
        finished_at=None,
        error_message=None,
    )


async def test_repeat_receive_switches_tab_and_prefills_code(tmp_path: Path) -> None:
    runner = FakeRunner([])
    app = make_app(tmp_path, runner)
    await app.history.add(_history_record("receive", "slow-tomato-almond"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        history_panel = await _open_history_and_wait(app, pilot)
        record = next(iter(history_panel._records.values()))
        history_panel.post_message(HistoryPanel.RepeatTransfer(record))
        await pilot.pause()

        assert app.query_one(TabbedContent).active == "receive"
        code_input = app.query_one(ReceivePanel).query_one("#receive-code", Input)
        assert code_input.value == "slow-tomato-almond"


async def test_repeat_send_switches_tab_and_prefills_code_option(tmp_path: Path) -> None:
    runner = FakeRunner([])
    app = make_app(tmp_path, runner)
    await app.history.add(_history_record("send", "fast-banana-apple"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        history_panel = await _open_history_and_wait(app, pilot)
        record = next(iter(history_panel._records.values()))
        history_panel.post_message(HistoryPanel.RepeatTransfer(record))
        await pilot.pause()

        assert app.query_one(TabbedContent).active == "send"
        code_input = app.query_one(SendPanel).query_one("#opt-code", Input)
        assert code_input.value == "fast-banana-apple"


# --- Сквозные уведомления об ошибках ----------------------------------------------------


async def test_error_event_notifies_while_on_another_tab(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello", encoding="utf-8")
    runner = FakeRunner([ErrorEvent(message="could not connect to relay")])
    app = make_app(tmp_path, runner)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        send_panel = app.query_one(SendPanel)
        send_panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        send_panel.action_send()
        # сразу уходим на другую вкладку: уведомление должно быть видно и там
        app.query_one(TabbedContent).active = "settings"
        assert send_panel.transfer_worker is not None
        await send_panel.transfer_worker.wait()
        await pilot.pause()

        messages = [n.message for n in app._notifications]
        assert any("could not connect to relay" in m for m in messages)

        status = str(send_panel.query_one("#send-status", Label).render())
        assert status == "Ошибка"
