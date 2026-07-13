"""Pilot-тесты HistoryPanel (Task 11)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input

from pycroc.storage.history import TransferRecord
from pycroc.ui.widgets.history_panel import HistoryPanel, _format_size

# --- Fakes -----------------------------------------------------------------


def _record(record_id: int, filename: str, *, code: str = "a-b-c") -> TransferRecord:
    return TransferRecord(
        id=record_id,
        direction="send",
        filename=filename,
        size_bytes=116,
        code=code,
        status="done",
        # id растёт вместе со временем: больший id = новее
        started_at=datetime(2026, 7, 1 + record_id, 12, 0),
        finished_at=None,
        error_message=None,
    )


class FakeHistory:
    def __init__(self, records: list[TransferRecord]) -> None:
        self.records = list(records)
        self.deleted: list[int] = []

    async def list(
        self, limit: int = 200, query: str | None = None
    ) -> list[TransferRecord]:
        result = sorted(self.records, key=lambda r: r.started_at, reverse=True)
        if query:
            needle = query.casefold()
            result = [r for r in result if needle in r.filename.casefold()]
        return result[:limit]

    async def delete(self, record_id: int) -> None:
        self.deleted.append(record_id)
        self.records = [r for r in self.records if r.id != record_id]


class PanelApp(App[None]):
    def __init__(self, panel: HistoryPanel) -> None:
        super().__init__()
        self._panel = panel
        self.repeats: list[TransferRecord] = []

    def compose(self) -> ComposeResult:
        yield self._panel

    def on_history_panel_repeat_transfer(
        self, message: HistoryPanel.RepeatTransfer
    ) -> None:
        self.repeats.append(message.record)


def make_panel(records: list[TransferRecord], history: Any = None) -> HistoryPanel:
    return HistoryPanel(history=history or FakeHistory(records))


async def wait_ops(panel: HistoryPanel) -> None:
    assert panel.ops_worker is not None
    await panel.ops_worker.wait()


# --- Наполнение таблицы --------------------------------------------------------


async def test_table_populates_from_history_newest_first() -> None:
    panel = make_panel([_record(1, "old.txt"), _record(2, "new.txt")])
    async with PanelApp(panel).run_test(size=(100, 30)):
        table = panel.query_one(DataTable)
        assert table.row_count == 2
        assert table.get_row_at(0)[1] == "new.txt"
        assert table.get_row_at(1)[1] == "old.txt"
        assert table.get_row_at(0)[3] == "отправка"


# --- Поиск с debounce ------------------------------------------------------------


async def test_search_filters_table_after_debounce() -> None:
    panel = make_panel(
        [_record(1, "report.pdf"), _record(2, "ОТЧЁТ.pdf"), _record(3, "photo.jpg")]
    )
    async with PanelApp(panel).run_test(size=(100, 30)) as pilot:
        panel.query_one("#history-search", Input).value = "отчёт"
        await pilot.pause(0.5)  # больше debounce (0.3)
        await wait_ops(panel)
        table = panel.query_one(DataTable)
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "ОТЧЁТ.pdf"

        # очистка строки поиска возвращает все записи
        panel.query_one("#history-search", Input).value = ""
        await pilot.pause(0.5)
        await wait_ops(panel)
        assert panel.query_one(DataTable).row_count == 3


# --- Удаление ----------------------------------------------------------------------


async def test_delete_calls_repository_and_removes_row() -> None:
    history = FakeHistory([_record(1, "old.txt"), _record(2, "new.txt")])
    panel = make_panel([], history)
    async with PanelApp(panel).run_test(size=(100, 30)) as pilot:
        table = panel.query_one(DataTable)
        assert table.row_count == 2  # курсор по умолчанию на первой строке (new.txt)
        await pilot.click("#history-delete")
        await wait_ops(panel)

        assert history.deleted == [2]
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "old.txt"


# --- Скопировать код -----------------------------------------------------------------


async def test_copy_puts_selected_code_to_clipboard() -> None:
    panel = make_panel(
        [_record(1, "old.txt", code="old-code"), _record(2, "new.txt", code="new-code")]
    )
    app = PanelApp(panel)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.click("#history-copy")  # курсор на первой строке: new.txt
        assert app.clipboard == "new-code"

        # Button проглатывает повторный клик, пока идёт active-эффект (~0.3 c)
        await pilot.pause(0.4)
        panel.query_one(DataTable).move_cursor(row=1)
        await pilot.click("#history-copy")
        assert app.clipboard == "old-code"


# --- Повторить передачу ---------------------------------------------------------------


async def test_repeat_posts_message_with_selected_record() -> None:
    panel = make_panel([_record(1, "old.txt"), _record(2, "new.txt")])
    app = PanelApp(panel)
    async with app.run_test(size=(100, 30)) as pilot:
        panel.query_one(DataTable).move_cursor(row=1)
        await pilot.click("#history-repeat")
        await pilot.pause()

    [record] = app.repeats
    assert record.filename == "old.txt"


# --- Пустая таблица --------------------------------------------------------------------


async def test_buttons_do_not_crash_on_empty_table() -> None:
    panel = make_panel([])
    async with PanelApp(panel).run_test(size=(100, 30)) as pilot:
        assert panel.query_one(DataTable).row_count == 0
        # паузы между кликами: active-эффект Button глушит быстрые повторы
        await pilot.click("#history-repeat")
        await pilot.pause(0.4)
        await pilot.click("#history-copy")
        await pilot.pause(0.4)
        await pilot.click("#history-delete")
        await pilot.pause()
    # действий не произошло, предупреждения показаны, исключений нет


# --- Форматирование размера ---------------------------------------------------------------


def test_format_size() -> None:
    assert _format_size(None) == "—"
    assert _format_size(116) == "116 B"
    assert _format_size(2048) == "2.0 kB"
    assert _format_size(5 * 1024 * 1024) == "5.0 MB"
    assert _format_size(3 * 1024 * 1024 * 1024) == "3.0 GB"
