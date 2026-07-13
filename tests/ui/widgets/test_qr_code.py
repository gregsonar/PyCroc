"""Тесты QrCodeWidget (Task 8)."""

from __future__ import annotations

from textual.app import App, ComposeResult

from pycroc.ui.widgets.qr_code import QrCodeWidget, render_qr_ascii

# qrcode.print_ascii печатает "пустоту" неразрывным пробелом \xa0
QR_BLOCK_CHARS = set(" \xa0▀▄█")


class QrApp(App[None]):
    def compose(self) -> ComposeResult:
        yield QrCodeWidget()


# --- Чистая функция рендера --------------------------------------------------


def test_render_qr_ascii_is_deterministic_and_nonempty() -> None:
    first = render_qr_ascii("slow-tomato-almond")
    second = render_qr_ascii("slow-tomato-almond")
    assert first == second
    assert first.strip() != ""
    # содержимое состоит из блочных символов QR (плюс переводы строк)
    assert set(first) - {"\n"} <= QR_BLOCK_CHARS


def test_render_qr_ascii_differs_for_different_codes() -> None:
    assert render_qr_ascii("slow-tomato-almond") != render_qr_ascii("fast-banana-apple")


# --- Реактивность виджета -----------------------------------------------------


async def test_setting_code_changes_rendered_text() -> None:
    app = QrApp()
    async with app.run_test() as pilot:
        widget = app.query_one(QrCodeWidget)
        assert str(widget.render()) == ""

        widget.code = "slow-tomato-almond"
        await pilot.pause()
        rendered = str(widget.render())
        assert rendered == render_qr_ascii("slow-tomato-almond")


async def test_changing_code_rerenders_and_none_clears() -> None:
    app = QrApp()
    async with app.run_test() as pilot:
        widget = app.query_one(QrCodeWidget)
        widget.code = "slow-tomato-almond"
        await pilot.pause()
        first = str(widget.render())

        widget.code = "fast-banana-apple"
        await pilot.pause()
        second = str(widget.render())
        assert second != first

        widget.code = None
        await pilot.pause()
        assert str(widget.render()) == ""
