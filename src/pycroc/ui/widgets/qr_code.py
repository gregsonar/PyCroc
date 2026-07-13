"""Виджет ASCII-QR-кода кодовой фразы.

QR генерируется библиотекой ``qrcode`` из уже полученной кодовой фразы
(``CodeEvent``), а не захватывается из вывода ``croc --qr`` — ASCII-арт croc
рассчитан на живой TTY и плохо переносит subprocess-захват (см. Design
decisions плана). Кодируется сама фраза как текст.
"""

from __future__ import annotations

import io

import qrcode
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


def render_qr_ascii(code: str) -> str:
    """Детерминированный ASCII-рендер QR для строки ``code``."""
    qr = qrcode.QRCode(border=1)
    qr.add_data(code)
    qr.make(fit=True)
    buffer = io.StringIO()
    qr.print_ascii(out=buffer, invert=True)
    return buffer.getvalue()


class QrCodeWidget(Static):
    """Показывает QR кодовой фразы; ``code = None`` — виджет пуст.

    ``code`` — реактивное свойство: присваивание из обработчика
    ``CodeEvent`` в SendPanel (Task 9) немедленно перерисовывает QR.
    """

    code: reactive[str | None] = reactive(None)

    def watch_code(self, code: str | None) -> None:
        if not code:
            self.update("")
            return
        # Text без markup: блочные символы QR не должны трактоваться Rich
        self.update(Text(render_qr_ascii(code)))
