"""Тесты построения аргументов CLI из CrocOptions (Task 2)."""

from __future__ import annotations

import argparse

from pycroc.core.options import (
    CrocOptions,
    build_receive_args,
    build_send_args,
    croc_secret_env,
    normalize_text,
)

# --- Round-trip хелперы: argparse-эквивалент CLI croc -------------------------


def _add_global_flags(parser: argparse.ArgumentParser) -> None:
    """Глобальные флаги croc: идут ДО подкоманды send / кодовой фразы."""
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no-compress", dest="no_compress", action="store_true")
    parser.add_argument("--ask", action="store_true")
    parser.add_argument("--relay")
    parser.add_argument("--relay6")
    parser.add_argument("--pass", dest="pass_")
    parser.add_argument("--socks5")
    parser.add_argument("--connect")
    parser.add_argument("--throttleUpload", dest="throttle_upload")
    parser.add_argument("--curve")
    parser.add_argument("--ignore-stdin", dest="ignore_stdin", action="store_true")


def parse_send_argv(argv: list[str]) -> tuple[CrocOptions, list[str]]:
    """Разбирает argv отправки обратно в (CrocOptions, paths).

    Повторяет реальную структуру CLI croc v10:
    ``[GLOBAL OPTIONS] send [COMMAND OPTIONS] <paths...>``.
    """
    split = argv.index("send")
    global_parser = argparse.ArgumentParser(exit_on_error=False)
    _add_global_flags(global_parser)
    global_ns = global_parser.parse_args(argv[:split])

    send_parser = argparse.ArgumentParser(exit_on_error=False)
    send_parser.add_argument("--transport")
    send_parser.add_argument("--hash", dest="hash_algo")
    send_parser.add_argument("--exclude")
    send_parser.add_argument("--transfers", type=int)
    send_parser.add_argument("--store", action="store_true")
    send_parser.add_argument("--store-downloads", dest="store_downloads", type=int)
    send_parser.add_argument("--store-expiration", dest="store_expiration")
    send_parser.add_argument("--store-url", dest="store_url")
    send_parser.add_argument("paths", nargs="*")
    send_ns = send_parser.parse_args(argv[split + 1 :])

    opts = CrocOptions(
        # code в argv не попадает (уходит через CROC_SECRET) — здесь всегда None
        code=None,
        pass_=global_ns.pass_,
        relay=global_ns.relay,
        relay6=global_ns.relay6,
        out_dir=None,
        socks5=global_ns.socks5,
        connect=global_ns.connect,
        throttle_upload=global_ns.throttle_upload,
        curve=global_ns.curve,
        transport=send_ns.transport,
        hash_algo=send_ns.hash_algo,
        no_compress=global_ns.no_compress,
        ask=global_ns.ask,
        auto_accept=global_ns.yes,
        exclude=tuple(send_ns.exclude.split(",")) if send_ns.exclude else (),
        transfers=send_ns.transfers,
        store=send_ns.store,
        store_downloads=send_ns.store_downloads,
        store_expiration=send_ns.store_expiration,
        store_url=send_ns.store_url,
    )
    return opts, list(send_ns.paths)


def parse_receive_argv(argv: list[str]) -> CrocOptions:
    """Разбирает argv приёма обратно в CrocOptions.

    Кодовая фраза в argv отсутствует (уходит через CROC_SECRET), поэтому
    возвращаются только опции — позиционного аргумента у приёма больше нет.
    """
    parser = argparse.ArgumentParser(exit_on_error=False)
    _add_global_flags(parser)
    parser.add_argument("--out", dest="out_dir")
    ns = parser.parse_args(argv)
    return CrocOptions(
        pass_=ns.pass_,
        relay=ns.relay,
        relay6=ns.relay6,
        out_dir=ns.out_dir,
        socks5=ns.socks5,
        connect=ns.connect,
        throttle_upload=ns.throttle_upload,
        curve=ns.curve,
        no_compress=ns.no_compress,
        ask=ns.ask,
        auto_accept=ns.yes,
    )


# --- --exclude: одна строка через запятую -------------------------------------


def test_exclude_is_single_comma_joined_flag() -> None:
    args = build_send_args(CrocOptions(exclude=("node_modules", ".git")), ["dir"])
    assert args.count("--exclude") == 1
    assert args[args.index("--exclude") + 1] == "node_modules,.git"


def test_empty_exclude_omits_flag() -> None:
    args = build_send_args(CrocOptions(), ["file.txt"])
    assert "--exclude" not in args


# --- --yes / auto_accept -------------------------------------------------------


def test_receive_auto_accept_adds_yes() -> None:
    assert "--yes" in build_receive_args(CrocOptions(auto_accept=True))


def test_receive_no_auto_accept_omits_yes() -> None:
    assert "--yes" not in build_receive_args(CrocOptions(auto_accept=False))


def test_send_auto_accept_adds_yes() -> None:
    assert "--yes" in build_send_args(CrocOptions(auto_accept=True), ["f"])


# --- Позиционные аргументы и направление-специфичные поля ----------------------


def test_send_global_flags_precede_subcommand_send_flags_follow() -> None:
    args = build_send_args(
        CrocOptions(relay="r:9009", hash_algo="imohash"), ["a.txt", "b.txt"]
    )
    # croc [GLOBAL] send [SEND-OPTS] paths — глобальный флаг после send валит croc
    assert args.index("--relay") < args.index("send")
    assert args.index("send") < args.index("--hash")
    assert args[-2:] == ["a.txt", "b.txt"]


def test_send_always_ignores_stdin_receive_never() -> None:
    # stdin процесса — PIPE (для y/n); без --ignore-stdin croc send шлёт stdin
    assert "--ignore-stdin" in build_send_args(CrocOptions(), ["f"])
    assert "--ignore-stdin" not in build_receive_args(CrocOptions())


def test_receive_args_have_no_subcommand_and_no_positional() -> None:
    args = build_receive_args(CrocOptions(relay="my.relay:9009"))
    assert "send" not in args
    assert args[args.index("--relay") + 1] == "my.relay:9009"
    # позиционный аргумент кода убран — код уходит через CROC_SECRET
    assert args[-1] == "my.relay:9009"


def test_code_never_appears_in_argv() -> None:
    # кодовая фраза не должна светиться в списке процессов
    send = build_send_args(CrocOptions(code="slow-tomato-almond"), ["f"])
    assert "slow-tomato-almond" not in send
    assert "--code" not in send
    assert "slow-tomato-almond" not in build_receive_args(CrocOptions())


def test_send_ignores_out_dir() -> None:
    assert "--out" not in build_send_args(CrocOptions(out_dir="/tmp/dl"), ["f"])


def test_receive_ignores_send_only_fields() -> None:
    opts = CrocOptions(
        code="custom-code",
        transport="relay",
        exclude=("x",),
        transfers=8,
        hash_algo="imohash",
        store=True,
        store_downloads=5,
        store_expiration="3d",
        store_url="https://getcroc.com",
    )
    args = build_receive_args(opts)
    assert "--code" not in args
    assert "--exclude" not in args
    assert "--transfers" not in args
    # --hash и --transport — флаги подкоманды send; у приёма их нет, croc упал бы
    assert "--hash" not in args
    assert "--transport" not in args
    # stored-передача (croc v11.1) — тоже только send
    assert not any(a.startswith("--store") for a in args)


# --- --transport: флаг подкоманды send (croc v11.3) ----------------------------


def test_transport_is_send_subcommand_flag() -> None:
    # проверено на реальном croc v11.5.0: --transport — флаг ПОДКОМАНДЫ send,
    # поставленный до send валит croc ("flag provided but not defined")
    args = build_send_args(CrocOptions(transport="derp"), ["f"])
    assert args.index("send") < args.index("--transport")
    assert args[args.index("--transport") + 1] == "derp"


def test_transport_never_on_receive() -> None:
    # у приёма подкоманды send нет — флаг transport к нему неприменим
    assert "--transport" not in build_receive_args(CrocOptions(transport="relay"))


def test_none_transport_omits_flag() -> None:
    assert "--transport" not in build_send_args(CrocOptions(), ["f"])
    assert "--transport" not in build_receive_args(CrocOptions())


# --- stored-передача: флаги подкоманды send (croc v11.1) ----------------------


def test_store_flag_added_only_when_enabled() -> None:
    assert "--store" not in build_send_args(CrocOptions(store=False), ["f"])
    args = build_send_args(CrocOptions(store=True), ["f"])
    assert "--store" in args
    assert args.index("send") < args.index("--store")


def test_store_downloads_and_expiration_follow_send() -> None:
    args = build_send_args(
        CrocOptions(store=True, store_downloads=5, store_expiration="3d"), ["f"]
    )
    assert args[args.index("--store-downloads") + 1] == "5"
    assert args[args.index("--store-expiration") + 1] == "3d"
    assert args.index("send") < args.index("--store-downloads")


def test_none_fields_produce_no_flags() -> None:
    # --ignore-stdin — единственный безусловный флаг отправки
    assert build_send_args(CrocOptions(auto_accept=False), ["f"]) == [
        "--ignore-stdin",
        "send",
        "f",
    ]
    # приём без опций — пустой argv (код уходит через env, позиционного нет)
    assert build_receive_args(CrocOptions(auto_accept=False)) == []


# --- CROC_SECRET: кодовая фраза через окружение --------------------------------


def test_croc_secret_env_adds_variable_over_base() -> None:
    env = croc_secret_env("slow-tomato-almond", {"PATH": "/usr/bin"})
    assert env == {"PATH": "/usr/bin", "CROC_SECRET": "slow-tomato-almond"}


def test_croc_secret_env_none_returns_none_for_inheritance() -> None:
    # нет фразы (send без своего кода) → None, subprocess наследует env родителя
    assert croc_secret_env(None, {"PATH": "/usr/bin"}) is None


# --- Round-trip через argparse-эквивалент --------------------------------------


def test_send_round_trip_all_fields() -> None:
    # code и out_dir в argv отправки не попадают: code — через CROC_SECRET,
    # out_dir осмыслен только при приёме.
    opts = CrocOptions(
        pass_="/path/to/pass-file",
        relay="relay.example.com:9009",
        relay6="[::1]:9009",
        socks5="127.0.0.1:1080",
        connect="proxy.example.com:8080",
        throttle_upload="500k",
        curve="p521",
        transport="derp",
        hash_algo="imohash",
        no_compress=True,
        ask=True,
        auto_accept=True,
        exclude=("node_modules", ".git", "*.log"),
        transfers=8,
        store=True,
        store_downloads=5,
        store_expiration="3d",
        store_url="https://getcroc.com",
    )
    paths = ["report.pdf", "photos/"]
    parsed_opts, parsed_paths = parse_send_argv(build_send_args(opts, paths))
    assert parsed_opts == opts
    assert parsed_paths == paths


def test_send_round_trip_drops_code_from_argv() -> None:
    # своя кодовая фраза не восстанавливается из argv — она ушла в CROC_SECRET
    opts = CrocOptions(code="my-custom-phrase", relay="r:9009")
    parsed_opts, _ = parse_send_argv(build_send_args(opts, ["f"]))
    assert parsed_opts.code is None
    assert parsed_opts.relay == "r:9009"


def test_receive_round_trip_all_fields() -> None:
    # Send-only поля (code/transport/hash_algo/exclude/transfers/store*)
    # не участвуют: receive их игнорирует.
    opts = CrocOptions(
        pass_="s3cret",
        relay="relay.example.com:9009",
        relay6="[::1]:9009",
        out_dir="/home/user/downloads",
        socks5="127.0.0.1:1080",
        connect="proxy.example.com:8080",
        throttle_upload="500k",
        curve="siec",
        no_compress=True,
        ask=True,
        auto_accept=False,
    )
    assert parse_receive_argv(build_receive_args(opts)) == opts


# --- normalize_text: контракт границы UI ---------------------------------------


def test_normalize_text_empty_and_whitespace_to_none() -> None:
    assert normalize_text("") is None
    assert normalize_text("   ") is None
    assert normalize_text(None) is None


def test_normalize_text_strips_value() -> None:
    assert normalize_text("  relay.example.com:9009 ") == "relay.example.com:9009"
