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


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument("--hash", dest="hash_algo")


def parse_send_argv(argv: list[str]) -> tuple[CrocOptions, list[str]]:
    """Разбирает argv отправки обратно в (CrocOptions, paths)."""
    assert argv[0] == "send"
    parser = argparse.ArgumentParser(exit_on_error=False)
    _add_common_flags(parser)
    parser.add_argument("--code")
    parser.add_argument("--exclude")
    parser.add_argument("--transfers", type=int)
    parser.add_argument("paths", nargs="*")
    ns = parser.parse_args(argv[1:])
    opts = CrocOptions(
        code=ns.code,
        pass_=ns.pass_,
        relay=ns.relay,
        relay6=ns.relay6,
        out_dir=None,
        socks5=ns.socks5,
        connect=ns.connect,
        throttle_upload=ns.throttle_upload,
        curve=ns.curve,
        hash_algo=ns.hash_algo,
        no_compress=ns.no_compress,
        ask=ns.ask,
        auto_accept=ns.yes,
        exclude=tuple(ns.exclude.split(",")) if ns.exclude else (),
        transfers=ns.transfers,
    )
    return opts, list(ns.paths)


def parse_receive_argv(argv: list[str]) -> tuple[CrocOptions, str]:
    """Разбирает argv приёма обратно в (CrocOptions, code)."""
    parser = argparse.ArgumentParser(exit_on_error=False)
    _add_common_flags(parser)
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
        hash_algo=ns.hash_algo,
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


def test_send_args_start_with_subcommand_and_end_with_paths() -> None:
    args = build_send_args(CrocOptions(), ["a.txt", "b.txt"])
    assert args[0] == "send"
    assert args[-2:] == ["a.txt", "b.txt"]


def test_receive_args_have_no_subcommand_and_end_with_code() -> None:
    args = build_receive_args(CrocOptions(relay="my.relay:9009"), "slow-tomato-almond")
    assert args[0] != "send"
    assert args[-1] == "slow-tomato-almond"
    assert args[args.index("--relay") + 1] == "my.relay:9009"


def test_send_ignores_out_dir() -> None:
    assert "--out" not in build_send_args(CrocOptions(out_dir="/tmp/dl"), ["f"])


def test_receive_ignores_send_only_fields() -> None:
    opts = CrocOptions(code="custom-code", exclude=("x",), transfers=8)
    args = build_receive_args(opts, "a-b-c")
    assert "--code" not in args
    assert "--exclude" not in args
    assert "--transfers" not in args


def test_none_fields_produce_no_flags() -> None:
    assert build_send_args(CrocOptions(auto_accept=False), ["f"]) == ["send", "f"]
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
        curve="P-521",
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
    # Send-only поля (code/exclude/transfers) не участвуют: receive их игнорирует.
    opts = CrocOptions(
        pass_="s3cret",
        relay="relay.example.com:9009",
        relay6="[::1]:9009",
        out_dir="/home/user/downloads",
        socks5="127.0.0.1:1080",
        connect="proxy.example.com:8080",
        throttle_upload="500k",
        curve="SIEC",
        hash_algo="xxhash",
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
