"""Хранилище конфигурации и профилей опций поверх TOML.

Файл (по умолчанию ``platformdirs.user_config_dir("pycroc")/config.toml``)
редактируем вручную, поэтому используется ``tomlkit``: он сохраняет
комментарии и форматирование нетронутых секций при записи.

Устойчивость к порче: повреждённый или структурно неверный TOML не роняет
приложение — чтение откатывается на пустой документ (профиль ``default``
в памяти), а путь и причина сбоя доступны UI через ``last_load_error``
для предупреждения пользователю. Значения неожиданных типов внутри профиля
(след ручной правки) молча заменяются значениями по умолчанию.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs
import tomlkit
from tomlkit import TOMLDocument

from pycroc.core.options import CrocOptions

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_NAME = "default"


@dataclass(frozen=True, slots=True)
class Profile:
    """Именованный набор опций croc."""

    name: str
    options: CrocOptions


def _options_to_table(opts: CrocOptions) -> dict[str, object]:
    """``CrocOptions`` -> TOML-таблица; ``None``-поля опускаются (в TOML нет null)."""
    table: dict[str, object] = {}
    text_fields: tuple[tuple[str, str | None], ...] = (
        ("code", opts.code),
        ("pass", opts.pass_),
        ("relay", opts.relay),
        ("relay6", opts.relay6),
        ("out_dir", opts.out_dir),
        ("socks5", opts.socks5),
        ("connect", opts.connect),
        ("throttle_upload", opts.throttle_upload),
        ("curve", opts.curve),
        ("hash_algo", opts.hash_algo),
    )
    for key, value in text_fields:
        if value is not None:
            table[key] = value
    table["no_compress"] = opts.no_compress
    table["ask"] = opts.ask
    table["auto_accept"] = opts.auto_accept
    table["exclude"] = list(opts.exclude)
    if opts.transfers is not None:
        table["transfers"] = opts.transfers
    return table


def _options_from_table(data: Mapping[str, object]) -> CrocOptions:
    """TOML-таблица -> ``CrocOptions``; значения неверных типов игнорируются."""

    def opt_str(key: str) -> str | None:
        value = data.get(key)
        return value if isinstance(value, str) and value else None

    def opt_bool(key: str, default: bool) -> bool:
        value = data.get(key)
        return value if isinstance(value, bool) else default

    exclude_raw = data.get("exclude")
    exclude = (
        tuple(item for item in exclude_raw if isinstance(item, str))
        if isinstance(exclude_raw, list | tuple)
        else ()
    )
    transfers_raw = data.get("transfers")
    transfers = (
        transfers_raw
        if isinstance(transfers_raw, int) and not isinstance(transfers_raw, bool)
        else None
    )
    return CrocOptions(
        code=opt_str("code"),
        pass_=opt_str("pass"),
        relay=opt_str("relay"),
        relay6=opt_str("relay6"),
        out_dir=opt_str("out_dir"),
        socks5=opt_str("socks5"),
        connect=opt_str("connect"),
        throttle_upload=opt_str("throttle_upload"),
        curve=opt_str("curve"),
        hash_algo=opt_str("hash_algo"),
        no_compress=opt_bool("no_compress", False),
        ask=opt_bool("ask", False),
        auto_accept=opt_bool("auto_accept", True),
        exclude=exclude,
        transfers=transfers,
    )


class ConfigStore:
    """CRUD профилей, активный профиль и путь к бинарнику croc."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            config_path = Path(platformdirs.user_config_dir("pycroc")) / "config.toml"
        self._config_path = Path(config_path)
        #: Причина последнего сбоя чтения файла (с путём) или None; UI
        #: показывает это предупреждением, не прерывая работу.
        self.last_load_error: str | None = None

    def load_profiles(self) -> dict[str, Profile]:
        """Все профили из файла; ``default`` присутствует всегда."""
        doc = self._read_document()
        profiles: dict[str, Profile] = {}
        raw_profiles = doc.get("profiles")
        if isinstance(raw_profiles, Mapping):
            for name, table in raw_profiles.items():
                if isinstance(table, Mapping):
                    profiles[str(name)] = Profile(
                        name=str(name), options=_options_from_table(table)
                    )
        profiles.setdefault(
            DEFAULT_PROFILE_NAME, Profile(DEFAULT_PROFILE_NAME, CrocOptions())
        )
        return profiles

    def save_profile(self, profile: Profile) -> None:
        doc = self._read_document()
        profiles = doc.get("profiles")
        if not isinstance(profiles, MutableMapping):
            profiles = tomlkit.table()
            doc["profiles"] = profiles
        profiles[profile.name] = _options_to_table(profile.options)
        self._write(doc)

    def delete_profile(self, name: str) -> None:
        """Удаляет профиль; ``default`` защищён (fallback, если пользователь
        удалит все остальные). Несуществующее имя — no-op. Если удалён
        активный профиль, активным становится ``default``."""
        if name == DEFAULT_PROFILE_NAME:
            raise ValueError('профиль "default" нельзя удалить')
        doc = self._read_document()
        profiles = doc.get("profiles")
        if not isinstance(profiles, MutableMapping) or name not in profiles:
            return
        del profiles[name]
        if doc.get("active_profile") == name:
            doc["active_profile"] = DEFAULT_PROFILE_NAME
        self._write(doc)

    def get_active_profile_name(self) -> str:
        doc = self._read_document()
        name = doc.get("active_profile")
        if not isinstance(name, str):
            return DEFAULT_PROFILE_NAME
        if name == DEFAULT_PROFILE_NAME:
            return name
        raw_profiles = doc.get("profiles")
        # имя, не существующее в profiles (ручная правка), — откат на default
        if isinstance(raw_profiles, Mapping) and name in raw_profiles:
            return name
        return DEFAULT_PROFILE_NAME

    def set_active_profile_name(self, name: str) -> None:
        doc = self._read_document()
        raw_profiles = doc.get("profiles")
        known = isinstance(raw_profiles, Mapping) and name in raw_profiles
        if name != DEFAULT_PROFILE_NAME and not known:
            raise ValueError(f"нет такого профиля: {name!r}")
        doc["active_profile"] = name
        self._write(doc)

    def get_binary_path(self) -> str:
        doc = self._read_document()
        path = doc.get("binary_path")
        return path if isinstance(path, str) and path else "croc"

    def set_binary_path(self, path: str) -> None:
        doc = self._read_document()
        doc["binary_path"] = path
        self._write(doc)

    def _read_document(self) -> TOMLDocument:
        self.last_load_error = None
        if not self._config_path.exists():
            return tomlkit.document()
        try:
            return tomlkit.parse(self._config_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — любая порча файла не должна крашить
            self.last_load_error = f"{self._config_path}: {exc}"
            logger.warning("не удалось прочитать конфиг %s: %s", self._config_path, exc)
            return tomlkit.document()

    def _write(self, doc: TOMLDocument) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
