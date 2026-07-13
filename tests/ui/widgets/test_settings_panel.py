"""Pilot-тесты SettingsPanel (Task 12)."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label, OptionList

from pycroc.core.options import CrocOptions
from pycroc.storage.config import ConfigStore, Profile
from pycroc.ui.widgets.settings_panel import SettingsPanel

FAKE_CROC = str(Path(__file__).parent.parent.parent / "fixtures" / "fake_croc.py")
MISSING_BINARY = "definitely-missing-croc-binary-xyz"


class PanelApp(App[None]):
    def __init__(self, panel: SettingsPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def make_panel(tmp_path: Path) -> tuple[SettingsPanel, ConfigStore]:
    config = ConfigStore(tmp_path / "config.toml")
    return SettingsPanel(config=config), config


def _option_ids(panel: SettingsPanel) -> list[str | None]:
    option_list = panel.query_one("#profile-list", OptionList)
    return [
        option_list.get_option_at_index(i).id for i in range(option_list.option_count)
    ]


def _option_prompts(panel: SettingsPanel) -> list[str]:
    option_list = panel.query_one("#profile-list", OptionList)
    return [
        str(option_list.get_option_at_index(i).prompt)
        for i in range(option_list.option_count)
    ]


def _notifications(app: App[None]) -> list[str]:
    return [n.message for n in app._notifications]


# --- Список профилей и активный маркер ---------------------------------------------


async def test_profiles_listed_with_active_marker(tmp_path: Path) -> None:
    panel, config = make_panel(tmp_path)
    config.save_profile(Profile("work", CrocOptions(relay="w:9009")))
    config.set_active_profile_name("work")
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert _option_ids(panel) == ["default", "work"]
        assert _option_prompts(panel) == ["default", "work  ← активный"]


async def test_create_profile_appears_in_list_and_persists(tmp_path: Path) -> None:
    panel, _ = make_panel(tmp_path)
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        panel.query_one("#new-profile-name", Input).value = "laptop"
        await pilot.click("#profile-create")
        await pilot.pause()
        assert "laptop" in _option_ids(panel)

    # сохранился на диске, виден новому экземпляру ConfigStore
    reloaded = ConfigStore(tmp_path / "config.toml").load_profiles()
    assert reloaded["laptop"] == Profile("laptop", CrocOptions())


async def test_create_duplicate_profile_warns(tmp_path: Path) -> None:
    panel, _ = make_panel(tmp_path)
    app = PanelApp(panel)
    async with app.run_test(size=(120, 40)) as pilot:
        panel.query_one("#new-profile-name", Input).value = "default"
        await pilot.click("#profile-create")
        await pilot.pause()
        assert any("уже существует" in m for m in _notifications(app))
        assert _option_ids(panel) == ["default"]


# --- Удаление ------------------------------------------------------------------------


async def test_delete_default_shows_error_and_does_not_crash(tmp_path: Path) -> None:
    panel, _ = make_panel(tmp_path)
    app = PanelApp(panel)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()  # on_mount выделяет активный (default)
        await pilot.click("#profile-delete")
        await pilot.pause()

        assert any("default" in m for m in _notifications(app))
        assert _option_ids(panel) == ["default"]  # профиль на месте
        assert app.is_running


async def test_delete_regular_profile_removes_it(tmp_path: Path) -> None:
    panel, config = make_panel(tmp_path)
    config.save_profile(Profile("work", CrocOptions()))
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        option_list = panel.query_one("#profile-list", OptionList)
        option_list.highlighted = option_list.get_option_index("work")
        await pilot.pause()
        await pilot.click("#profile-delete")
        await pilot.pause()
        assert _option_ids(panel) == ["default"]
    assert "work" not in ConfigStore(tmp_path / "config.toml").load_profiles()


# --- Активация -----------------------------------------------------------------------


async def test_activate_profile_persists_and_marks(tmp_path: Path) -> None:
    panel, config = make_panel(tmp_path)
    config.save_profile(Profile("work", CrocOptions()))
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        option_list = panel.query_one("#profile-list", OptionList)
        option_list.highlighted = option_list.get_option_index("work")
        await pilot.pause()
        await pilot.click("#profile-activate")
        await pilot.pause()
        assert "work  ← активный" in _option_prompts(panel)
    assert ConfigStore(tmp_path / "config.toml").get_active_profile_name() == "work"


# --- Редактирование опций профиля ------------------------------------------------------


async def test_edit_and_save_profile_options(tmp_path: Path) -> None:
    panel, config = make_panel(tmp_path)
    config.save_profile(Profile("work", CrocOptions(relay="old.relay:9009")))
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        option_list = panel.query_one("#profile-list", OptionList)
        option_list.highlighted = option_list.get_option_index("work")
        await pilot.pause()
        # форма заполнилась значениями профиля
        assert panel.query_one("#opt-relay", Input).value == "old.relay:9009"

        panel.query_one("#opt-relay", Input).value = "new.relay:9009"
        panel.query_one("#opt-exclude", Input).value = "node_modules,.git"
        # кнопка ниже видимой области (форма длинная) — жмём программно
        panel.query_one("#profile-save", Button).press()
        await pilot.pause()

    saved = ConfigStore(tmp_path / "config.toml").load_profiles()["work"].options
    assert saved.relay == "new.relay:9009"
    assert saved.exclude == ("node_modules", ".git")


async def test_highlight_switches_form_content(tmp_path: Path) -> None:
    panel, config = make_panel(tmp_path)
    config.save_profile(Profile("work", CrocOptions(relay="work.relay:9009")))
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        await pilot.pause()  # выделен default (активный)
        assert panel.query_one("#opt-relay", Input).value == ""

        option_list = panel.query_one("#profile-list", OptionList)
        option_list.highlighted = option_list.get_option_index("work")
        await pilot.pause()
        assert panel.query_one("#opt-relay", Input).value == "work.relay:9009"


# --- Проверка бинарника -----------------------------------------------------------------


async def test_check_binary_success_saves_path(tmp_path: Path) -> None:
    panel, config = make_panel(tmp_path)
    async with PanelApp(panel).run_test(size=(120, 40)) as pilot:
        panel.query_one("#binary-path", Input).value = FAKE_CROC
        await pilot.click("#binary-check")
        assert panel.ops_worker is not None
        await panel.ops_worker.wait()
        status = str(panel.query_one("#binary-status", Label).render())
        assert "v10.0.0-fake" in status
    assert ConfigStore(tmp_path / "config.toml").get_binary_path() == FAKE_CROC


async def test_check_binary_missing_shows_error_and_keeps_path(tmp_path: Path) -> None:
    panel, _ = make_panel(tmp_path)
    app = PanelApp(panel)
    async with app.run_test(size=(120, 40)) as pilot:
        panel.query_one("#binary-path", Input).value = MISSING_BINARY
        await pilot.click("#binary-check")
        assert panel.ops_worker is not None
        await panel.ops_worker.wait()
        assert "Ошибка" in str(panel.query_one("#binary-status", Label).render())
    # неудачная проверка не сохраняет путь
    assert ConfigStore(tmp_path / "config.toml").get_binary_path() == "croc"
