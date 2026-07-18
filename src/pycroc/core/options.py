"""Опции croc и построение аргументов командной строки.

Контракт нормализации: все текстовые поля ``CrocOptions`` должны быть
нормализованы на границе UI *до* создания объекта — пустая строка после
``strip()`` обязана превратиться в ``None`` (для этого есть
:func:`normalize_text`). Функции ``build_*_args`` не перепроверяют это:
``None`` означает "флаг не передаётся", любая непустая строка передаётся
в argv как есть (в частности, ``pass_`` может быть путём к файлу с паролем —
croc поддерживает ``--pass FILEWITHPASSWORD``, валидация формата не нужна).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CrocOptions:
    """Набор опций croc, общий для отправки и приёма.

    Поля, специфичные для одного направления, игнорируются другим билдером:
    ``code``, ``exclude``, ``transfers`` — только send; ``out_dir`` — только receive.
    """

    code: str | None = None  # --code (только send)
    pass_: str | None = None  # --pass
    relay: str | None = None  # --relay
    relay6: str | None = None  # --relay6
    out_dir: str | None = None  # --out (только receive)
    socks5: str | None = None  # --socks5
    connect: str | None = None  # --connect (http-proxy)
    throttle_upload: str | None = None  # --throttleUpload, напр. "500k"
    curve: str | None = None  # p256 | p384 | p521 | siec | ed25519 (croc v10)
    hash_algo: str | None = None  # xxhash | imohash | md5 (только send)
    no_compress: bool = False
    ask: bool = False
    auto_accept: bool = True  # управляет --yes И реакцией на AcceptPromptEvent
    exclude: tuple[str, ...] = field(default_factory=tuple)
    transfers: int | None = None


def normalize_text(value: str | None) -> str | None:
    """Хелпер для границы UI: пустая после ``strip()`` строка -> ``None``.

    Применяется к значениям текстовых полей формы перед созданием
    ``CrocOptions``, иначе в argv попадёт, например, ``--relay ""``.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _global_args(opts: CrocOptions) -> list[str]:
    """Глобальные флаги croc.

    ВАЖНО (проверено на реальном croc v10.2.7, Task 14): формат CLI —
    ``croc [GLOBAL OPTIONS] [COMMAND] [COMMAND OPTIONS] [files]``.
    Глобальный флаг, поставленный ПОСЛЕ подкоманды ``send``, валит процесс
    с usage в stdout и пустым stderr.
    """
    args: list[str] = []
    if opts.auto_accept:
        args.append("--yes")
    if opts.no_compress:
        args.append("--no-compress")
    if opts.ask:
        args.append("--ask")
    value_flags: tuple[tuple[str, str | None], ...] = (
        ("--relay", opts.relay),
        ("--relay6", opts.relay6),
        ("--pass", opts.pass_),
        ("--socks5", opts.socks5),
        ("--connect", opts.connect),
        ("--throttleUpload", opts.throttle_upload),
        ("--curve", opts.curve),
    )
    for flag, value in value_flags:
        if value is not None:
            args.extend((flag, value))
    return args


def build_send_args(opts: CrocOptions, paths: Sequence[str]) -> list[str]:
    """Полный хвост argv для отправки: ``croc <результат>``.

    Возвращает ``[<глобальные флаги>, "send", <флаги send>, <paths...>]``.
    Флаги подкоманды ``send``: ``--code``, ``--hash``, ``--exclude``,
    ``--transfers``. Поле ``out_dir`` игнорируется (имеет смысл только при
    приёме). ``exclude`` croc принимает одной строкой через запятую — флаг
    ``--exclude`` добавляется ровно один раз.

    ``--ignore-stdin`` добавляется всегда: ``CrocRunner`` открывает stdin
    процесса как PIPE, а croc send с piped stdin переключается в режим
    ``cat file | croc send`` — отправляет stdin вместо файлов и ждёт EOF
    вечно. Приёму флаг ставить нельзя: там stdin нужен для ответов y/n.
    """
    args = [*_global_args(opts), "--ignore-stdin", "send"]
    if opts.code is not None:
        args.extend(("--code", opts.code))
    if opts.hash_algo is not None:
        args.extend(("--hash", opts.hash_algo))
    if opts.exclude:
        args.extend(("--exclude", ",".join(opts.exclude)))
    if opts.transfers is not None:
        args.extend(("--transfers", str(opts.transfers)))
    args.extend(paths)
    return args


def build_receive_args(opts: CrocOptions, code: str) -> list[str]:
    """Полный хвост argv для приёма: ``croc <результат>``.

    Приём у croc — без подкоманды, кодовая фраза передаётся позиционным
    аргументом ``code``. Send-only поля (``opts.code``, ``hash_algo``,
    ``exclude``, ``transfers``) игнорируются: у приёма таких флагов нет,
    и croc упал бы на неизвестном флаге.
    """
    args = _global_args(opts)
    if opts.out_dir is not None:
        args.extend(("--out", opts.out_dir))
    args.append(code)
    return args
