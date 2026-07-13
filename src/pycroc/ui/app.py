"""Каркас Textual-приложения PyCroc.

``PyCrocApp`` владеет единственными экземплярами ``CrocRunner``,
``HistoryRepository`` и ``ConfigStore`` и инжектирует их в дочерние виджеты
(dependency injection: в тестах экземпляры подставляются через конструктор,
глобальных синглтонов нет). Вкладки — заглушки, реальные панели появятся
в Task 9–12 и будут подключены в Task 13.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from pycroc.core.exceptions import CrocNotFoundError
from pycroc.core.runner import CrocRunner
from pycroc.storage.config import ConfigStore
from pycroc.storage.history import HistoryRepository


class PyCrocApp(App[None]):
    """TUI-клиент croc: вкладки Send / Receive / History / Settings."""

    TITLE = "PyCroc"
    CSS_PATH = "app.tcss"

    # Создаются в on_mount (или инжектируются в конструктор в тестах)
    config: ConfigStore
    history: HistoryRepository
    croc_runner: CrocRunner

    def __init__(
        self,
        *,
        config: ConfigStore | None = None,
        history: HistoryRepository | None = None,
        runner: CrocRunner | None = None,
    ) -> None:
        super().__init__()
        self._injected_config = config
        self._injected_history = history
        self._injected_runner = runner
        #: Версия croc или None, если бинарник не найден (Send/Receive
        #: блокируются в Task 13 именно по этому признаку)
        self.croc_version: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="send"):
            with TabPane("Send", id="send"):
                yield Static("Отправка файлов — появится в Task 9", classes="placeholder")
            with TabPane("Receive", id="receive"):
                yield Static("Приём по кодовой фразе — появится в Task 10", classes="placeholder")
            with TabPane("History", id="history"):
                yield Static("История передач — появится в Task 11", classes="placeholder")
            with TabPane("Settings", id="settings"):
                yield Static("Настройки и профили — появятся в Task 12", classes="placeholder")
        yield Footer()

    async def on_mount(self) -> None:
        self.config = self._injected_config or ConfigStore()
        self.history = self._injected_history or HistoryRepository(
            Path(platformdirs.user_data_dir("pycroc")) / "history.db"
        )
        binary_path = self.config.get_binary_path()
        if self.config.last_load_error is not None:
            self.notify(
                f"Файл конфигурации повреждён и проигнорирован: {self.config.last_load_error}",
                severity="warning",
                timeout=10,
            )
        self.croc_runner = self._injected_runner or CrocRunner(binary_path)
        try:
            self.croc_version = await self.croc_runner.check_binary()
        except CrocNotFoundError:
            self.notify(
                f"Бинарник croc не найден ({binary_path!r}). "
                "Отправка и приём недоступны — укажите путь в Settings.",
                severity="warning",
                timeout=10,
            )

def main() -> None:
    """Точка входа CLI-скрипта ``pycroc`` (см. [project.scripts])."""
    PyCrocApp().run()
