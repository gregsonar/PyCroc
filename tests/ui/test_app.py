"""Pilot-тесты каркаса приложения (Task 7)."""

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
    return PyCrocApp(config=config, history=HistoryRepository(tmp_path / "history.db"))


def _notification_messages(app: PyCrocApp) -> list[str]:
    return [notification.message for notification in app._notifications]


async def test_app_starts_with_four_tabs(tmp_path: Path) -> None:
    app = _app(tmp_path, MISSING_BINARY)
    async with app.run_test():
        assert [pane.id for pane in app.query(TabPane)] == [
            "send",
            "receive",
            "history",
            "settings",
        ]
        assert app.query_one(TabbedContent).active == "send"


async def test_missing_croc_warns_instead_of_crashing(tmp_path: Path) -> None:
    app = _app(tmp_path, MISSING_BINARY)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.croc_version is None
        assert any("croc" in message for message in _notification_messages(app))
        assert app.is_running


async def test_binary_version_detected_via_fake_croc(tmp_path: Path) -> None:
    app = _app(tmp_path, FAKE_CROC)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.croc_version == "v10.0.0-fake"
        assert not any("не найден" in message for message in _notification_messages(app))


async def test_corrupted_config_warns_and_app_survives(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text("broken [ toml ====", encoding="utf-8")
    app = PyCrocApp(
        config=ConfigStore(tmp_path / "config.toml"),
        history=HistoryRepository(tmp_path / "history.db"),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert any("повреждён" in message for message in _notification_messages(app))
        assert app.is_running
