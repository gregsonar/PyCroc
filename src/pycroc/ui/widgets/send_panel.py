"""Панель отправки: выбор файлов, форма опций, прогресс, QR-код.

Зависимости (``CrocRunner``/``HistoryRepository``/``ConfigStore``)
инжектируются через конструктор — в тестах подставляются fake-реализации
без патчинга модулей (см. Design decisions плана).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.timer import Timer
from textual.widgets import Button, Label, ProgressBar
from textual.worker import Worker

from pycroc.core.events import (
    CodeEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    TransferStartEvent,
)
from pycroc.core.exceptions import CrocError
from pycroc.core.options import CrocOptions
from pycroc.core.runner import CrocRunner
from pycroc.core.units import format_size, parse_size
from pycroc.storage.config import ConfigStore
from pycroc.storage.history import HistoryRepository, TransferRecord, TransferStatus
from pycroc.ui.widgets.file_picker import MultiSelectDirectoryTree
from pycroc.ui.widgets.options_form import OptionsForm
from pycroc.ui.widgets.qr_code import QrCodeWidget

_SIZE_DEBOUNCE_SECONDS = 0.15


def selected_total_size(paths: list[str]) -> int:
    """Суммарный размер путей в байтах (файлы + рекурсивный обход папок).

    Недоступные/исчезнувшие файлы молча пропускаются — размер это оценка
    для превью, а не источник истины. Блокирующий I/O: вызывать через
    ``asyncio.to_thread``, чтобы не морозить UI на больших деревьях.
    """
    total = 0
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for root, _dirs, files in os.walk(path):
                for name in files:
                    with contextlib.suppress(OSError):
                        total += os.path.getsize(os.path.join(root, name))
        else:
            with contextlib.suppress(OSError):
                total += path.stat().st_size
    return total


class SendPanel(Vertical):
    """Вкладка Send."""

    DEFAULT_CSS = """
    SendPanel {
        height: 1fr;
    }
    #send-layout {
        height: 1fr;
    }
    #send-left {
        width: 50%;
        padding-right: 1;
    }
    #file-picker {
        height: 1fr;
    }
    #send-form {
        width: 1fr;
    }
    .form-title {
        margin-top: 1;
        text-style: bold;
    }
    .buttons {
        height: auto;
        margin-top: 1;
    }
    #cancel-button {
        margin-left: 2;
    }
    #clear-selection-button {
        margin-left: 2;
    }
    #send-progress {
        margin-top: 1;
    }
    #send-code-row {
        height: auto;
    }
    #send-code-text {
        text-style: bold;
    }
    #copy-code-button {
        margin-left: 2;
    }
    """

    def __init__(
        self,
        *,
        runner: CrocRunner,
        history: HistoryRepository,
        config: ConfigStore,
        start_path: str | Path | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._runner = runner
        self._history = history
        self._config = config
        self._start_path = Path(start_path) if start_path is not None else Path.home()
        #: Активный worker передачи; тесты и отмена ждут именно его, а не все
        #: worker-ы приложения (у DirectoryTree есть вечный загрузчик)
        self.transfer_worker: Worker[None] | None = None
        self._current_code: str | None = None
        self._size_timer: Timer | None = None
        self._pending_size_paths: list[str] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="send-layout"):
            with Vertical(id="send-left"):
                yield Label("Файлы и папки (space — выбрать):")
                yield MultiSelectDirectoryTree(self._start_path, id="file-picker")
                yield Label("Выбрано: ничего", id="send-selection-size")
                with Horizontal(classes="buttons"):
                    yield Button("Отправить", variant="primary", id="send-button")
                    yield Button("Отменить", id="cancel-button", disabled=True)
                    yield Button("Снять выделение", id="clear-selection-button")
                yield ProgressBar(total=100, show_eta=False, id="send-progress")
                yield Label("", id="send-rate")
                yield Label("", id="send-status")
            with VerticalScroll(id="send-form"):
                # Код и QR — ПЕРВЫМИ в прокручиваемой колонке: внизу под
                # формой они обновлялись за пределами видимой области, и без
                # заданного --code получатель не мог узнать код вовсе
                # (пункт 5 конспекта, критичный)
                yield Label("Код передачи:", classes="form-title")
                with Horizontal(id="send-code-row"):
                    yield Label("", id="send-code-text")
                    yield Button("Копировать", id="copy-code-button", disabled=True)
                yield QrCodeWidget(id="send-qr")
                yield Label("Опции (пустое поле — по умолчанию):", classes="form-title")
                yield OptionsForm(id="send-options")

    def on_mount(self) -> None:
        active = self._config.get_active_profile_name()
        self._apply_options(self._config.load_profiles()[active].options)

    # --- форма <-> CrocOptions (делегируется OptionsForm) ---------------------

    def _apply_options(self, options: CrocOptions) -> None:
        self.query_one(OptionsForm).apply_options(options)

    def _options_from_form(self) -> CrocOptions:
        return self.query_one(OptionsForm).read_options()

    # --- запуск/отмена передачи ----------------------------------------------

    @on(Button.Pressed, "#send-button")
    def _send_pressed(self) -> None:
        self.action_send()

    @on(Button.Pressed, "#cancel-button")
    def _cancel_pressed(self) -> None:
        self.action_cancel()

    @on(Button.Pressed, "#copy-code-button")
    def _copy_code_pressed(self) -> None:
        if self._current_code:
            self.app.copy_to_clipboard(self._current_code)
            self.notify("Код скопирован в буфер обмена")

    @on(Button.Pressed, "#clear-selection-button")
    def _clear_selection_pressed(self) -> None:
        # сброс всех отметок разом — не искать каждую в большом дереве
        tree = self.query_one(MultiSelectDirectoryTree)
        if not tree.selected_paths():
            self.notify("Нет отмеченных файлов", severity="warning")
            return
        tree.clear_selection()

    @on(MultiSelectDirectoryTree.SelectionChanged)
    def _selection_changed(self, event: MultiSelectDirectoryTree.SelectionChanged) -> None:
        # debounce: быстрые переключения коалесцируются в один пересчёт
        # (как поиск в History) — не гоняем обход дерева на каждый toggle
        self._pending_size_paths = event.paths
        if self._size_timer is not None:
            self._size_timer.stop()
        self._size_timer = self.set_timer(_SIZE_DEBOUNCE_SECONDS, self._recompute_size)

    def _recompute_size(self) -> None:
        # обход папок может быть небыстрым — считаем в потоке, не морозя UI
        self.run_worker(
            self._update_selection_size(self._pending_size_paths),
            exclusive=True,
            group="send-selection-size",
        )

    async def _update_selection_size(self, paths: list[str]) -> None:
        label = self.query_one("#send-selection-size", Label)
        if not paths:
            label.update("Выбрано: ничего")
            return
        total = await asyncio.to_thread(selected_total_size, paths)
        noun = "объект" if len(paths) == 1 else "объектов"
        label.update(f"Выбрано: {len(paths)} {noun}, {format_size(total)}")

    def action_send(self) -> None:
        paths = self.query_one(MultiSelectDirectoryTree).selected_paths()
        if not paths:
            self.notify("Не отмечен ни один файл или папка", severity="warning")
            return
        options = self._options_from_form()
        self.transfer_worker = self.run_worker(
            self._run_send(paths, options), exclusive=True, group="send-transfer"
        )

    def action_cancel(self) -> None:
        self.run_worker(self._runner.cancel(), group="send-cancel")

    def _set_transferring(self, active: bool) -> None:
        self.query_one("#send-button", Button).disabled = active
        self.query_one("#cancel-button", Button).disabled = not active

    async def _run_send(self, paths: list[str], options: CrocOptions) -> None:
        progress = self.query_one("#send-progress", ProgressBar)
        rate_label = self.query_one("#send-rate", Label)
        status_label = self.query_one("#send-status", Label)
        code_label = self.query_one("#send-code-text", Label)
        qr = self.query_one(QrCodeWidget)

        progress.update(progress=0)
        rate_label.update("")
        code_label.update("")
        qr.code = None
        self._current_code = None
        self.query_one("#copy-code-button", Button).disabled = True
        status_label.update("Запуск croc…")
        self._set_transferring(True)

        started_at = datetime.now()
        # генератор завершился без DoneEvent/ErrorEvent => передача отменена
        final_status: TransferStatus = "cancelled"
        error_message: str | None = None
        code_value = options.code or ""
        size_bytes: int | None = None
        try:
            async for event in self._runner.send(paths, options):
                if isinstance(event, CodeEvent) and event.code != self._current_code:
                    # croc v11 печатает код дважды (строка-инструкция и URL) —
                    # реагируем только на первое появление, чтобы не дублировать
                    # уведомление и обновление QR
                    code_value = event.code
                    self._current_code = event.code
                    qr.code = event.code
                    code_label.update(event.code)
                    self.query_one("#copy-code-button", Button).disabled = False
                    # код дублируется уведомлением: критично, чтобы получатель
                    # мог его узнать сразу (пункт 5 конспекта)
                    self.notify(f"Код передачи: {event.code}", timeout=10)
                    status_label.update("Ожидание получателя…")
                elif isinstance(event, TransferStartEvent):
                    size_bytes = parse_size(event.size)
                    status_label.update(f"Отправка {event.filename}…")
                elif isinstance(event, ProgressEvent):
                    progress.update(progress=event.percent)
                    rate_label.update(event.rate)
                elif isinstance(event, DoneEvent):
                    final_status = "done"
                    progress.update(progress=100)
                    status_label.update("Готово")
                elif isinstance(event, ErrorEvent):
                    final_status = "error"
                    error_message = event.message
                    status_label.update("Ошибка")
                    self.notify(event.message, severity="error")
        except CrocError as exc:
            final_status = "error"
            error_message = str(exc)
            status_label.update("Ошибка")
            self.notify(str(exc), severity="error")
        finally:
            # Панель могла быть размонтирована посреди передачи (закрытие
            # приложения) — виджетов уже нет, но историю записать всё равно надо
            try:
                self._set_transferring(False)
                if final_status == "cancelled":
                    status_label.update("Отменено")
            except NoMatches:
                pass
            filename = Path(paths[0]).name
            if len(paths) > 1:
                filename += f" (+{len(paths) - 1})"
            await self._history.add(
                TransferRecord(
                    id=None,
                    direction="send",
                    filename=filename,
                    size_bytes=size_bytes,
                    code=code_value,
                    status=final_status,
                    started_at=started_at,
                    finished_at=datetime.now(),
                    error_message=error_message,
                )
            )
