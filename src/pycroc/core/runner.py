"""CrocRunner — асинхронная subprocess-обёртка над бинарником croc.

Единственный держатель subprocess-состояния: запускает croc через
``asyncio.create_subprocess_exec``, читает stderr чанками (не ``readline()`` —
croc перерисовывает прогресс через ``\\r``), нарезает поток через
:func:`pycroc.core.parser.split_stream_chunks`, разбирает строки через
:func:`pycroc.core.parser.parse_line` и отдаёт события async-генератором.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from collections import deque
from collections.abc import AsyncIterator

from pycroc.core.events import (
    AcceptPromptEvent,
    DoneEvent,
    ErrorEvent,
    Event,
)
from pycroc.core.exceptions import CrocNotFoundError, TransferInProgressError
from pycroc.core.options import (
    CrocOptions,
    build_receive_args,
    build_send_args,
    croc_secret_env,
)
from pycroc.core.parser import parse_line, split_stream_chunks

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 4096
# Сколько последних нераспознанных строк stderr попадает в fallback-ErrorEvent
_ERROR_TAIL_LINES = 10
_TERMINATE_TIMEOUT = 5.0
_VERSION_RE = re.compile(r"v?\d+\.\d+[\w.\-]*")


class CrocRunner:
    """Запуск croc и трансляция его stderr в события.

    ``binary_path`` — имя/путь бинарника croc; путь с расширением ``.py``
    (fake_croc в интеграционных тестах) запускается через текущий интерпретатор
    Python, т.к. скрипт нельзя exec-нуть напрямую (в т.ч. на Windows).
    """

    def __init__(self, binary_path: str = "croc") -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._running = False
        self._cancel_requested = False
        self.set_binary(binary_path)

    def set_binary(self, binary_path: str) -> None:
        """Смена пути к бинарнику (после проверки в Settings).

        На уже запущенную передачу не влияет — команда читается при старте
        следующего процесса.
        """
        self._binary_path = binary_path
        if binary_path.endswith(".py"):
            self._command: tuple[str, ...] = (sys.executable, binary_path)
        else:
            self._command = (binary_path,)

    async def send(self, paths: list[str], options: CrocOptions) -> AsyncIterator[Event]:
        """Отправка файлов/папок; события по мере разбора stderr.

        Своя кодовая фраза (``options.code``) уходит через ``CROC_SECRET``,
        не через argv — не светится в списке процессов.
        """
        async for event in self._run(
            build_send_args(options, paths), options, secret=options.code
        ):
            yield event

    async def receive(self, code: str, options: CrocOptions) -> AsyncIterator[Event]:
        """Приём по кодовой фразе; события по мере разбора stderr.

        Код передаётся через ``CROC_SECRET`` (не позиционным аргументом).
        """
        async for event in self._run(build_receive_args(options), options, secret=code):
            yield event

    async def cancel(self) -> None:
        """Останавливает активную передачу.

        ``terminate()`` (SIGTERM) предпочтительнее ``kill()``: croc корректно
        освобождает relay-канал; ``kill()`` — только по таймауту. После отмены
        генератор send/receive завершается без ``ErrorEvent`` и без исключения.
        """
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        self._cancel_requested = True
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.wait()

    async def respond(self, accept: bool) -> None:
        """Ответ на ``AcceptPromptEvent`` при ``auto_accept=False``.

        Вызывается UI (модалка подтверждения перезаписи); пишет ``y``/``n``
        в stdin активного процесса. Если процесс уже завершился (гонка с
        кликом пользователя) — тихо ничего не делает.
        """
        await self._write_stdin(b"y\n" if accept else b"n\n")

    async def check_binary(self) -> str:
        """Запускает ``<binary> --version``, возвращает строку версии.

        Бросает :class:`CrocNotFoundError`, если бинарник не найден,
        не запускается или завершился с ошибкой.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._command,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as exc:
            raise CrocNotFoundError(f"не удалось запустить {self._binary_path!r}: {exc}") from exc
        output, _ = await proc.communicate()
        text = output.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            raise CrocNotFoundError(
                f"{self._binary_path!r} --version завершился с кодом {proc.returncode}: {text}"
            )
        match = _VERSION_RE.search(text)
        return match.group(0) if match else text

    async def _run(
        self, argv: list[str], options: CrocOptions, *, secret: str | None
    ) -> AsyncIterator[Event]:
        if self._running:
            raise TransferInProgressError(
                "передача уже выполняется: croc поддерживает один канал на процесс"
            )
        self._running = True
        proc: asyncio.subprocess.Process | None = None
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *self._command,
                    *argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    env=croc_secret_env(secret, os.environ),
                )
            except OSError as exc:
                raise CrocNotFoundError(
                    f"не удалось запустить {self._binary_path!r}: {exc}"
                ) from exc
            self._proc = proc
            self._cancel_requested = False
            assert proc.stderr is not None
            buffer = b""
            recent_unrecognized: deque[str] = deque(maxlen=_ERROR_TAIL_LINES)
            error_seen = False
            eof = False
            while not eof:
                chunk = await proc.stderr.read(_CHUNK_SIZE)
                if chunk:
                    buffer += chunk
                    lines, buffer = split_stream_chunks(buffer)
                    if buffer:
                        # Запрос подтверждения croc печатает без перевода строки
                        # и ждёт stdin — из буфера он сам никогда не "дозреет".
                        tail = buffer.decode("utf-8", errors="replace")
                        if isinstance(parse_line(tail), AcceptPromptEvent):
                            lines.append(tail)
                            buffer = b""
                else:
                    eof = True
                    lines = [buffer.decode("utf-8", errors="replace")] if buffer else []
                    buffer = b""
                for line in lines:
                    event = parse_line(line)
                    if event is None:
                        if line.strip():
                            recent_unrecognized.append(line.strip())
                            logger.debug("нераспознанная строка croc: %r", line)
                        continue
                    if isinstance(event, AcceptPromptEvent) and options.auto_accept:
                        await self._write_stdin(b"y\n")
                        continue
                    if isinstance(event, ErrorEvent):
                        error_seen = True
                    yield event
            returncode = await proc.wait()
            if self._cancel_requested:
                return
            if returncode == 0:
                yield DoneEvent()
            elif not error_seen:
                message = "\n".join(recent_unrecognized) or (
                    f"croc завершился с кодом {returncode}"
                )
                yield ErrorEvent(message=message)
        finally:
            if proc is not None and proc.returncode is None:
                proc.terminate()
            self._proc = None
            self._running = False

    async def _write_stdin(self, data: bytes) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.returncode is not None:
            return
        proc.stdin.write(data)
        await proc.stdin.drain()
