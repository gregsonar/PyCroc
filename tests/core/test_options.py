"""Тесты построения аргументов CLI из CrocOptions (Task 2)."""

from __future__ import annotations

import argparse

from pycroc.core.options import (
    CrocOptions,
    build_receive_args,
    build_send_args,
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
    send_parser.add_argument("--code")
    send_parser.add_argument("--hash", dest="hash_algo")
    send_parser.add_argument("--exclude")
    send_parser.add_argument("--transfers", type=int)
    send_parser.add_argument("paths", nargs="*")
    send_ns = send_parser.parse_args(argv[split + 1 :])

    opts = CrocOptions(
        code=send_ns.code,
        pass_=global_ns.pass_,
        relay=global_ns.relay,
        relay6=global_ns.relay6,
        out_dir=None,
        socks5=global_ns.socks5,
        connect=global_ns.connect,
        throttle_upload=global_ns.throttle_upload,
        curve=global_ns.curve,
        hash_algo=send_ns.hash_algo,
        no_compress=global_ns.no_compress,
        ask=global_ns.ask,
        auto_accept=global_ns.yes,
        exclude=tuple(send_ns.exclude.split(",")) if send_ns.exclude else (),
        transfers=send_ns.transfers,
    )
    return opts, list(send_ns.paths)


def parse_receive_argv(argv: list[str]) -> tuple[CrocOptions, str]:
    """Разбирает argv приёма обратно в (CrocOptions, code)."""
    parser = argparse.ArgumentParser(exit_on_error=False)
    _add_global_flags(parser)
    parser.add_argument("--out", dest="out_dir")
    parser.add_argument("code")
    ns = parser.parse_args(argv)
    opts = CrocOptions(
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
    return opts, str(ns.code)


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
    assert "--yes" in build_receive_args(CrocOptions(auto_accept=True), "a-b-c")


def test_receive_no_auto_accept_omits_yes() -> None:
    assert "--yes" not in build_receive_args(CrocOptions(auto_accept=False), "a-b-c")


def test_send_auto_accept_adds_yes() -> None:
    assert "--yes" in build_send_args(CrocOptions(auto_accept=True), ["f"])


# --- Позиционные аргументы и направление-специфичные поля ----------------------


def test_send_global_flags_precede_subcommand_send_flags_follow() -> None:
    args = build_send_args(
        CrocOptions(relay="r:9009", code="x-y", hash_algo="imohash"), ["a.txt", "b.txt"]
    )
    # croc [GLOBAL] send [SEND-OPTS] paths — глобальный флаг после send валит croc
    assert args.index("--relay") < args.index("send")
    assert args.index("send") < args.index("--code")
    assert args.index("send") < args.index("--hash")
    assert args[-2:] == ["a.txt", "b.txt"]


def test_send_always_ignores_stdin_receive_never() -> None:
    # stdin процесса — PIPE (для y/n); без --ignore-stdin croc send шлёт stdin
    assert "--ignore-stdin" in build_send_args(CrocOptions(), ["f"])
    assert "--ignore-stdin" not in build_receive_args(CrocOptions(), "a-b-c")


def test_receive_args_have_no_subcommand_and_end_with_code() -> None:
    args = build_receive_args(CrocOptions(relay="my.relay:9009"), "slow-tomato-almond")
    assert args[0] != "send"
    assert args[-1] == "slow-tomato-almond"
    assert args[args.index("--relay") + 1] == "my.relay:9009"


def test_send_ignores_out_dir() -> None:
    assert "--out" not in build_send_args(CrocOptions(out_dir="/tmp/dl"), ["f"])


def test_receive_ignores_send_only_fields() -> None:
    opts = CrocOptions(code="custom-code", exclude=("x",), transfers=8, hash_algo="imohash")
    args = build_receive_args(opts, "a-b-c")
    assert "--code" not in args
    assert "--exclude" not in args
    assert "--transfers" not in args
    # --hash — флаг подкоманды send; у приёма его нет, croc упал бы
    assert "--hash" not in args


def test_none_fields_produce_no_flags() -> None:
    # --ignore-stdin — единственный безусловный флаг отправки
    assert build_send_args(CrocOptions(auto_accept=False), ["f"]) == [
        "--ignore-stdin",
        "send",
        "f",
    ]
    assert build_receive_args(CrocOptions(auto_accept=False), "a-b-c") == ["a-b-c"]


# --- Round-trip через argparse-эквивалент --------------------------------------


def test_send_round_trip_all_fields() -> None:
    # out_dir не участвует: в argv отправки он не попадает по построению.
    opts = CrocOptions(
        code="my-custom-phrase",
        pass_="/path/to/pass-file",
        relay="relay.example.com:9009",
        relay6="[::1]:9009",
        socks5="127.0.0.1:1080",
        connect="proxy.example.com:8080",
        throttle_upload="500k",
        curve="p521",
        hash_algo="imohash",
        no_compress=True,
        ask=True,
        auto_accept=True,
        exclude=("node_modules", ".git", "*.log"),
        transfers=8,
    )
    paths = ["report.pdf", "photos/"]
    parsed_opts, parsed_paths = parse_send_argv(build_send_args(opts, paths))
    assert parsed_opts == opts
    assert parsed_paths == paths


def test_receive_round_trip_all_fields() -> None:
    # Send-only поля (code/hash_algo/exclude/transfers) не участвуют:
    # receive их игнорирует.
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
    parsed_opts, parsed_code = parse_receive_argv(build_receive_args(opts, "slow-tomato-almond"))
    assert parsed_opts == opts
    assert parsed_code == "slow-tomato-almond"


# --- normalize_text: контракт границы UI ---------------------------------------


def test_normalize_text_empty_and_whitespace_to_none() -> None:
    assert normalize_text("") is None
    assert normalize_text("   ") is None
    assert normalize_text(None) is None


def test_normalize_text_strips_value() -> None:
    assert normalize_text("  relay.example.com:9009 ") == "relay.example.com:9009"
