"""PyCrocApp: четыре вкладки с общими зависимостями (Task 13).

``PyCrocApp`` владеет единственными экземплярами ``CrocRunner``,
``HistoryRepository`` и ``ConfigStore`` и инжектирует их в панели через
конструкторы (в тестах подставляются fake-реализации, глобальных синглтонов
нет). Зависимости создаются в ``__init__``, а не в ``on_mount``: ``compose()``
выполняется раньше, а панелям они нужны при создании; все три объекта ленивые
и диск при создании не трогают (кроме чтения config.toml).

Сквозная логика уровня приложения:
- отсутствие croc не роняет приложение: предупреждение + блокировка вкладок
  Send/Receive, активной становится Settings;
- успешная проверка бинарника в Settings (``BinaryVerified``) переключает
  раннер на новый путь и разблокирует вкладки;
- «Повторить» из History (``RepeatTransfer``) открывает Send/Receive
  с предзаполненной кодовой фразой.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs
from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, TabbedContent, TabPane

from pycroc.core.exceptions import CrocNotFoundError
from pycroc.core.runner import CrocRunner
from pycroc.storage.config import ConfigStore
from pycroc.storage.history import HistoryRepository
from pycroc.ui.widgets.history_panel import HistoryPanel
from pycroc.ui.widgets.receive_panel import ReceivePanel
from pycroc.ui.widgets.send_panel import SendPanel
from pycroc.ui.widgets.settings_panel import SettingsPanel


class PyCrocApp(App[None]):
    """TUI-клиент croc: вкладки Send / Receive / History / Settings."""

    TITLE = "PyCroc"
    CSS_PATH = "app.tcss"

    def __init__(
        self,
        *,
        config: ConfigStore | None = None,
        history: HistoryRepository | None = None,
        runner: CrocRunner | None = None,
        send_start_path: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.config = config or ConfigStore()
        self.history = history or HistoryRepository(
            Path(platformdirs.user_data_dir("pycroc")) / "history.db"
        )
        binary_path = self.config.get_binary_path()
        # ошибка чтения конфига фиксируется сейчас: панели в on_mount тоже
        # читают конфиг и сбросили бы last_load_error до нашего on_mount
        self._config_error = self.config.last_load_error
        self._binary_path = binary_path
        self.croc_runner = runner or CrocRunner(binary_path)
        self._send_start_path = send_start_path
        #: Версия croc или None, если бинарник не найден
        self.croc_version: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="send"):
            with TabPane("Send", id="send"):
                yield SendPanel(
                    runner=self.croc_runner,
                    history=self.history,
                    config=self.config,
                    start_path=self._send_start_path,
                )
            with TabPane("Receive", id="receive"):
                yield ReceivePanel(
                    runner=self.croc_runner,
                    history=self.history,
                    config=self.config,
                )
            with TabPane("History", id="history"):
                yield HistoryPanel(history=self.history)
            with TabPane("Settings", id="settings"):
                yield SettingsPanel(config=self.config)
        yield Footer()

    async def on_mount(self) -> None:
        if self._config_error is not None:
            self.notify(
                f"Файл конфигурации повреждён и проигнорирован: {self._config_error}",
                severity="warning",
                timeout=10,
            )
        try:
            self.croc_version = await self.croc_runner.check_binary()
        except CrocNotFoundError:
            self.notify(
                f"Бинарник croc не найден ({self._binary_path!r}). "
                "Вкладки Send/Receive заблокированы — укажите путь в Settings.",
                severity="warning",
                timeout=10,
            )
            self._set_transfer_tabs_enabled(False)

    def _set_transfer_tabs_enabled(self, enabled: bool) -> None:
        tabbed = self.query_one(TabbedContent)
        for tab_id in ("send", "receive"):
            if enabled:
                tabbed.enable_tab(tab_id)
            else:
                tabbed.disable_tab(tab_id)
        if not enabled:
            tabbed.active = "settings"

    # --- сквозные сообщения панелей -------------------------------------------

    @on(SettingsPanel.BinaryVerified)
    def _on_binary_verified(self, message: SettingsPanel.BinaryVerified) -> None:
        self.croc_runner.set_binary(message.path)
        self._binary_path = message.path
        self.croc_version = message.version
        self._set_transfer_tabs_enabled(True)
        self.notify(f"croc {message.version} готов к работе")

    @on(HistoryPanel.RepeatTransfer)
    def _on_repeat_transfer(self, message: HistoryPanel.RepeatTransfer) -> None:
        if self.croc_version is None:
            self.notify(
                "croc не найден — сначала укажите путь в Settings", severity="warning"
            )
            return
        record = message.record
        tabbed = self.query_one(TabbedContent)
        if record.direction == "receive":
            tabbed.active = "receive"
            self.query_one(ReceivePanel).query_one("#receive-code", Input).value = record.code
        else:
            tabbed.active = "send"
            # у send предзаполняется --code: та же фраза для повторной отправки
            self.query_one(SendPanel).query_one("#opt-code", Input).value = record.code


def main() -> None:
    """Точка входа CLI-скрипта ``pycroc`` (см. [project.scripts])."""
    PyCrocApp().run()
