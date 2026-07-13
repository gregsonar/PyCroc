"""Тесты ConfigStore и профилей (Task 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pycroc.core.options import CrocOptions
from pycroc.storage.config import ConfigStore, Profile

FULL_OPTIONS = CrocOptions(
    code="my-custom-phrase",
    pass_="/path/to/pass-file",
    relay="relay.example.com:9009",
    relay6="[::1]:9009",
    out_dir="/home/user/downloads",
    socks5="127.0.0.1:1080",
    connect="proxy.example.com:8080",
    throttle_upload="500k",
    curve="P-521",
    hash_algo="imohash",
    no_compress=True,
    ask=True,
    auto_accept=False,
    exclude=("node_modules", ".git", "*.log"),
    transfers=8,
)


def _store(tmp_path: Path) -> ConfigStore:
    return ConfigStore(tmp_path / "config.toml")


# --- save + load round-trip ------------------------------------------------------


def test_save_and_load_round_trip_all_fields(tmp_path: Path) -> None:
    _store(tmp_path).save_profile(Profile("work", FULL_OPTIONS))
    # новый экземпляр — гарантия, что читаем с диска, а не из памяти
    loaded = _store(tmp_path).load_profiles()
    assert loaded["work"] == Profile("work", FULL_OPTIONS)


def test_exclude_round_trips_as_toml_array(tmp_path: Path) -> None:
    _store(tmp_path).save_profile(Profile("work", FULL_OPTIONS))
    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert 'exclude = ["node_modules", ".git", "*.log"]' in text
    loaded = _store(tmp_path).load_profiles()["work"].options.exclude
    assert isinstance(loaded, tuple)
    assert loaded == ("node_modules", ".git", "*.log")


def test_load_profiles_always_contains_default(tmp_path: Path) -> None:
    assert _store(tmp_path).load_profiles() == {
        "default": Profile("default", CrocOptions())
    }


def test_save_overwrites_existing_profile(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_profile(Profile("work", FULL_OPTIONS))
    store.save_profile(Profile("work", CrocOptions(relay="other:9009")))
    assert _store(tmp_path).load_profiles()["work"].options == CrocOptions(relay="other:9009")


# --- защита default ----------------------------------------------------------------


def test_delete_default_raises_and_keeps_profile(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_profile(Profile("default", CrocOptions(relay="my:9009")))
    with pytest.raises(ValueError, match="default"):
        store.delete_profile("default")
    assert store.load_profiles()["default"].options == CrocOptions(relay="my:9009")


def test_delete_profile_removes_it_and_resets_active(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_profile(Profile("work", FULL_OPTIONS))
    store.set_active_profile_name("work")
    store.delete_profile("work")
    assert "work" not in store.load_profiles()
    assert store.get_active_profile_name() == "default"


def test_delete_nonexistent_profile_is_noop(tmp_path: Path) -> None:
    _store(tmp_path).delete_profile("no-such-profile")


# --- активный профиль ----------------------------------------------------------------


def test_active_profile_defaults_to_default(tmp_path: Path) -> None:
    assert _store(tmp_path).get_active_profile_name() == "default"


def test_set_and_get_active_profile(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_profile(Profile("work", FULL_OPTIONS))
    store.set_active_profile_name("work")
    assert _store(tmp_path).get_active_profile_name() == "work"


def test_set_active_to_unknown_profile_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no-such"):
        _store(tmp_path).set_active_profile_name("no-such")


def test_active_pointing_to_missing_profile_falls_back(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        'active_profile = "deleted-by-hand"\n', encoding="utf-8"
    )
    assert _store(tmp_path).get_active_profile_name() == "default"


# --- путь к бинарнику -----------------------------------------------------------------


def test_binary_path_defaults_to_croc(tmp_path: Path) -> None:
    assert _store(tmp_path).get_binary_path() == "croc"


def test_set_and_get_binary_path(tmp_path: Path) -> None:
    _store(tmp_path).set_binary_path("C:/tools/croc.exe")
    assert _store(tmp_path).get_binary_path() == "C:/tools/croc.exe"


# --- повреждённый файл ------------------------------------------------------------------


def test_corrupted_toml_falls_back_to_default_without_raising(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("this is [ not valid ==== toml", encoding="utf-8")
    store = ConfigStore(config_path)
    assert store.load_profiles() == {"default": Profile("default", CrocOptions())}
    assert store.last_load_error is not None
    assert str(config_path) in store.last_load_error


def test_structurally_wrong_toml_does_not_crash(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'profiles = "banana"\nactive_profile = 42\nbinary_path = false\n',
        encoding="utf-8",
    )
    store = ConfigStore(config_path)
    assert store.load_profiles() == {"default": Profile("default", CrocOptions())}
    assert store.get_active_profile_name() == "default"
    assert store.get_binary_path() == "croc"


def test_wrong_value_types_inside_profile_are_ignored(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[profiles.broken]\n"
        "relay = 9009\n"  # не строка
        'auto_accept = "yes"\n'  # не bool
        'transfers = true\n'  # bool вместо int
        'exclude = "not-an-array"\n',
        encoding="utf-8",
    )
    loaded = ConfigStore(config_path).load_profiles()
    assert loaded["broken"].options == CrocOptions()


# --- сохранение ручного форматирования ---------------------------------------------------


def test_save_preserves_manual_comments(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "# мой конфиг, не трогать\n"
        'binary_path = "C:/tools/croc.exe"  # самосборный\n',
        encoding="utf-8",
    )
    store = ConfigStore(config_path)
    store.save_profile(Profile("work", CrocOptions(relay="my:9009")))
    text = config_path.read_text(encoding="utf-8")
    assert "# мой конфиг, не трогать" in text
    assert "# самосборный" in text
    assert store.get_binary_path() == "C:/tools/croc.exe"
