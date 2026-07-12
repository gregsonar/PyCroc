"""Тесты HistoryRepository (Task 5)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from pycroc.storage.history import HistoryRepository, TransferRecord


def _record(**overrides: Any) -> TransferRecord:
    defaults: dict[str, Any] = {
        "id": None,
        "direction": "send",
        "filename": "report.pdf",
        "size_bytes": 116,
        "code": "slow-tomato-almond",
        "status": "done",
        "started_at": datetime(2026, 7, 8, 12, 30, 15),
        "finished_at": datetime(2026, 7, 8, 12, 31, 40),
        "error_message": None,
    }
    return TransferRecord(**{**defaults, **overrides})


async def test_add_and_list_restores_record_with_dates(tmp_path: Path) -> None:
    repo = HistoryRepository(tmp_path / "history.db")
    record = _record()
    new_id = await repo.add(record)
    assert await repo.list() == [replace(record, id=new_id)]


async def test_add_and_list_none_fields_survive_round_trip(tmp_path: Path) -> None:
    repo = HistoryRepository(tmp_path / "history.db")
    record = _record(
        status="error",
        size_bytes=None,
        finished_at=None,
        error_message="croc завершился с кодом 1",
    )
    new_id = await repo.add(record)
    assert await repo.list() == [replace(record, id=new_id)]


async def test_list_query_filters_filename_case_insensitively(tmp_path: Path) -> None:
    repo = HistoryRepository(tmp_path / "history.db")
    await repo.add(_record(filename="report.pdf"))
    await repo.add(_record(filename="REPORT.pdf"))
    await repo.add(_record(filename="photo.jpg"))

    found = await repo.list(query="Report.PDF")
    assert sorted(r.filename for r in found) == ["REPORT.pdf", "report.pdf"]

    assert await repo.list(query="нет-такого-файла") == []


async def test_list_query_treats_sql_wildcard_chars_literally(tmp_path: Path) -> None:
    repo = HistoryRepository(tmp_path / "history.db")
    await repo.add(_record(filename="100%_done.txt"))
    await repo.add(_record(filename="100x-done.txt"))

    found = await repo.list(query="100%_")
    assert [r.filename for r in found] == ["100%_done.txt"]


async def test_list_query_is_case_insensitive_for_non_ascii(tmp_path: Path) -> None:
    repo = HistoryRepository(tmp_path / "history.db")
    await repo.add(_record(filename="Отчёт-Июль.pdf"))
    await repo.add(_record(filename="Straße-Plan.pdf"))
    await repo.add(_record(filename="年度报告.pdf"))
    await repo.add(_record(filename="unrelated.txt"))

    assert [r.filename for r in await repo.list(query="отчёт")] == ["Отчёт-Июль.pdf"]
    assert [r.filename for r in await repo.list(query="ОТЧЁТ-и")] == ["Отчёт-Июль.pdf"]
    # casefold: ß эквивалентно ss
    assert [r.filename for r in await repo.list(query="STRASSE")] == ["Straße-Plan.pdf"]
    assert [r.filename for r in await repo.list(query="报告")] == ["年度报告.pdf"]


async def test_list_orders_newest_first_and_respects_limit(tmp_path: Path) -> None:
    repo = HistoryRepository(tmp_path / "history.db")
    await repo.add(_record(filename="old.txt", started_at=datetime(2026, 7, 1, 10, 0)))
    await repo.add(_record(filename="new.txt", started_at=datetime(2026, 7, 8, 10, 0)))
    await repo.add(_record(filename="mid.txt", started_at=datetime(2026, 7, 4, 10, 0)))

    assert [r.filename for r in await repo.list()] == ["new.txt", "mid.txt", "old.txt"]
    assert [r.filename for r in await repo.list(limit=2)] == ["new.txt", "mid.txt"]


async def test_delete_removes_record_and_is_idempotent(tmp_path: Path) -> None:
    repo = HistoryRepository(tmp_path / "history.db")
    record_id = await repo.add(_record())

    await repo.delete(record_id)
    assert await repo.list() == []

    await repo.delete(record_id)  # повторное удаление — не ошибка
    await repo.delete(999_999)  # несуществующий id — не ошибка


async def test_schema_is_created_lazily_not_in_constructor(tmp_path: Path) -> None:
    db_path = tmp_path / "subdir" / "history.db"
    repo = HistoryRepository(db_path)
    assert not db_path.exists(), "конструктор не должен трогать диск"

    assert await repo.list() == []  # первое обращение создаёт каталог и схему
    assert db_path.exists()
