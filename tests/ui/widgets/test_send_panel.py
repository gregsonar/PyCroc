"""Pilot-тесты SendPanel с mock CrocRunner (Task 9)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Button, Checkbox, Input, Label, ProgressBar

from pycroc.core.events import (
    CodeEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    ProgressEvent,
)
from pycroc.core.options import CrocOptions
from pycroc.storage.config import ConfigStore, Profile
from pycroc.storage.history import TransferRecord
from pycroc.ui.widgets.file_picker import MultiSelectDirectoryTree
from pycroc.ui.widgets.qr_code import QrCodeWidget
from pycroc.ui.widgets.send_panel import SendPanel

# --- Fakes -----------------------------------------------------------------


class FakeRunner:
    """Отдаёт заскриптованные события; hold=True — ждёт cancel() после них."""

    def __init__(self, events: list[Event], hold: bool = False) -> None:
        self.sent: list[tuple[list[str], CrocOptions]] = []
        self.cancel_called = False
        self._events = list(events)
        self._hold = hold
        self._release = asyncio.Event()

    async def send(self, paths: list[str], options: CrocOptions) -> AsyncIterator[Event]:
        self.sent.append((list(paths), options))
        for event in self._events:
            yield event
            await asyncio.sleep(0)
        if self._hold:
            await self._release.wait()

    async def cancel(self) -> None:
        self.cancel_called = True
        self._release.set()


class FakeHistory:
    def __init__(self) -> None:
        self.records: list[TransferRecord] = []

    async def add(self, record: TransferRecord) -> int:
        self.records.append(record)
        return len(self.records)


class PanelApp(App[None]):
    def __init__(self, panel: SendPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


async def wait_transfer(panel: SendPanel) -> None:
    """Ждёт завершения worker-а передачи (не всех: у DirectoryTree вечный загрузчик)."""
    assert panel.transfer_worker is not None
    await panel.transfer_worker.wait()


def make_panel(
    tmp_path: Path, runner: Any, history: FakeHistory | None = None
) -> tuple[SendPanel, Path]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    file_path = data_dir / "file.txt"
    file_path.write_text("hello", encoding="utf-8")
    panel = SendPanel(
        runner=runner,
        history=history or FakeHistory(),
        config=ConfigStore(tmp_path / "config.toml"),
        start_path=data_dir,
    )
    return panel, file_path


# --- Сборка опций и вызов раннера -------------------------------------------


async def test_send_passes_selected_paths_and_form_options(tmp_path: Path) -> None:
    runner = FakeRunner([DoneEvent()])
    panel, file_path = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(120, 40)):
        panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        panel.query_one("#opt-relay", Input).value = "my.relay:9009"
        panel.query_one("#opt-exclude", Input).value = "node_modules, .git"
        panel.query_one("#opt-transfers", Input).value = "8"
        panel.query_one("#opt-auto-accept", Checkbox).value = False
        panel.action_send()
        await wait_transfer(panel)

    paths, options = runner.sent[0]
    assert paths == [str(file_path)]
    assert options.relay == "my.relay:9009"
    assert options.exclude == ("node_modules", ".git")
    assert options.transfers == 8
    assert options.auto_accept is False


async def test_send_button_click_triggers_transfer(tmp_path: Path) -> None:
    runner = FakeRunner([DoneEvent()])
    panel, file_path = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        await pilot.click("#send-button")
        await wait_transfer(panel)
    assert len(runner.sent) == 1


async def test_send_without_selection_warns_and_does_not_run(tmp_path: Path) -> None:
    runner = FakeRunner([DoneEvent()])
    panel, _ = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        panel.action_send()
        await pilot.pause()
    assert runner.sent == []


async def test_empty_form_fields_become_none(tmp_path: Path) -> None:
    runner = FakeRunner([DoneEvent()])
    panel, file_path = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(120, 40)):
        panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        panel.query_one("#opt-relay", Input).value = "   "  # только пробелы
        panel.action_send()
        await wait_transfer(panel)
    _, options = runner.sent[0]
    assert options.relay is None
    assert options.code is None
    assert options.exclude == ()


# --- Обновление UI по синтетическим событиям -----------------------------------


async def test_code_and_progress_events_update_widgets(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            CodeEvent(code="slow-tomato-almond"),
            ProgressEvent(direction="Sending", filename="file.txt", percent=42, rate="2.1 MB/s"),
        ],
        hold=True,
    )
    panel, file_path = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        panel.action_send()
        await pilot.pause()

        assert panel.query_one(QrCodeWidget).code == "slow-tomato-almond"
        assert str(panel.query_one("#send-code-text", Label).render()) == "slow-tomato-almond"
        assert panel.query_one("#send-progress", ProgressBar).progress == 42
        assert str(panel.query_one("#send-rate", Label).render()) == "2.1 MB/s"
        # во время передачи Send заблокирован, Cancel доступен
        assert panel.query_one("#send-button", Button).disabled is True
        assert panel.query_one("#cancel-button", Button).disabled is False

        panel.action_cancel()
        await wait_transfer(panel)


# --- Запись в историю ------------------------------------------------------------


async def test_done_event_records_history(tmp_path: Path) -> None:
    history = FakeHistory()
    runner = FakeRunner([CodeEvent(code="slow-tomato-almond"), DoneEvent()])
    panel, file_path = make_panel(tmp_path, runner, history)
    async with PanelApp(panel).run_test(size=(120, 40)):
        panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        panel.action_send()
        await wait_transfer(panel)

    [record] = history.records
    assert record.direction == "send"
    assert record.status == "done"
    assert record.filename == "file.txt"
    assert record.code == "slow-tomato-almond"
    assert record.finished_at is not None


async def test_error_event_records_history_error(tmp_path: Path) -> None:
    history = FakeHistory()
    runner = FakeRunner([ErrorEvent(message="could not connect to relay")])
    panel, file_path = make_panel(tmp_path, runner, history)
    async with PanelApp(panel).run_test(size=(120, 40)):
        panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        panel.action_send()
        await wait_transfer(panel)

    [record] = history.records
    assert record.status == "error"
    assert record.error_message == "could not connect to relay"


async def test_cancel_records_cancelled_status(tmp_path: Path) -> None:
    history = FakeHistory()
    runner = FakeRunner(
        [ProgressEvent(direction="Sending", filename="file.txt", percent=10, rate="1 kB/s")],
        hold=True,
    )
    panel, file_path = make_panel(tmp_path, runner, history)
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        panel.action_send()
        await pilot.pause()
        panel.action_cancel()
        await wait_transfer(panel)

    assert runner.cancel_called
    [record] = history.records
    assert record.status == "cancelled"


async def test_panel_removal_mid_transfer_does_not_crash(tmp_path: Path) -> None:
    """Закрытие/размонтирование панели посреди передачи не роняет worker."""
    runner = FakeRunner(
        [ProgressEvent(direction="Sending", filename="file.txt", percent=10, rate="1 kB/s")],
        hold=True,
    )
    panel, file_path = make_panel(tmp_path, runner)
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        panel.query_one(MultiSelectDirectoryTree).toggle(file_path)
        panel.action_send()
        await pilot.pause()
        await panel.remove()  # размонтирование при активной передаче
        await pilot.pause()
    # выход из контекста без исключений — worker завершился корректно


# --- Значения формы из активного профиля -------------------------------------------


async def test_form_defaults_come_from_active_profile(tmp_path: Path) -> None:
    config = ConfigStore(tmp_path / "config.toml")
    config.save_profile(
        Profile(
            "work",
            CrocOptions(relay="work.relay:9009", exclude=("node_modules",), no_compress=True),
        )
    )
    config.set_active_profile_name("work")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = SendPanel(
        runner=FakeRunner([]),
        history=FakeHistory(),
        config=config,
        start_path=data_dir,
    )
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert panel.query_one("#opt-relay", Input).value == "work.relay:9009"
        assert panel.query_one("#opt-exclude", Input).value == "node_modules"
        assert panel.query_one("#opt-no-compress", Checkbox).value is True
        assert panel.query_one("#opt-auto-accept", Checkbox).value is True


# --- MultiSelectDirectoryTree ---------------------------------------------------------


async def test_file_picker_toggle_and_selected_paths(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    file_a = data_dir / "a.txt"
    file_b = data_dir / "b.txt"
    file_a.write_text("a", encoding="utf-8")
    file_b.write_text("b", encoding="utf-8")

    class TreeApp(App[None]):
        def compose(self) -> ComposeResult:
            yield MultiSelectDirectoryTree(data_dir)

    app = TreeApp()
    async with app.run_test():
        tree = app.query_one(MultiSelectDirectoryTree)
        assert tree.selected_paths() == []
        tree.toggle(file_a)
        tree.toggle(file_b)
        assert tree.selected_paths() == [str(file_a), str(file_b)]
        tree.toggle(file_a)  # повторный toggle снимает отметку
        assert tree.selected_paths() == [str(file_b)]
        tree.clear_selection()
        assert tree.selected_paths() == []
        tree.action_toggle_selected()  # курсор на корне — отмечает его без падения
