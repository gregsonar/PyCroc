"""Исключения core-слоя pycroc."""

from __future__ import annotations


class CrocError(Exception):
    """Базовое исключение pycroc."""


class CrocNotFoundError(CrocError):
    """Бинарник croc не найден или не удалось запустить."""


class TransferInProgressError(CrocError):
    """Попытка запустить передачу при уже активном процессе croc.

    croc — один канал на процесс; параллельный send/receive из одного
    приложения запрещён на уровне ``CrocRunner``.
    """
