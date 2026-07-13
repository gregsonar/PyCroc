"""Панель истории передач: таблица, поиск с debounce, действия по строке.

«Повторить передачу» отправляет message ``RepeatTransfer`` — переключение
вкладок и предзаполнение полей сделает ``PyCrocApp`` в Task 13, сама панель
про другие вкладки не знает. Кодовая фраза в таблице не отображается
(только действие «скопировать код») — см. пункт 3 конспекта ручного
тестирования о защите кодов от утечки.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Button, DataTable, Input
from textual.worker import Worker

from pycroc.core.options import normalize_text
from pycroc.storage.history import HistoryRepository, TransferRecord

_SEARCH_DEBOUNCE_SECONDS = 0.3

_DIRECTION_LABELS = {"send": "отправка", "receive": "приём"}


def _format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    size = float(size_bytes)
    for unit in ("B", "kB", "MB"):
        if size < 1024:
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class HistoryPanel(Vertical):
    """Вкладка History."""

    DEFAULT_CSS = """
    HistoryPanel {
        height: 1fr;
        padding: 0 1;
    }
    #history-table {
        height: 1fr;
        margin-top: 1;
    }
    .buttons {
        height: auto;
        margin-top: 1;
    }
    #history-copy, #history-delete {
        margin-left: 2;
    }
    """

    class RepeatTransfer(Message):
        """Пользователь просит повторить передачу из выбранной записи."""

        def __init__(self, record: TransferRecord) -> None:
            super().__init__()
            self.record = record

    def __init__(self, *, history: HistoryRepository, id: str | None = None) -> None:
        super().__init__(id=id)
        self._history = history
        self._records: dict[str, TransferRecord] = {}
        self._search_timer: Timer | None = None
        #: Последний worker операций (поиск/удаление) — тесты ждут его
        self.ops_worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Поиск по имени файла", id="history-search")
        yield DataTable(id="history-table")
        with Horizontal(classes="buttons"):
            yield Button("Повторить", variant="primary", id="history-repeat")
            yield Button("Скопировать код", id="history-copy")
            yield Button("Удалить", id="history-delete")

    async def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Дата", "Файл", "Размер", "Направление", "Статус")
        await self.refresh_table()

    async def refresh_table(self) -> None:
        """Перечитывает таблицу из репозитория с учётом строки поиска."""
        query = normalize_text(self.query_one("#history-search", Input).value)
        table = self.query_one(DataTable)
        records = await self._history.list(query=query)
        table.clear()
        self._records.clear()
        for record in records:
            key = str(record.id)
            table.add_row(
                record.started_at.strftime("%Y-%m-%d %H:%M"),
                record.filename,
                _format_size(record.size_bytes),
                _DIRECTION_LABELS.get(record.direction, record.direction),
                record.status,
                key=key,
            )
            self._records[key] = record

    def _selected_record(self) -> TransferRecord | None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        row_value = cell_key.row_key.value
        return self._records.get(row_value) if row_value is not None else None

    # --- поиск с debounce -----------------------------------------------------

    @on(Input.Changed, "#history-search")
    def _search_changed(self) -> None:
        if self._search_timer is not None:
            self._search_timer.stop()
        self._search_timer = self.set_timer(_SEARCH_DEBOUNCE_SECONDS, self._run_search)

    def _run_search(self) -> None:
        self.ops_worker = self.run_worker(
            self.refresh_table(), exclusive=True, group="history-ops"
        )

    # --- действия по строке ------------------------------------------------------

    @on(Button.Pressed, "#history-repeat")
    def _repeat_pressed(self) -> None:
        record = self._selected_record()
        if record is None:
            self.notify("Нет выбранной записи", severity="warning")
            return
        self.post_message(self.RepeatTransfer(record))

    @on(Button.Pressed, "#history-copy")
    def _copy_pressed(self) -> None:
        record = self._selected_record()
        if record is None:
            self.notify("Нет выбранной записи", severity="warning")
            return
        self.app.copy_to_clipboard(record.code)
        self.notify("Код скопирован в буфер обмена")

    @on(Button.Pressed, "#history-delete")
    def _delete_pressed(self) -> None:
        record = self._selected_record()
        if record is None or record.id is None:
            self.notify("Нет выбранной записи", severity="warning")
            return
        self.ops_worker = self.run_worker(
            self._delete_and_refresh(record.id), exclusive=True, group="history-ops"
        )

    async def _delete_and_refresh(self, record_id: int) -> None:
        await self._history.delete(record_id)
        await self.refresh_table()
