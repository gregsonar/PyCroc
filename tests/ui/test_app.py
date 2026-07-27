"""Pilot-тесты каркаса приложения (Task 7; обновлены в Task 13:
отсутствие croc теперь блокирует вкладки Send/Receive)."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import TabbedContent, TabPane

from pycroc.storage.config import ConfigStore
from pycroc.storage.history import HistoryRepository
from pycroc.ui.app import PyCrocApp

FAKE_CROC = str(Path(__file__).parent.parent / "fixtures" / "fake_croc.py")
MISSING_BINARY = "definitely-missing-croc-binary-xyz"


def _app(tmp_path: Path, binary: str) -> PyCrocApp:
    config = ConfigStore(tmp_path / "config.toml")
    config.set_binary_path(binary)
    return _app_with_config(tmp_path, config)


def _app_with_config(tmp_path: Path, config: ConfigStore) -> PyCrocApp:
    return PyCrocApp(
        config=config,
        history=HistoryRepository(tmp_path / "history.db"),
        send_start_path=tmp_path,
    )


def _notification_messages(app: PyCrocApp) -> list[str]:
    return [notification.message for notification in app._notifications]


async def test_app_starts_with_four_tabs(tmp_path: Path) -> None:
    app = _app(tmp_path, FAKE_CROC)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert [pane.id for pane in app.query(TabPane)] == [
            "send",
            "receive",
            "history",
            "settings",
        ]
        assert app.query_one(TabbedContent).active == "send"


async def test_missing_croc_warns_and_disables_transfer_tabs(tmp_path: Path) -> None:
    app = _app(tmp_path, MISSING_BINARY)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.croc_version is None
        assert any("croc" in message for message in _notification_messages(app))
        tabbed = app.query_one(TabbedContent)
        assert tabbed.get_tab("send").disabled is True
        assert tabbed.get_tab("receive").disabled is True
        assert tabbed.active == "settings"
        assert app.is_running


async def test_binary_version_detected_via_fake_croc(tmp_path: Path) -> None:
    app = _app(tmp_path, FAKE_CROC)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.croc_version == "v10.0.0-fake"
        assert not any("не найден" in message for message in _notification_messages(app))
        tabbed = app.query_one(TabbedContent)
        assert tabbed.get_tab("send").disabled is False
        assert tabbed.get_tab("receive").disabled is False


async def test_corrupted_config_warns_and_app_survives(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text("broken [ toml ====", encoding="utf-8")
    app = PyCrocApp(
        config=ConfigStore(tmp_path / "config.toml"),
        history=HistoryRepository(tmp_path / "history.db"),
        send_start_path=tmp_path,
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert any("повреждён" in message for message in _notification_messages(app))
        assert app.is_running


async def test_saved_theme_is_restored_on_start(tmp_path: Path) -> None:
    config = ConfigStore(tmp_path / "config.toml")
    config.set_theme("gruvbox")
    app = _app_with_config(tmp_path, config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.theme == "gruvbox"


async def test_changing_theme_persists_to_config(tmp_path: Path) -> None:
    config = ConfigStore(tmp_path / "config.toml")
    app = _app_with_config(tmp_path, config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.theme = "nord"
        await pilot.pause()
    # новый экземпляр ConfigStore видит записанную тему
    assert ConfigStore(tmp_path / "config.toml").get_theme() == "nord"


async def test_unknown_saved_theme_is_ignored_without_crash(tmp_path: Path) -> None:
    config = ConfigStore(tmp_path / "config.toml")
    config.set_theme("theme-from-the-future-that-does-not-exist")
    app = _app_with_config(tmp_path, config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # неизвестная тема проигнорирована, приложение живо, тема — дефолтная
        assert app.is_running
        assert app.theme in app.available_themes
