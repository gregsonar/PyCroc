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

from collections.abc import Mapping, Sequence
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
    # --transport: auto | derp | relay (croc v11.3, флаг подкоманды send —
    # это выбор ОТПРАВИТЕЛЯ, у приёма такого флага нет)
    transport: str | None = None
    hash_algo: str | None = None  # xxhash | imohash | md5 (только send)
    no_compress: bool = False
    ask: bool = False
    auto_accept: bool = True  # управляет --yes И реакцией на AcceptPromptEvent
    exclude: tuple[str, ...] = field(default_factory=tuple)
    transfers: int | None = None
    # Stored-передача (croc v11.1, только send): один зашифрованный upload
    # обслуживает несколько получателей по ссылке/токену в течение срока жизни.
    store: bool = False  # --store
    store_downloads: int | None = None  # --store-downloads N (число выдач)
    store_expiration: str | None = None  # --store-expiration, напр. "3d"
    store_url: str | None = None  # --store-url (по умолчанию https://getcroc.com)


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
    Флаги подкоманды ``send``: ``--transport`` (croc v11.3, выбор транспорта
    отправителем), ``--hash``, ``--exclude``, ``--transfers``,
    ``--store``/``--store-downloads``/``--store-expiration``/``--store-url``
    (stored-передача croc v11.1). Поле ``out_dir`` игнорируется (имеет смысл
    только при приёме). ``exclude`` croc принимает одной строкой через запятую —
    флаг ``--exclude`` добавляется ровно один раз.

    Кодовая фраза (``opts.code``) в argv НЕ попадает: она передаётся через
    переменную окружения ``CROC_SECRET`` (см. :func:`croc_secret_env`),
    чтобы не светиться в списке процессов ОС — это рекомендует сам croc.

    ``--ignore-stdin`` добавляется всегда: ``CrocRunner`` открывает stdin
    процесса как PIPE, а croc send с piped stdin переключается в режим
    ``cat file | croc send`` — отправляет stdin вместо файлов и ждёт EOF
    вечно. Приёму флаг ставить нельзя: там stdin нужен для ответов y/n.
    """
    args = [*_global_args(opts), "--ignore-stdin", "send"]
    if opts.transport is not None:
        args.extend(("--transport", opts.transport))
    if opts.hash_algo is not None:
        args.extend(("--hash", opts.hash_algo))
    if opts.exclude:
        args.extend(("--exclude", ",".join(opts.exclude)))
    if opts.transfers is not None:
        args.extend(("--transfers", str(opts.transfers)))
    if opts.store:
        args.append("--store")
    if opts.store_downloads is not None:
        args.extend(("--store-downloads", str(opts.store_downloads)))
    if opts.store_expiration is not None:
        args.extend(("--store-expiration", opts.store_expiration))
    if opts.store_url is not None:
        args.extend(("--store-url", opts.store_url))
    args.extend(paths)
    return args


def build_receive_args(opts: CrocOptions) -> list[str]:
    """Полный хвост argv для приёма: ``croc <результат>``.

    Приём у croc — без подкоманды и БЕЗ позиционной кодовой фразы: код
    передаётся через ``CROC_SECRET`` (см. :func:`croc_secret_env`), при
    установленной переменной croc с пустым позиционным аргументом уходит
    в приём. Send-only поля (``opts.code``, ``transport``, ``hash_algo``,
    ``exclude``, ``transfers`` и ``store*``) игнорируются: у приёма таких флагов
    нет, и croc упал бы на неизвестном флаге.
    """
    args = _global_args(opts)
    if opts.out_dir is not None:
        args.extend(("--out", opts.out_dir))
    return args


def croc_secret_env(
    secret: str | None, base_env: Mapping[str, str]
) -> dict[str, str] | None:
    """Окружение для запуска croc с кодовой фразой в ``CROC_SECRET``.

    Возвращает копию ``base_env`` с добавленным ``CROC_SECRET`` при наличии
    ``secret``; ``None`` — если фразы нет (отправка без своего кода: croc
    сгенерирует её сам), чтобы ``create_subprocess_exec`` унаследовал
    окружение родителя без изменений.
    """
    if secret is None:
        return None
    return {**base_env, "CROC_SECRET": secret}
