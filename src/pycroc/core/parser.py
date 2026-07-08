"""Разбор строк stderr croc в события.

Чистые функции: ни asyncio, ни subprocess — только ``str -> Event | None``
(и вспомогательная нарезка байтового потока на строки). Формат вывода croc
меняется между версиями, поэтому нераспознанная строка — это ``None``,
а не исключение (``CrocRunner`` логирует такие строки на уровне debug).
"""

from __future__ import annotations

import re

from pycroc.core.events import (
    AcceptPromptEvent,
    CodeEvent,
    ErrorEvent,
    Event,
    ProgressEvent,
    TransferStartEvent,
)

CODE_RE = re.compile(r"^Code is:\s*(?P<code>\S+)")
SENDING_INIT_RE = re.compile(r"^Sending '(?P<name>.+)' \((?P<size>[\d.]+\s?\w+)\)")
ACCEPT_PROMPT_RE = re.compile(r"^Accept '(?P<name>.+)' \((?P<size>[\d.]+\s?\w+)\)\? \(y/n\)")
PROGRESS_RE = re.compile(
    r"(?P<direction>Sending|Receiving)\s+\([^)]*\)\s+"
    r"(?P<filename>\S+)\s+(?P<percent>\d+)%\s*\|[^|]*\|\s*"
    r"\((?P<done>[\d.]+)/(?P<total>[\d.]+)\s*(?P<unit>\w+),\s*"
    r"(?P<rate>[\d.]+)\s*(?P<rate_unit>[\w/]+)\)\s*\[(?P<elapsed>[\w:]+)\]"
)
# У ошибок croc нет единого префикса между версиями — матчим известные начала;
# остальное ловит fallback в CrocRunner по ненулевому коду возврата.
ERROR_RE = re.compile(r"^(?:[Ee]rror\b|failed to\b)")

_LINE_SEP_RE = re.compile(rb"\r\n|\r|\n")


def parse_line(line: str) -> Event | None:
    """Пробует по очереди все известные паттерны; возвращает ``None`` для
    нераспознанной строки (не бросает исключение — формат вывода croc
    меняется между версиями)."""
    line = line.strip()
    if not line:
        return None
    if m := CODE_RE.match(line):
        return CodeEvent(code=m["code"])
    if m := SENDING_INIT_RE.match(line):
        return TransferStartEvent(filename=m["name"], size=m["size"])
    if m := ACCEPT_PROMPT_RE.match(line):
        return AcceptPromptEvent(filename=m["name"], size=m["size"])
    # Прогресс не заякорен: перед ним могут оставаться артефакты перерисовки.
    if m := PROGRESS_RE.search(line):
        return ProgressEvent(
            direction=m["direction"],
            filename=m["filename"],
            percent=int(m["percent"]),
            rate=f"{m['rate']} {m['rate_unit']}",
        )
    if ERROR_RE.match(line):
        return ErrorEvent(message=line)
    return None


def split_stream_chunks(buffer: bytes) -> tuple[list[str], bytes]:
    """Отрезает от накопленного буфера завершённые строки, возвращает
    ``(строки, неполный остаток)``.

    croc перерисовывает прогресс-бар через ``\\r`` без ``\\n``, поэтому
    ``readline()`` "из коробки" слипает все обновления в одну строку до конца
    передачи — разделителем считается ``\\r\\n``, ``\\r`` или ``\\n``.
    Вызывающая сторона дописывает новые байты к остатку и вызывает функцию
    снова; по EOF остаток декодируется как финальная строка.

    Финальный одиночный ``\\r`` удерживается в остатке: он может оказаться
    первой половиной ``\\r\\n``, разрезанного границей чанка.
    """
    if buffer.endswith(b"\r"):
        splittable, held_back = buffer[:-1], b"\r"
    else:
        splittable, held_back = buffer, b""
    parts = _LINE_SEP_RE.split(splittable)
    remainder = parts.pop() + held_back
    lines = [part.decode("utf-8", errors="replace") for part in parts]
    return lines, remainder
