"""Панель приёма: код с автодополнением из истории, папка назначения, прогресс.

Автодополнение — только из истории передач (хранилище «избранного» в плане
не реализуется — решение пользователя от 2026-07-13). Опции, не имеющие
полей на этой панели (relay, pass и т.д.), берутся из активного профиля
``ConfigStore``; форма переопределяет только ``out_dir`` и ``auto_accept``.

Зависимости инжектируются через конструктор, как в ``SendPanel``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.suggester import Suggester
from textual.widgets import Button, Checkbox, Input, Label, ProgressBar
from textual.worker import Worker

from pycroc.core.events import (
    AcceptPromptEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    TransferStartEvent,
)
from pycroc.core.exceptions import CrocError
from pycroc.core.options import CrocOptions, normalize_text
from pycroc.core.runner import CrocRunner
from pycroc.core.units import parse_size
from pycroc.storage.config import ConfigStore
from pycroc.storage.history import HistoryRepository, TransferRecord, TransferStatus
from pycroc.ui.widgets.overwrite_modal import OverwriteConflictModal


class HistoryCodeSuggester(Suggester):
    """Инлайн-подсказка кодовой фразы из истории передач (новые — раньше)."""

    def __init__(self, history: HistoryRepository) -> None:
        # история меняется между вызовами — кеш подсказок отключён
        super().__init__(use_cache=False, case_sensitive=True)
        self._history = history

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        for record in await self._history.list(limit=50):
            if record.code.startswith(value) and record.code != value:
                return record.code
        return None


class ReceivePanel(Vertical):
    """Вкладка Receive."""

    BINDINGS: ClassVar[list[BindingType]] = [
        # как в OptionsForm: стрелки двигают фокус по полям (пункт 2 конспекта)
        Binding("down", "focus_next_field", "Следующее поле", show=False),
        Binding("up", "focus_previous_field", "Предыдущее поле", show=False),
    ]

    def action_focus_next_field(self) -> None:
        self.screen.focus_next()

    def action_focus_previous_field(self) -> None:
        self.screen.focus_previous()

    DEFAULT_CSS = """
    ReceivePanel {
        height: 1fr;
        padding: 0 1;
    }
    .buttons {
        height: auto;
        margin-top: 1;
    }
    #receive-cancel-button {
        margin-left: 2;
    }
    #receive-progress {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        *,
        runner: CrocRunner,
        history: HistoryRepository,
        config: ConfigStore,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._runner = runner
        self._history = history
        self._config = config
        #: Активный worker передачи (см. одноимённое поле SendPanel)
        self.transfer_worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Кодовая фраза (подсказка из истории, принять — стрелка вправо):")
        yield Input(
            placeholder="например slow-tomato-almond",
            suggester=HistoryCodeSuggester(self._history),
            id="receive-code",
        )
        yield Label("Папка назначения (--out, пусто — текущая):")
        yield Input(placeholder="путь к папке", id="receive-out")
        yield Checkbox(
            "--yes (авто-подтверждение перезаписи)", value=True, id="receive-auto-accept"
        )
        with Horizontal(classes="buttons"):
            yield Button("Получить", variant="primary", id="receive-button")
            yield Button("Отменить", id="receive-cancel-button", disabled=True)
        yield ProgressBar(total=100, show_eta=False, id="receive-progress")
        yield Label("", id="receive-rate")
        yield Label("", id="receive-status")

    def on_mount(self) -> None:
        options = self._active_profile_options()
        if options.out_dir:
            self.query_one("#receive-out", Input).value = options.out_dir
        self.query_one("#receive-auto-accept", Checkbox).value = options.auto_accept

    def _active_profile_options(self) -> CrocOptions:
        active = self._config.get_active_profile_name()
        return self._config.load_profiles()[active].options

    # --- запуск/отмена передачи ----------------------------------------------

    @on(Button.Pressed, "#receive-button")
    def _receive_pressed(self) -> None:
        self.action_receive()

    @on(Button.Pressed, "#receive-cancel-button")
    def _cancel_pressed(self) -> None:
        self.action_cancel()

    def action_receive(self) -> None:
        code = normalize_text(self.query_one("#receive-code", Input).value)
        if code is None:
            self.notify("Введите кодовую фразу", severity="warning")
            return
        options = replace(
            self._active_profile_options(),
            out_dir=normalize_text(self.query_one("#receive-out", Input).value),
            auto_accept=self.query_one("#receive-auto-accept", Checkbox).value,
        )
        self.transfer_worker = self.run_worker(
            self._run_receive(code, options), exclusive=True, group="receive-transfer"
        )

    def action_cancel(self) -> None:
        self.run_worker(self._runner.cancel(), group="receive-cancel")

    def _set_transferring(self, active: bool) -> None:
        self.query_one("#receive-button", Button).disabled = active
        self.query_one("#receive-cancel-button", Button).disabled = not active

    async def _run_receive(self, code: str, options: CrocOptions) -> None:
        progress = self.query_one("#receive-progress", ProgressBar)
        rate_label = self.query_one("#receive-rate", Label)
        status_label = self.query_one("#receive-status", Label)

        progress.update(progress=0)
        rate_label.update("")
        status_label.update("Подключение к отправителю…")
        self._set_transferring(True)

        started_at = datetime.now()
        # генератор завершился без DoneEvent/ErrorEvent => передача отменена
        final_status: TransferStatus = "cancelled"
        error_message: str | None = None
        filename = ""
        size_bytes: int | None = None
        try:
            async for event in self._runner.receive(code, options):
                if isinstance(event, AcceptPromptEvent):
                    filename = event.filename
                    size_bytes = parse_size(event.size)
                    accept = await self.app.push_screen_wait(
                        OverwriteConflictModal(event.filename, event.size)
                    )
                    await self._runner.respond(accept)
                    status_label.update("Приём…" if accept else "Отклонено")
                elif isinstance(event, TransferStartEvent):
                    filename = event.filename
                    size_bytes = parse_size(event.size)
                    status_label.update(f"Приём {event.filename}…")
                elif isinstance(event, ProgressEvent):
                    filename = event.filename
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
            # Панель могла быть размонтирована посреди передачи — виджетов
            # уже нет, но запись в историю всё равно нужна
            try:
                self._set_transferring(False)
                if final_status == "cancelled":
                    status_label.update("Отменено")
            except NoMatches:
                pass
            await self._history.add(
                TransferRecord(
                    id=None,
                    direction="receive",
                    filename=filename or "?",
                    size_bytes=size_bytes,
                    code=code,
                    status=final_status,
                    started_at=started_at,
                    finished_at=datetime.now(),
                    error_message=error_message,
                )
            )
