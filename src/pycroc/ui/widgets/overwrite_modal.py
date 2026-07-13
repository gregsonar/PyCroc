"""Модальное окно подтверждения перезаписи файла при приёме.

Показывается на ``AcceptPromptEvent`` при ``auto_accept=False``; результат
(``bool``) вызывающая сторона передаёт в ``CrocRunner.respond()``, который
пишет ``y\\n``/``n\\n`` в stdin процесса croc.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class OverwriteConflictModal(ModalScreen[bool]):
    """``Accept 'file.txt' (116 B)? (y/n)`` в виде модалки."""

    DEFAULT_CSS = """
    OverwriteConflictModal {
        align: center middle;
    }
    #modal-dialog {
        width: 64;
        height: auto;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #modal-buttons {
        height: auto;
        margin-top: 1;
        align-horizontal: center;
    }
    #modal-no {
        margin-left: 2;
    }
    """

    def __init__(self, filename: str, size: str) -> None:
        super().__init__()
        # ВАЖНО: не называть поля _size/_filename без префикса — _size уже
        # занят внутренним атрибутом Widget (Size компоновщика)
        self._target_filename = filename
        self._target_size = size

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Label(f"Принять '{self._target_filename}' ({self._target_size})?")
            yield Label("Существующий файл может быть перезаписан.")
            with Horizontal(id="modal-buttons"):
                yield Button("Да", variant="primary", id="modal-yes")
                yield Button("Нет", id="modal-no")

    @on(Button.Pressed, "#modal-yes")
    def _accept(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#modal-no")
    def _reject(self) -> None:
        self.dismiss(False)
