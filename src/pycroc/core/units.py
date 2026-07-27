"""Человекочитаемые размеры файлов.

croc печатает размеры в SI-нотации (база 1000: «6.2 kB» для 6200 байт —
подтверждено замером на реальном croc v10.2.7). Форматтер и парсер здесь
согласованы по базе 1000, поэтому размер, разобранный из строки croc и
показанный в истории, совпадает с тем, что croc показал при передаче.
"""

from __future__ import annotations

import re

_PARSE_RE = re.compile(r"^\s*(?P<value>[\d.]+)\s*(?P<unit>[kKMGT]?B)\s*$")
_FACTORS = {
    "B": 1,
    "KB": 1_000,
    "MB": 1_000_000,
    "GB": 1_000_000_000,
    "TB": 1_000_000_000_000,
}


def format_size(size_bytes: int | None) -> str:
    """Байты -> строка вида ``6.2 kB``; ``None`` -> ``«—»`` (нет данных)."""
    if size_bytes is None:
        return "—"
    size = float(size_bytes)
    if size < 1000:
        return f"{int(size)} B"
    for unit in ("kB", "MB", "GB", "TB"):
        size /= 1000
        if size < 1000:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"


def parse_size(text: str | None) -> int | None:
    """Строка croc (``6.2 kB``, ``116 B``) -> байты; ``None`` при неразборе.

    Не бросает исключений — неизвестный формат даёт ``None`` (в истории
    отрисуется «—»), как и любой другой парсинг вывода croc.
    """
    if text is None:
        return None
    match = _PARSE_RE.match(text)
    if match is None:
        return None
    factor = _FACTORS.get(match["unit"].upper())
    if factor is None:
        return None
    return round(float(match["value"]) * factor)
