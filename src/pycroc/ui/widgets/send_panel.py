"""Панель отправки: выбор файлов, форма опций, прогресс, QR-код.

Зависимости (``CrocRunner``/``HistoryRepository``/``ConfigStore``)
инжектируются через конструктор — в тестах подставляются fake-реализации
без патчинга модулей (см. Design decisions плана).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Checkbox, Input, Label, ProgressBar
from textual.worker import Worker

from pycroc.core.events import (
    CodeEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    TransferStartEvent,
)
from pycroc.core.exceptions import CrocError
from pycroc.core.options import CrocOptions, normalize_text
from pycroc.core.runner import CrocRunner
from pycroc.storage.config import ConfigStore
from pycroc.storage.history import HistoryRepository, TransferRecord, TransferStatus
from pycroc.ui.widgets.file_picker import MultiSelectDirectoryTree
from pycroc.ui.widgets.qr_code import QrCodeWidget


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
    #send-progress {
        margin-top: 1;
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

    def compose(self) -> ComposeResult:
        with Horizontal(id="send-layout"):
            with Vertical(id="send-left"):
                yield Label("Файлы и папки (space — отметить):")
                yield MultiSelectDirectoryTree(self._start_path, id="file-picker")
                with Horizontal(classes="buttons"):
                    yield Button("Отправить", variant="primary", id="send-button")
                    yield Button("Отменить", id="cancel-button", disabled=True)
                yield ProgressBar(total=100, show_eta=False, id="send-progress")
                yield Label("", id="send-rate")
                yield Label("", id="send-status")
            with VerticalScroll(id="send-form"):
                yield Label("Опции (пустое поле — по умолчанию):", classes="form-title")
                yield Input(placeholder="--code: своя кодовая фраза", id="opt-code")
                yield Input(placeholder="--pass: пароль relay или файл с ним", id="opt-pass")
                yield Input(placeholder="--relay host:port", id="opt-relay")
                yield Input(placeholder="--relay6 [ipv6]:port", id="opt-relay6")
                yield Input(placeholder="--socks5 host:port", id="opt-socks5")
                yield Input(placeholder="--connect http-proxy", id="opt-connect")
                yield Input(placeholder="--throttleUpload, напр. 500k", id="opt-throttle")
                yield Input(placeholder="--curve: P-256 | P-348 | P-521 | SIEC", id="opt-curve")
                yield Input(placeholder="--hash: xxhash | imohash", id="opt-hash")
                yield Input(placeholder="--exclude: шаблоны через запятую", id="opt-exclude")
                yield Input(placeholder="--transfers: число потоков", id="opt-transfers")
                yield Checkbox("--no-compress", id="opt-no-compress")
                yield Checkbox("--ask", id="opt-ask")
                yield Checkbox("--yes (авто-подтверждение)", value=True, id="opt-auto-accept")
                yield Label("Код передачи:", classes="form-title")
                yield Label("", id="send-code-text")
                yield QrCodeWidget(id="send-qr")

    def on_mount(self) -> None:
        active = self._config.get_active_profile_name()
        self._apply_options(self._config.load_profiles()[active].options)

    # --- форма <-> CrocOptions ---------------------------------------------

    def _apply_options(self, options: CrocOptions) -> None:
        def set_text(input_id: str, value: str | None) -> None:
            self.query_one(f"#{input_id}", Input).value = value or ""

        set_text("opt-code", options.code)
        set_text("opt-pass", options.pass_)
        set_text("opt-relay", options.relay)
        set_text("opt-relay6", options.relay6)
        set_text("opt-socks5", options.socks5)
        set_text("opt-connect", options.connect)
        set_text("opt-throttle", options.throttle_upload)
        set_text("opt-curve", options.curve)
        set_text("opt-hash", options.hash_algo)
        set_text("opt-exclude", ",".join(options.exclude) if options.exclude else None)
        set_text(
            "opt-transfers",
            str(options.transfers) if options.transfers is not None else None,
        )
        self.query_one("#opt-no-compress", Checkbox).value = options.no_compress
        self.query_one("#opt-ask", Checkbox).value = options.ask
        self.query_one("#opt-auto-accept", Checkbox).value = options.auto_accept

    def _options_from_form(self) -> CrocOptions:
        def text(input_id: str) -> str | None:
            return normalize_text(self.query_one(f"#{input_id}", Input).value)

        exclude_text = text("opt-exclude")
        exclude = (
            tuple(part for part in (p.strip() for p in exclude_text.split(",")) if part)
            if exclude_text
            else ()
        )
        transfers_text = text("opt-transfers")
        transfers = int(transfers_text) if transfers_text and transfers_text.isdigit() else None
        return CrocOptions(
            code=text("opt-code"),
            pass_=text("opt-pass"),
            relay=text("opt-relay"),
            relay6=text("opt-relay6"),
            socks5=text("opt-socks5"),
            connect=text("opt-connect"),
            throttle_upload=text("opt-throttle"),
            curve=text("opt-curve"),
            hash_algo=text("opt-hash"),
            no_compress=self.query_one("#opt-no-compress", Checkbox).value,
            ask=self.query_one("#opt-ask", Checkbox).value,
            auto_accept=self.query_one("#opt-auto-accept", Checkbox).value,
            exclude=exclude,
            transfers=transfers,
        )

    # --- запуск/отмена передачи ----------------------------------------------

    @on(Button.Pressed, "#send-button")
    def _send_pressed(self) -> None:
        self.action_send()

    @on(Button.Pressed, "#cancel-button")
    def _cancel_pressed(self) -> None:
        self.action_cancel()

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
        status_label.update("Запуск croc…")
        self._set_transferring(True)

        started_at = datetime.now()
        # генератор завершился без DoneEvent/ErrorEvent => передача отменена
        final_status: TransferStatus = "cancelled"
        error_message: str | None = None
        code_value = options.code or ""
        try:
            async for event in self._runner.send(paths, options):
                if isinstance(event, CodeEvent):
                    code_value = event.code
                    qr.code = event.code
                    code_label.update(event.code)
                    status_label.update("Ожидание получателя…")
                elif isinstance(event, TransferStartEvent):
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
                    size_bytes=None,
                    code=code_value,
                    status=final_status,
                    started_at=started_at,
                    finished_at=datetime.now(),
                    error_message=error_message,
                )
            )
