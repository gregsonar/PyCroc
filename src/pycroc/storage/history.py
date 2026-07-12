"""Хранилище истории передач поверх SQLite.

Внутри — синхронный ``sqlite3``, наружу — async-методы через
``asyncio.to_thread``. Схема создаётся лениво при первом обращении
(``CREATE TABLE IF NOT EXISTS``), а не в конструкторе — конструктор не
трогает диск вовсе, что упрощает тесты с временными путями БД.

Конкурентная запись из send и receive одновременно невозможна по построению
(``CrocRunner`` разрешает одну активную передачу), поэтому retry-логики
сверх стандартного timeout ``sqlite3`` нет.
"""

from __future__ import annotations

import asyncio
import builtins
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

Direction = Literal["send", "receive"]
TransferStatus = Literal["done", "error", "cancelled"]

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL,
    filename TEXT NOT NULL,
    size_bytes INTEGER,
    code TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT
)
"""


@dataclass(frozen=True, slots=True)
class TransferRecord:
    """Одна запись истории передач; ``id is None`` — ещё не сохранена."""

    id: int | None
    direction: Direction
    filename: str
    size_bytes: int | None
    code: str
    status: TransferStatus
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None


class HistoryRepository:
    """CRUD записей передач; датавремя хранится ISO-строками."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    async def add(self, record: TransferRecord) -> int:
        """Сохраняет запись, возвращает присвоенный id."""
        return await asyncio.to_thread(self._add_sync, record)

    async def list(
        self, limit: int = 200, query: str | None = None
    ) -> list[TransferRecord]:
        """Записи от новых к старым; ``query`` — регистронезависимая
        подстрока имени файла."""
        return await asyncio.to_thread(self._list_sync, limit, query)

    async def delete(self, record_id: int) -> None:
        """Удаляет запись; несуществующий id — не ошибка (idempotent)."""
        await asyncio.to_thread(self._delete_sync, record_id)

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(_SCHEMA)
        return conn

    def _add_sync(self, record: TransferRecord) -> int:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                """
                INSERT INTO transfers (
                    direction, filename, size_bytes, code, status,
                    started_at, finished_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.direction,
                    record.filename,
                    record.size_bytes,
                    record.code,
                    record.status,
                    record.started_at.isoformat(),
                    record.finished_at.isoformat() if record.finished_at else None,
                    record.error_message,
                ),
            )
            rowid = cursor.lastrowid
        assert rowid is not None
        return rowid

    # builtins.list: в области видимости класса имя list — это метод выше
    def _list_sync(self, limit: int, query: str | None) -> builtins.list[TransferRecord]:
        sql = "SELECT * FROM transfers ORDER BY started_at DESC, id DESC"
        with closing(self._connect()) as conn:
            if not query:
                rows = conn.execute(f"{sql} LIMIT ?", (limit,)).fetchall()
                return [self._row_to_record(row) for row in rows]
            # Фильтр по подстроке — на стороне Python: LIKE/lower() в SQLite
            # регистронезависимы только для ASCII, а имена файлов могут быть
            # кириллицей, умляутами и т.д. casefold() корректен для Unicode.
            rows = conn.execute(sql).fetchall()
        needle = query.casefold()
        records: builtins.list[TransferRecord] = []
        for row in rows:
            if needle in row["filename"].casefold():
                records.append(self._row_to_record(row))
                if len(records) >= limit:
                    break
        return records

    def _delete_sync(self, record_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM transfers WHERE id = ?", (record_id,))

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> TransferRecord:
        return TransferRecord(
            id=row["id"],
            direction=cast(Direction, row["direction"]),
            filename=row["filename"],
            size_bytes=row["size_bytes"],
            code=row["code"],
            status=cast(TransferStatus, row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=(
                datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None
            ),
            error_message=row["error_message"],
        )
