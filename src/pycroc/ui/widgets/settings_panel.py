"""Панель настроек: профили опций, активный профиль, путь к бинарнику croc.

Слева — список профилей (создание/активация/удаление), справа —
``OptionsForm`` выделенного профиля с кнопкой сохранения. Сверху — путь к
бинарнику: кнопка «Проверить» запускает ``check_binary()`` и при успехе
сохраняет путь в конфиг (при ошибке путь не сохраняется).

``runner_factory`` инжектируется для тестов: проверка бинарника должна
использовать путь из поля, а не раннер приложения с прежним путём.
"""

from __future__ import annotations

from collections.abc import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, OptionList
from textual.widgets.option_list import Option
from textual.worker import Worker

from pycroc.core.exceptions import CrocNotFoundError
from pycroc.core.options import CrocOptions, normalize_text
from pycroc.core.runner import CrocRunner
from pycroc.storage.config import DEFAULT_PROFILE_NAME, ConfigStore, Profile
from pycroc.ui.widgets.options_form import OptionsForm


class SettingsPanel(Vertical):
    """Вкладка Settings."""

    DEFAULT_CSS = """
    SettingsPanel {
        height: 1fr;
        padding: 0 1;
    }
    .binary-row {
        height: auto;
    }
    #binary-path {
        width: 1fr;
    }
    #settings-layout {
        height: 1fr;
        margin-top: 1;
    }
    #settings-left {
        width: 40%;
        padding-right: 1;
    }
    #profile-list {
        height: 1fr;
    }
    #settings-right {
        width: 1fr;
    }
    .buttons {
        height: auto;
        margin-top: 1;
    }
    .form-title {
        text-style: bold;
    }
    """

    def __init__(
        self,
        *,
        config: ConfigStore,
        runner_factory: Callable[[str], CrocRunner] = CrocRunner,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._config = config
        self._runner_factory = runner_factory
        self._selected: str | None = None
        #: Последний worker проверки бинарника — тесты ждут его
        self.ops_worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Путь к бинарнику croc:", classes="form-title")
        with Horizontal(classes="binary-row"):
            yield Input(placeholder="croc или полный путь", id="binary-path")
            yield Button("Проверить", id="binary-check")
        yield Label("", id="binary-status")
        with Horizontal(id="settings-layout"):
            with Vertical(id="settings-left"):
                yield Label("Профили:", classes="form-title")
                yield OptionList(id="profile-list")
                yield Input(placeholder="имя нового профиля", id="new-profile-name")
                with Horizontal(classes="buttons"):
                    yield Button("Создать", id="profile-create")
                    yield Button("Активировать", id="profile-activate")
                    yield Button("Удалить", variant="error", id="profile-delete")
            with VerticalScroll(id="settings-right"):
                yield Label("Опции выбранного профиля:", classes="form-title")
                yield OptionsForm(id="profile-options")
                with Horizontal(classes="buttons"):
                    yield Button("Сохранить профиль", variant="primary", id="profile-save")

    def on_mount(self) -> None:
        self.query_one("#binary-path", Input).value = self._config.get_binary_path()
        self._reload_profiles(select=self._config.get_active_profile_name())

    def _reload_profiles(self, select: str) -> None:
        profiles = self._config.load_profiles()
        active = self._config.get_active_profile_name()
        option_list = self.query_one("#profile-list", OptionList)
        option_list.clear_options()
        for name in sorted(profiles):
            label = f"{name}  ← активный" if name == active else name
            option_list.add_option(Option(label, id=name))
        target = select if select in profiles else DEFAULT_PROFILE_NAME
        option_list.highlighted = option_list.get_option_index(target)

    # --- выбор профиля -----------------------------------------------------------

    @on(OptionList.OptionHighlighted, "#profile-list")
    def _profile_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        name = event.option_id
        if name is None:
            return
        self._selected = name
        profiles = self._config.load_profiles()
        if name in profiles:
            self.query_one(OptionsForm).apply_options(profiles[name].options)

    # --- CRUD профилей --------------------------------------------------------------

    @on(Button.Pressed, "#profile-create")
    def _create_pressed(self) -> None:
        name_input = self.query_one("#new-profile-name", Input)
        name = normalize_text(name_input.value)
        if name is None:
            self.notify("Введите имя нового профиля", severity="warning")
            return
        if name in self._config.load_profiles():
            self.notify(f"Профиль {name!r} уже существует", severity="warning")
            return
        self._config.save_profile(Profile(name, CrocOptions()))
        name_input.value = ""
        self._reload_profiles(select=name)
        self.notify(f"Профиль {name!r} создан")

    @on(Button.Pressed, "#profile-save")
    def _save_pressed(self) -> None:
        if self._selected is None:
            self.notify("Нет выбранного профиля", severity="warning")
            return
        options = self.query_one(OptionsForm).read_options()
        self._config.save_profile(Profile(self._selected, options))
        self.notify(f"Профиль {self._selected!r} сохранён")

    @on(Button.Pressed, "#profile-activate")
    def _activate_pressed(self) -> None:
        if self._selected is None:
            self.notify("Нет выбранного профиля", severity="warning")
            return
        self._config.set_active_profile_name(self._selected)
        self._reload_profiles(select=self._selected)
        self.notify(f"Активный профиль: {self._selected!r}")

    @on(Button.Pressed, "#profile-delete")
    def _delete_pressed(self) -> None:
        if self._selected is None:
            self.notify("Нет выбранного профиля", severity="warning")
            return
        try:
            self._config.delete_profile(self._selected)
        except ValueError as exc:
            # защита default: показать ошибку, не падать
            self.notify(str(exc), severity="error")
            return
        self.notify(f"Профиль {self._selected!r} удалён")
        self._reload_profiles(select=DEFAULT_PROFILE_NAME)

    # --- проверка бинарника ------------------------------------------------------------

    @on(Button.Pressed, "#binary-check")
    def _check_pressed(self) -> None:
        path = normalize_text(self.query_one("#binary-path", Input).value) or "croc"
        self.ops_worker = self.run_worker(
            self._check_binary(path), exclusive=True, group="settings-check"
        )

    async def _check_binary(self, path: str) -> None:
        status = self.query_one("#binary-status", Label)
        status.update("Проверка…")
        try:
            version = await self._runner_factory(path).check_binary()
        except CrocNotFoundError as exc:
            status.update(f"Ошибка: {exc}")
            self.notify(str(exc), severity="error")
            return
        self._config.set_binary_path(path)
        status.update(f"croc {version} — путь сохранён")
