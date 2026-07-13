"""Переиспользуемая форма полей ``CrocOptions``.

Используется ``SendPanel`` (опции конкретной отправки) и ``SettingsPanel``
(редактирование профиля). Форма не знает, откуда берутся значения и куда
уходят — только ``apply_options()`` / ``read_options()``. Пустые текстовые
поля нормализуются в ``None`` (контракт ``pycroc.core.options``).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Checkbox, Input

from pycroc.core.options import CrocOptions, normalize_text


class OptionsForm(Vertical):
    """Поля всех опций croc; id полей — ``opt-*``."""

    DEFAULT_CSS = """
    OptionsForm {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Input(placeholder="--code: своя кодовая фраза", id="opt-code")
        yield Input(placeholder="--pass: пароль relay или файл с ним", id="opt-pass")
        yield Input(placeholder="--relay host:port", id="opt-relay")
        yield Input(placeholder="--relay6 [ipv6]:port", id="opt-relay6")
        yield Input(placeholder="--socks5 host:port", id="opt-socks5")
        yield Input(placeholder="--connect http-proxy", id="opt-connect")
        yield Input(placeholder="--throttleUpload, напр. 500k", id="opt-throttle")
        yield Input(placeholder="--curve: P-256 | P-348 | P-521 | SIEC", id="opt-curve")
        yield Input(placeholder="--hash: xxhash | imohash", id="opt-hash")
        yield Input(placeholder="--exclude: шаблоны через запятую", id="opt-exclude")
        yield Input(placeholder="--transfers: число потоков", id="opt-transfers")
        yield Checkbox("--no-compress", id="opt-no-compress")
        yield Checkbox("--ask", id="opt-ask")
        yield Checkbox("--yes (авто-подтверждение)", value=True, id="opt-auto-accept")

    def apply_options(self, options: CrocOptions) -> None:
        """Заполняет поля значениями ``options``."""

        def set_text(input_id: str, value: str | None) -> None:
            self.query_one(f"#{input_id}", Input).value = value or ""

        set_text("opt-code", options.code)
        set_text("opt-pass", options.pass_)
        set_text("opt-relay", options.relay)
        set_text("opt-relay6", options.relay6)
        set_text("opt-socks5", options.socks5)
        set_text("opt-connect", options.connect)
        set_text("opt-throttle", options.throttle_upload)
        set_text("opt-curve", options.curve)
        set_text("opt-hash", options.hash_algo)
        set_text("opt-exclude", ",".join(options.exclude) if options.exclude else None)
        set_text(
            "opt-transfers",
            str(options.transfers) if options.transfers is not None else None,
        )
        self.query_one("#opt-no-compress", Checkbox).value = options.no_compress
        self.query_one("#opt-ask", Checkbox).value = options.ask
        self.query_one("#opt-auto-accept", Checkbox).value = options.auto_accept

    def read_options(self) -> CrocOptions:
        """Собирает ``CrocOptions`` из текущих значений полей."""

        def text(input_id: str) -> str | None:
            return normalize_text(self.query_one(f"#{input_id}", Input).value)

        exclude_text = text("opt-exclude")
        exclude = (
            tuple(part for part in (p.strip() for p in exclude_text.split(",")) if part)
            if exclude_text
            else ()
        )
        transfers_text = text("opt-transfers")
        transfers = int(transfers_text) if transfers_text and transfers_text.isdigit() else None
        return CrocOptions(
            code=text("opt-code"),
            pass_=text("opt-pass"),
            relay=text("opt-relay"),
            relay6=text("opt-relay6"),
            socks5=text("opt-socks5"),
            connect=text("opt-connect"),
            throttle_upload=text("opt-throttle"),
            curve=text("opt-curve"),
            hash_algo=text("opt-hash"),
            no_compress=self.query_one("#opt-no-compress", Checkbox).value,
            ask=self.query_one("#opt-ask", Checkbox).value,
            auto_accept=self.query_one("#opt-auto-accept", Checkbox).value,
            exclude=exclude,
            transfers=transfers,
        )
