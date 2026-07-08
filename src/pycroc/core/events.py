"""События, извлекаемые из stderr croc.

Чистые dataclasses без логики: производятся :mod:`pycroc.core.parser`
(и ``CrocRunner`` — для ``DoneEvent``/``ErrorEvent`` по коду возврата),
потребляются UI-виджетами.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodeEvent:
    """Кодовая фраза передачи: ``Code is: slow-tomato-almond``."""

    code: str


@dataclass(frozen=True, slots=True)
class TransferStartEvent:
    """Начало отправки: ``Sending 'file.txt' (116 B)``."""

    filename: str
    size: str


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Строка прогресс-бара (Sending/Receiving ... N% ...)."""

    direction: str
    filename: str
    percent: int
    rate: str


@dataclass(frozen=True, slots=True)
class AcceptPromptEvent:
    """Запрос подтверждения на приёме: ``Accept 'file.txt' (116 B)? (y/n)``."""

    filename: str
    size: str


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """Явная строка ошибки croc либо fallback от ``CrocRunner``."""

    message: str


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """Успешное завершение передачи (эмитится ``CrocRunner`` по returncode 0)."""

    filename: str | None = None


Event = (
    CodeEvent
    | TransferStartEvent
    | ProgressEvent
    | AcceptPromptEvent
    | ErrorEvent
    | DoneEvent
)
