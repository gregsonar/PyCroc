# GUI-клиент для croc на Python + Textual

*(Если план предназначен для AI-агента — Claude Code, ralphex и т.п. — можно переключиться на английский по вашему запросу. По умолчанию остаёмся на русском.)*

## Overview

Проект: настольное TUI-приложение (`pycroc`) на Python + Textual, которое оборачивает
CLI-бинарник [`croc`](https://github.com/schollz/croc) (Go, subprocess) и даёт полноценный
интерфейс отправки/приёма файлов вместо голого терминала: формы вместо флагов, живой прогресс-бар,
QR-код кодовой фразы, история передач, избранные коды/пути и профили настроек (relay, шифрование,
socks5-прокси и т.д.).

croc не имеет Python-биндингов — единственный практичный способ интеграции — вызывать
установленный бинарник `croc` через `asyncio.subprocess` и парсить его вывод. Это ключевое
архитектурное решение, зафиксированное ниже.

После завершения работы пользователь увидит:
- Вкладку **Send**: выбор файлов/папок, настройка опций (пароль, relay, кривая шифрования,
  количество портов, socks5-прокси, throttle), кнопка отправки, живой прогресс-бар и QR-код
  с кодовой фразой для сканирования на другом устройстве.
- Вкладку **Receive**: поле ввода кодовой фразы (с автодополнением из истории/избранного),
  выбор папки назначения, прогресс-бар, модальное окно при конфликте перезаписи файла.
- Вкладку **History**: таблица всех прошлых передач (файл, направление, размер, дата, статус)
  с возможностью повторить передачу или скопировать код.
- Вкладку **Settings**: управление профилями (свой relay/pass/curve/socks5), выбор активного
  профиля, путь к бинарнику `croc` с проверкой версии.
- Приложение с CLI-скриптом `pycroc`, устанавливаемое через `pip install`.

**Out of scope:**
- Собственная реализация протокола croc на Python (принято решение — только subprocess-обёртка).
- Разработка/хостинг собственного публичного relay-сервера (только поддержка *подключения* к
  своему relay через существующие флаги `--relay`/`--relay6`/`--pass`).
- Мобильные и веб-версии интерфейса.
- Синхронизация истории/профилей между несколькими машинами (только локальное хранение).
- Поддержка версий croc старше v9 (ориентируемся на актуальный CLI, см. Context).

## Context (from discovery)

Файлового доступа к существующему проекту нет — это greenfield-проект, создаётся с нуля.
Ниже — факты о `croc`, подтверждённые поиском актуальной документации (не из памяти модели,
т.к. флаги менялись между мажорными версиями v6–v10):

- **Формат команд**: `croc send [опции] <файл...>` для отправки; получение — позиционный
  аргумент без подкоманды: `croc [опции] <код-фраза>`; `croc relay [опции]` — поднять свой relay.
- **Разделение потоков вывода**: весь человекочитаемый вывод (прогресс-бар, код, статусы) идёт
  в **stderr**; **stdout** используется только при `--stdout` для передачи содержимого файла —
  это важно: наш парсер должен читать именно stderr, не stdout.
- **Ключевые глобальные флаги** (актуальны для v9/v10, `send` дополнительно имеет `--qr`/`--qrcode`,
  `--exclude`, `--transfers`, `--zip`):
  `--yes`, `--stdout`, `--no-compress`, `--ask`, `--relay <addr>`, `--relay6 <addr>`,
  `--out <dir>`, `--pass <value>`, `--socks5 <addr>`, `--connect <http-proxy>`,
  `--throttleUpload <rate>`, `--curve {P-256,P-348,P-521,SIEC}`, `--hash {xxhash,imohash}`,
  `--classic`, `--remember`, `--debug`, `--code <phrase>` (только при `send`).
- **Формат строки кода**: `Code is: slow-tomato-almond`.
- **Формат строки начала отправки**: `Sending 'file.txt' (116 B)`.
- **Формат строки прогресса** (пример из реального вывода):
  `Receiving (<-192.168.225.37:9009) file.txt 100% |████████████████████| (116/116 B, 32.966 kB/s) [0s:0s] ✔️`
- **Запрос подтверждения на приёме** (если не указан `--yes`): `Accept 'file.txt' (116 B)? (y/n)`.
- croc сам умеет рисовать QR-код в терминале (`--qr`), но это ASCII-арт, рассчитанный на
  живой TTY, а не на программный парсинг — решение: генерировать свой QR из кодовой фразы через
  библиотеку `qrcode`, не полагаясь на вывод `--qr` (см. Design decisions).

## Development Approach

- Подход: **код сначала, затем тесты** — но каждая задача, меняющая поведение, обязана
  включать тесты до перехода к следующей задаче (это требование не зависит от порядка написания).
- Каждая задача выполняется полностью, прежде чем переходить к следующей.
- **КРИТИЧНО: все тесты должны проходить перед началом следующей задачи.**
- Обратная совместимость не актуальна (новый проект), но CLI-опции croc должны быть версионно
  устойчивы: парсер вывода не должен падать на неизвестной строке — только игнорировать её с
  debug-логом (croc меняет формат вывода между версиями).
- После каждого изменения запускать: `ruff check .`, `mypy src`, `pytest -q`.

## Testing Strategy

- **Unit-тесты**: регэкспы парсера stderr на корпусе реальных зафиксированных строк вывода
  (прогресс, код, начало отправки, запрос подтверждения, ошибки); построение argv из
  `CrocOptions`; CRUD профилей конфигурации; CRUD истории передач.
- **Integration-тесты**: `CrocRunner` против поддельного исполняемого файла `croc`
  (Python-скрипт-заглушка, печатающий заранее заданные строки в stderr с задержками) —
  это позволяет тестировать асинхронное чтение потока и порядок событий без реальной сети
  и без второго пира.
- **Наиболее ценный тест**: корректность извлечения процента и скорости из строки прогресса
  на нескольких вариантах реального вывода croc (разные версии/направления/юниты размера).
  Это самый опасный failure mode — при ошибке парсинга UI просто "зависает" без прогресса,
  не падая и не показывая ошибку, и пользователь не поймёт, идёт передача или нет.
- **Round-trip тест**: `build_args(options)` → `argv` → повторный разбор в `CrocOptions` даёт
  тот же объект — защищает от рассинхронизации при обновлении флагов croc.
- **Widget-тесты**: `textual.testing` / `App.run_test()` (Pilot) — эмуляция ввода кода,
  нажатия Send, проверка обновления прогресс-бара по синтетическим событиям от
  подставного (mock) `CrocRunner`.

## Solution Overview

**Architecture:**

1. `pycroc.core.options` — `CrocOptions` (dataclass) + `build_send_args()` /
   `build_receive_args()`, переводящие опции в список аргументов `croc`.
2. `pycroc.core.parser` — чистые функции разбора строк stderr в события
   (`CodeEvent`, `ProgressEvent`, `TransferStartEvent`, `AcceptPromptEvent`, `ErrorEvent`,
   `DoneEvent`). Не знает про subprocess и Textual — только `str -> Event | None`.
3. `pycroc.core.runner` — `CrocRunner`: запускает `croc` через
   `asyncio.create_subprocess_exec`, построчно читает stderr, прогоняет через `parser`,
   публикует события через `asyncio.Queue` (или callback), умеет отправлять `y\n`/`n\n`
   в stdin при `AcceptPromptEvent`, умеет отменять передачу (`process.terminate()`).
4. `pycroc.storage.history` — `HistoryRepository` поверх SQLite (`sqlite3`, вызовы через
   `asyncio.to_thread`), CRUD записей передач.
5. `pycroc.storage.config` — `ConfigStore` поверх TOML (`tomlkit`) в
   `platformdirs.user_config_dir("pycroc")`: профили опций + активный профиль + путь к бинарнику.
6. `pycroc.ui.app` — `PyCrocApp(App)` с `TabbedContent` (Send/Receive/History/Settings),
   владеет единственным экземпляром `CrocRunner`, `HistoryRepository`, `ConfigStore`,
   инжектирует их в дочерние виджеты (dependency injection через конструкторы, не глобальные
   синглтоны — упрощает тестирование виджетов с mock-зависимостями).
7. `pycroc.ui.widgets.*` — `SendPanel`, `ReceivePanel`, `HistoryPanel`, `SettingsPanel`,
   `QrCodeWidget`, `OverwriteConflictModal`.

**Key data flow / event dispatch:**

```
[SendPanel]
  user picks files, sets options, presses "Send"
    -> SendPanel.action_send()
    -> options = CrocOptions.from_form(self.query(...))
    -> self.run_worker(self._run_send(files, options), exclusive=True)

[SendPanel._run_send] (async worker)
    -> async for event in self.app.croc_runner.send(files, options):
         match event:
           CodeEvent(code)        -> self.code = code (reactive) -> QrCodeWidget updates
           TransferStartEvent(fn) -> self.status = f"Отправка {fn}..."
           ProgressEvent(pct, rate) -> self.progress_bar.update(progress=pct); self.rate_label.update(rate)
           DoneEvent(fn)          -> self.status = "Готово"; history.add(...)
           ErrorEvent(msg)        -> self.app.notify(msg, severity="error")
    -> on completion (success or error): history_repo.add(record); HistoryPanel.refresh()

[CrocRunner.send] (async generator)
    -> proc = await asyncio.create_subprocess_exec("croc", "send", *build_send_args(opts), *files,
                                                     stdin=PIPE, stdout=PIPE, stderr=PIPE)
    -> async for raw_line in proc.stderr:
         event = parse_line(raw_line.decode())
         if isinstance(event, AcceptPromptEvent) and opts.auto_accept:
             proc.stdin.write(b"y\n"); continue
         if event is not None:
             yield event
    -> await proc.wait(); yield DoneEvent(...) if proc.returncode == 0 else ErrorEvent(...)
```

**Design decisions:**
- **Subprocess, не реализация протокола**: croc — сложный криптографический протокол (PAKE,
  AES-256, релей на WebSocket). Переизобретение на Python — риск багов безопасности и месяцы
  работы ради минимального выигрыша. Обёртка над официальным бинарником — стандартный подход
  для GUI-клиентов таких CLI-утилит (аналогично GUI-обёрткам над rsync/ffmpeg).
- **Свой QR-код вместо `--qr` croc**: ASCII-QR croc рассчитан на прямой вывод в TTY и плохо
  поддаётся программному захвату через subprocess (спецсимволы, привязка к ширине терминала
  реального процесса). Генерация QR из уже полученной кодовой фразы через библиотеку `qrcode`
  даёт полный контроль над рендерингом внутри Textual-виджета.
- **SQLite для истории, TOML для конфигурации**: история — растущий набор записей с фильтрацией
  и сортировкой → реляционное хранилище оправдано даже для локального однопользовательского
  приложения. Конфигурация — короткий, редактируемый вручную набор профилей → TOML читаем и
  редактируется руками при необходимости.
- **Dependency injection вместо глобальных синглтонов**: `CrocRunner`/`HistoryRepository`/
  `ConfigStore` передаются виджетам явно (через конструктор или `self.app` с типизацией) —
  позволяет в тестах подставлять fake-реализации без патчинга модулей.
- **Парсер как чистые функции**: `parser.py` не содержит asyncio/subprocess — тестируется
  без единого mock, просто строка на входе, событие на выходе.

## Technical Details

### `CrocOptions` и построение аргументов CLI

**Окружение:** используется `SendPanel`/`ReceivePanel` для сборки формы в аргументы,
и `CrocRunner` — для передачи в `asyncio.create_subprocess_exec`.

```python
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class CrocOptions:
    code: str | None = None
    pass_: str | None = None          # --pass
    relay: str | None = None          # --relay
    relay6: str | None = None         # --relay6
    out_dir: str | None = None        # --out (только receive)
    socks5: str | None = None         # --socks5
    connect: str | None = None        # --connect (http-proxy)
    throttle_upload: str | None = None  # --throttleUpload, напр. "500k"
    curve: str | None = None          # P-256 | P-348 | P-521 | SIEC
    hash_algo: str | None = None      # xxhash | imohash
    no_compress: bool = False
    ask: bool = False
    auto_accept: bool = True          # управляет --yes И реакцией на AcceptPromptEvent
    exclude: tuple[str, ...] = field(default_factory=tuple)
    transfers: int | None = None

def build_send_args(opts: CrocOptions) -> list[str]: ...
def build_receive_args(opts: CrocOptions) -> list[str]: ...
```

Граничные случаи:
- `pass_` может быть путём к файлу (croc поддерживает `--pass FILEWITHPASSWORD`) — GUI не
  должен пытаться валидировать формат, просто передавать строку как есть.
- `exclude` — croc принимает одну строку с значениями через запятую, а не несколько флагов;
  `build_send_args` обязан сделать `",".join(opts.exclude)`, а не повторять флаг.
- Пустая строка после `strip()` в любом текстовом поле формы должна трактоваться как `None`,
  иначе в `argv` попадёт `--relay ""`.

**Тест-кейсы:**
- `build_send_args(CrocOptions(exclude=("node_modules", ".git")))` содержит ровно один
  `--exclude` со значением `"node_modules,.git"`.
- `build_receive_args(CrocOptions(auto_accept=True))` содержит `--yes`.
- Round-trip: опции со всеми полями заполненными → argv → повторный парсинг через
  `argparse`-эквивалент в тестовом хелпере → совпадает с исходным объектом.

### Парсер строк вывода (`pycroc.core.parser`)

**Окружение:** вызывается из `CrocRunner` построчно на каждой строке stderr; не имеет
состояния между вызовами (кроме, возможно, текущего имени файла для продолжения прогресса).

```python
import re
from dataclasses import dataclass

CODE_RE = re.compile(r"^Code is:\s*(?P<code>\S+)")
SENDING_INIT_RE = re.compile(r"^Sending '(?P<name>.+)' \((?P<size>[\d.]+\s?\w+)\)")
ACCEPT_PROMPT_RE = re.compile(r"^Accept '(?P<name>.+)' \((?P<size>[\d.]+\s?\w+)\)\? \(y/n\)")
PROGRESS_RE = re.compile(
    r"(?P<direction>Sending|Receiving)\s+\([^)]*\)\s+"
    r"(?P<filename>\S+)\s+(?P<percent>\d+)%\s*\|[^|]*\|\s*"
    r"\((?P<done>[\d.]+)/(?P<total>[\d.]+)\s*(?P<unit>\w+),\s*"
    r"(?P<rate>[\d.]+)\s*(?P<rate_unit>[\w/]+)\)\s*\[(?P<elapsed>[\w:]+)\]"
)

@dataclass(frozen=True)
class ProgressEvent:
    direction: str
    filename: str
    percent: int
    rate: str

def parse_line(line: str) -> "Event | None":
    """Пробует по очереди все известные паттерны; возвращает None для нераспознанной строки
    (не бросает исключение — формат вывода croc меняется между версиями)."""
    ...
```

Граничные случаи (специфичные для croc, не общие "handle empty input"):
- Прогресс-бар печатается через `\r` (перезапись строки), а не `\n` — при построчном чтении
  из `proc.stderr` через `asyncio.StreamReader.readline()` это может слипаться в одну "строку"
  без `\n` до финального обновления; нужно читать по символам/буферизовать до `\r` **или** `\n`,
  а не полагаться на `readline()` "из коробки" — это отдельный подзадача в `CrocRunner`.
  Task 3 обязан включить тест на этот кейс с фикстурой сырых байт, где прогресс разделён `\r`.
  - Обновление 2025: в v9/v10 отдельные прогресс-строки для многофайловой передачи выводятся
    последовательно по каждому файлу — парсер должен матчить `filename`, а не предполагать
    единственный файл на сессию.
- Финальная галочка `✔️` в конце строки прогресса — эмодзи, регэксп не должен требовать его
  наличия (может не рендериться в некоторых локалях/версиях).
- Ошибки croc не имеют единого префикса (`Error`, `error`, `failed to ...` встречаются в разных
  версиях) — парсер должен иметь fallback: если процесс завершился с ненулевым кодом возврата
  и ни одна строка не распозналась как явная ошибка, `CrocRunner` сам формирует `ErrorEvent`
  из последних N нераспознанных строк stderr.

**Тест-кейсы:**
- `parse_line("Code is: slow-tomato-almond")` → `CodeEvent(code="slow-tomato-almond")`.
- `parse_line("Receiving (<-192.168.225.37:9009) file.txt 100% |████████████████████| (116/116 B, 32.966 kB/s) [0s:0s] ✔️")`
  → `ProgressEvent(direction="Receiving", filename="file.txt", percent=100, rate="32.966 kB/s")`.
- `parse_line("some future unknown croc output format")` → `None` (не исключение).
- Буфер, где прогресс разбит на несколько `\r`-обновлений подряд без `\n` — `CrocRunner`
  корректно выдаёт последовательность `ProgressEvent` с растущим `percent`, не теряя финальное
  100%-обновление.

### `CrocRunner` (async subprocess-обёртка)

**Окружение:** единственный держатель subprocess-состояния; создаётся один раз в
`PyCrocApp.on_mount`, инжектируется в `SendPanel`/`ReceivePanel`. Вызывающая сторона — Textual
worker (`self.run_worker(...)`), т.к. Textual сам работает на asyncio-луп и не требует отдельного
потока для async-генераторов.

```python
class CrocRunner:
    def __init__(self, binary_path: str = "croc") -> None: ...

    async def send(
        self, paths: list[str], options: CrocOptions
    ) -> AsyncIterator[Event]: ...

    async def receive(
        self, code: str, options: CrocOptions
    ) -> AsyncIterator[Event]: ...

    async def cancel(self) -> None:
        """Посылает SIGTERM текущему процессу; croc должен корректно закрыть соединение с relay."""
        ...

    async def check_binary(self) -> str:
        """Запускает `croc --version`, возвращает версию или бросает CrocNotFoundError."""
        ...
```

Граничные случаи:
- Бинарник croc может отсутствовать в `PATH` — `check_binary()` вызывается при старте
  приложения и на входе в Settings; отсутствие не должно крашить приложение, только показывать
  предупреждение и блокировать вкладки Send/Receive.
- Отмена передачи должна не просто убить процесс, но и корректно освободить relay-канал —
  croc сам это делает при получении SIGTERM/SIGINT; `proc.terminate()` (SIGTERM) предпочтительнее
  `proc.kill()` (SIGKILL) именно по этой причине.
- Параллельный запуск двух send/receive из одного приложения запрещён на уровне `CrocRunner`
  (croc — один канал на процесс): второй вызов `send`/`receive` при активном процессе должен
  бросать `TransferInProgressError`, а не тихо перезаписывать `self._proc`.

**Тест-кейсы:**
- Подставной `croc`-скрипт печатает валидную последовательность строк с задержками —
  `CrocRunner.send()` отдаёт события в правильном порядке: `TransferStartEvent`, `CodeEvent`,
  несколько `ProgressEvent` с растущим percent, `DoneEvent`.
- Подставной скрипт завершается с кодом 1 и печатает нераспознаваемую ошибку —
  `CrocRunner.send()` отдаёт `ErrorEvent` с текстом последних строк stderr.
- Вызов `cancel()` во время активной передачи завершает subprocess и генератор завершается
  без исключения (или с чётко определённым `CancelledTransferEvent`).
- `check_binary()` с несуществующим путём бросает `CrocNotFoundError`.

### `HistoryRepository` (SQLite)

**Окружение:** используется `SendPanel`/`ReceivePanel` по завершении передачи (запись) и
`HistoryPanel` (чтение/поиск/удаление).

```python
@dataclass(frozen=True, slots=True)
class TransferRecord:
    id: int | None
    direction: Literal["send", "receive"]
    filename: str
    size_bytes: int | None
    code: str
    status: Literal["done", "error", "cancelled"]
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None

class HistoryRepository:
    async def add(self, record: TransferRecord) -> int: ...
    async def list(self, limit: int = 200, query: str | None = None) -> list[TransferRecord]: ...
    async def delete(self, record_id: int) -> None: ...
```

Граничные случаи: путь к БД должен создаваться лениво (`CREATE TABLE IF NOT EXISTS`) при первом
обращении, а не в конструкторе — иначе тесты с временными файлами БД усложняются; конкурентная
запись из send и receive одновременно невозможна по построению (`CrocRunner` разрешает только
одну активную передачу), поэтому блокировки SQLite можно не оборачивать в retry-логику сверх
стандартного `sqlite3` timeout.

**Тест-кейсы:**
- `add()` + `list()` возвращает добавленную запись с корректно восстановленными датами.
- `list(query="report.pdf")` фильтрует только записи с этим именем файла (регистронезависимо).
- `delete()` несуществующего id не бросает исключение (idempotent).

### `ConfigStore` и профили (TOML)

**Окружение:** используется `SettingsPanel` для CRUD профилей и `SendPanel`/`ReceivePanel`
для получения опций активного профиля как значений формы по умолчанию.

```python
@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    options: CrocOptions

class ConfigStore:
    def load_profiles(self) -> dict[str, Profile]: ...
    def save_profile(self, profile: Profile) -> None: ...
    def delete_profile(self, name: str) -> None: ...
    def get_active_profile_name(self) -> str: ...
    def set_active_profile_name(self, name: str) -> None: ...
    def get_binary_path(self) -> str: ...
```

Граничные случаи: профиль `"default"` не может быть удалён (fallback, если пользователь удалит
все остальные); при повреждённом/невалидном TOML-файле — не крашить приложение, а откатиться на
профиль по умолчанию в памяти и показать предупреждение с путём к файлу для ручного исправления.

**Тест-кейсы:**
- `save_profile` + `load_profiles` восстанавливает все поля `CrocOptions`, включая `exclude`
  (кортеж строк корректно сериализуется в TOML-массив и обратно).
- Попытка `delete_profile("default")` бросает `ValueError` и не удаляет файл.
- Повреждённый TOML-файл → `load_profiles()` возвращает только `{"default": Profile(...)}`
  без исключения.

### UI-виджеты (`SendPanel`, `ReceivePanel`, `HistoryPanel`, `QrCodeWidget`, `OverwriteConflictModal`)

**Окружение:** дочерние виджеты `PyCrocApp`, получают `CrocRunner`/`HistoryRepository`/
`ConfigStore` через `self.app` (типизированный `PyCrocApp`, не `App` — для mypy) либо явные
конструкторные параметры для тестируемости в изоляции.

- `SendPanel`: выбор файлов через кастомный виджет на базе `DirectoryTree` с чекбоксами
  (Textual не имеет нативного multi-select file picker), форма опций, `ProgressBar`
  (встроенный виджет Textual), `QrCodeWidget` (рендерит ASCII-QR из `qrcode.QRCode` внутри
  `Static`, обновляется реактивно при получении `CodeEvent`).
- `ReceivePanel`: поле ввода кода с автодополнением (`Input` + кастомный `SuggestionList`
  на основе истории/избранного), выбор папки назначения, тот же `ProgressBar`.
- `OverwriteConflictModal`: `ModalScreen`, показывается при `AcceptPromptEvent`, если
  `opts.auto_accept=False` — пользователь явно подтверждает/отклоняет через кнопки, ответ
  пишется в `proc.stdin`.
- `HistoryPanel`: `DataTable` + `Input` для поиска, привязан к `HistoryRepository.list()`.

Граничные случаи: длинные списки файлов (сотни) в `SendPanel` не должны блокировать UI при
построении дерева — обход файловой системы для `DirectoryTree` должен выполняться асинхронно
(Textual уже это делает по умолчанию, но кастомный multi-select слой поверх должен сохранить
эту асинхронность, а не собирать список файлов синхронно в `on_mount`).

**Тест-кейсы:**
- Pilot-тест: ввод кода в `ReceivePanel`, нажатие "Receive" вызывает `CrocRunner.receive`
  с этим кодом (проверка через mock).
- Pilot-тест: получение синтетического `ProgressEvent(percent=42)` через тестовый канал
  обновляет `ProgressBar.progress` до 42.
- Pilot-тест: `AcceptPromptEvent` при `auto_accept=False` открывает `OverwriteConflictModal`,
  выбор "Нет" отправляет `b"n\n"` в stdin подставного процесса.

## What Goes Where

- **Implementation Steps** (`[ ]`): код, тесты, документация — всё проверяется локально.
- **Post-Completion**: ручная проверка на реальном croc между двумя машинами (сеть, relay).

---

## Implementation Steps

### Task 1: Скелет проекта

**Files:**
- Create: `pyproject.toml`, `src/pycroc/__init__.py`, `src/pycroc/py.typed`
- Create: `.pre-commit-config.yaml`, `ruff.toml` (или секция в `pyproject.toml`), `pytest.ini`
- Create: `README.md` (заглушка), `.gitignore`

- [x] настроить `pyproject.toml` (hatchling backend, зависимости: `textual`, `qrcode`,
      `tomlkit`, `platformdirs`; dev-зависимости: `pytest`, `pytest-asyncio`, `ruff`, `mypy`)
- [x] добавить entry point `pycroc = pycroc.ui.app:main` в `[project.scripts]`
- [x] настроить `ruff` (line-length, правила) и `mypy --strict` для `src/`
- [x] добавить `pytest-asyncio` в режиме `asyncio_mode = "auto"`
- [x] запустить `ruff check .` и `mypy src` — оба должны проходить на пустом каркасе

*Note: реальный `croc`-бинарник в CI недоступен — все интеграционные тесты используют
подставной скрипт-заглушку (см. Task 3), а не настоящий croc.*

### Task 2: `CrocOptions` и построение аргументов CLI

**Files:**
- Create: `src/pycroc/core/options.py`
- Create: `tests/core/test_options.py`

- [x] реализовать dataclass `CrocOptions` со всеми полями из Technical Details
- [x] реализовать `build_send_args(opts, files) -> list[str]`
- [x] реализовать `build_receive_args(opts, code) -> list[str]`
- [x] обработать пустые строки полей формы как `None` (нормализация на границе UI, не здесь —
      здесь входные данные уже нормализованы; добавить явный docstring с этим контрактом)
- [x] добавить тесты: сборка `--exclude` через запятую, `--yes` при `auto_accept`, round-trip
      через тестовый argparse-парсер
- [x] запустить `pytest tests/core/test_options.py -q` — должен пройти перед Task 3

### Task 3: Парсер строк вывода croc

**Files:**
- Create: `src/pycroc/core/parser.py`
- Create: `src/pycroc/core/events.py` (dataclasses событий)
- Create: `tests/core/test_parser.py`
- Create: `tests/fixtures/croc_stderr_samples.txt` (реальные захваченные строки вывода)

- [x] определить dataclasses событий: `CodeEvent`, `TransferStartEvent`, `ProgressEvent`,
      `AcceptPromptEvent`, `ErrorEvent`, `DoneEvent`
- [x] реализовать regex-паттерны из Technical Details (`CODE_RE`, `SENDING_INIT_RE`,
      `ACCEPT_PROMPT_RE`, `PROGRESS_RE`)
- [x] реализовать `parse_line(line: str) -> Event | None` с fallback на `None` для
      нераспознанных строк (без исключений)
- [x] реализовать буферизацию по `\r`/`\n` в отдельной функции `split_stream_chunks()`
      для корректной обработки перезаписываемых прогресс-строк (см. граничный случай в
      Technical Details) — покрыть тестом с сырыми байтами, где нет `\n` до конца передачи
- [x] добавить тесты на все примеры из `croc_stderr_samples.txt`, включая мультифайловую
      передачу (несколько разных `filename` подряд) и строку с ошибкой
- [x] запустить `pytest tests/core/test_parser.py -q` — критический гейт, самый важный тест
      в проекте (см. Testing Strategy) — должен пройти перед Task 4

### Task 4: `CrocRunner` — subprocess-обёртка

**Files:**
- Create: `src/pycroc/core/runner.py`
- Create: `src/pycroc/core/exceptions.py` (`CrocNotFoundError`, `TransferInProgressError`)
- Create: `tests/core/test_runner.py`
- Create: `tests/fixtures/fake_croc.py` (Python-скрипт-заглушка, эмулирующий поведение croc)

- [x] реализовать `fake_croc.py`, принимающий аргументы командной строки и печатающий в
      stderr заранее заданный сценарий строк с настраиваемыми задержками (через env-переменную
      с путём к JSON-сценарию)
- [x] реализовать `CrocRunner.check_binary()` (вызов `<binary> --version`, парсинг версии)
- [x] реализовать `CrocRunner.send()` как async-генератор поверх `asyncio.create_subprocess_exec`
- [x] реализовать `CrocRunner.receive()` аналогично
- [x] реализовать автоответ `y\n`/`n\n` в stdin на `AcceptPromptEvent` согласно `opts.auto_accept`
- [x] реализовать `CrocRunner.cancel()` (`proc.terminate()` с таймаутом, затем `kill()`)
- [x] реализовать защиту от параллельного запуска (`TransferInProgressError`)
- [x] добавить тесты: успешный сценарий, сценарий с ошибкой, отмена во время передачи,
      попытка параллельного запуска, отсутствие бинарника
- [x] запустить `pytest tests/core/test_runner.py -q` — должен пройти перед Task 5

### Task 5: Хранилище истории (SQLite)

**Files:**
- Create: `src/pycroc/storage/history.py`
- Create: `tests/storage/test_history.py`

- [x] определить dataclass `TransferRecord`
- [x] реализовать `HistoryRepository` с ленивой инициализацией схемы (`CREATE TABLE IF NOT EXISTS`)
- [x] реализовать `add`, `list` (с фильтром по `query`), `delete` через `asyncio.to_thread`
      поверх `sqlite3`
- [x] добавить тесты: add+list, поиск по подстроке имени файла, idempotent delete
- [x] запустить `pytest tests/storage/test_history.py -q`

### Task 6: Хранилище конфигурации и профилей (TOML)

**Files:**
- Create: `src/pycroc/storage/config.py`
- Create: `tests/storage/test_config.py`

- [x] реализовать `Profile` dataclass и сериализацию `CrocOptions <-> TOML` (включая
      `exclude: tuple[str, ...] <-> TOML-массив`)
- [x] реализовать `ConfigStore` с путём через `platformdirs.user_config_dir("pycroc")`
- [x] реализовать защиту профиля `"default"` от удаления
- [x] реализовать fallback на профиль по умолчанию при повреждённом файле конфигурации
- [x] добавить тесты: save+load round-trip, защита `default`, восстановление после
      повреждённого TOML
- [x] запустить `pytest tests/storage/test_config.py -q`

### Task 7: Каркас Textual-приложения

**Files:**
- Create: `src/pycroc/ui/app.py`
- Create: `src/pycroc/ui/app.tcss`
- Create: `tests/ui/test_app.py`

- [x] реализовать `PyCrocApp(App)` с `TabbedContent` из четырёх пустых вкладок-заглушек
- [x] в `on_mount` создать единственные экземпляры `CrocRunner`, `HistoryRepository`,
      `ConfigStore`, вызвать `check_binary()` и показать предупреждение через `self.notify()`
      при отсутствии croc (без падения приложения)
- [x] добавить базовую тему `app.tcss` (согласно `frontend-design`, если стилизация UI
      выходит за рамки стандартных виджетов Textual)
- [x] добавить Pilot-тест: приложение стартует, четыре вкладки видны, `pycroc` без
      установленного `croc` показывает предупреждение, а не падает
- [x] запустить `pytest tests/ui/test_app.py -q`

### Task 8: `QrCodeWidget`

**Files:**
- Create: `src/pycroc/ui/widgets/qr_code.py`
- Create: `tests/ui/widgets/test_qr_code.py`

- [x] реализовать генерацию ASCII-QR из строки кода через `qrcode.QRCode` + `print_ascii`
      в буфер, рендер как `Static` содержимое
- [x] сделать `code` реактивным свойством, обновляющим QR при изменении
- [x] добавить тест: установка `widget.code = "slow-tomato-almond"` меняет отрендеренный текст
- [x] запустить `pytest tests/ui/widgets/test_qr_code.py -q`

### Task 9: `SendPanel`

**Files:**
- Create: `src/pycroc/ui/widgets/send_panel.py`
- Create: `src/pycroc/ui/widgets/file_picker.py` (multi-select на базе `DirectoryTree`)
- Create: `tests/ui/widgets/test_send_panel.py`

- [x] реализовать `file_picker.py`: `DirectoryTree` с чекбоксами, метод `selected_paths()`
- [x] реализовать форму опций `SendPanel` (поля, соответствующие `CrocOptions`), с значениями
      по умолчанию из активного профиля `ConfigStore`
- [x] реализовать `action_send()`: сборка `CrocOptions`, запуск `run_worker` с
      `croc_runner.send(...)`, обработка событий (`CodeEvent` -> `QrCodeWidget`,
      `ProgressEvent` -> `ProgressBar`, `DoneEvent`/`ErrorEvent` -> запись в `HistoryRepository`)
- [x] реализовать кнопку отмены передачи (`croc_runner.cancel()`)
- [x] добавить Pilot-тесты: mock `CrocRunner`, проверка обновления прогресс-бара и QR по
      синтетическим событиям, проверка вызова `HistoryRepository.add` по завершении
- [x] запустить `pytest tests/ui/widgets/test_send_panel.py -q`

### Task 10: `ReceivePanel` и `OverwriteConflictModal`

**Files:**
- Create: `src/pycroc/ui/widgets/receive_panel.py`
- Create: `src/pycroc/ui/widgets/overwrite_modal.py`
- Create: `tests/ui/widgets/test_receive_panel.py`

- [x] реализовать поле ввода кода с автодополнением из истории + избранного
      *(решение 2026-07-13: только из истории — хранилище избранного планом не предусмотрено)*
- [x] реализовать выбор папки назначения (`--out`)
- [x] реализовать `action_receive()` аналогично `SendPanel.action_send()`
- [x] реализовать `OverwriteConflictModal` (`ModalScreen`), открывается на
      `AcceptPromptEvent` при `auto_accept=False`, пишет ответ в stdin активного процесса
      через `CrocRunner`
- [x] добавить Pilot-тесты: ввод кода запускает `croc_runner.receive` с этим кодом,
      `AcceptPromptEvent` открывает модалку, выбор "Нет" отправляет `n\n`
- [x] запустить `pytest tests/ui/widgets/test_receive_panel.py -q`

### Task 11: `HistoryPanel`

**Files:**
- Create: `src/pycroc/ui/widgets/history_panel.py`
- Create: `tests/ui/widgets/test_history_panel.py`

- [x] реализовать `DataTable`, привязанный к `HistoryRepository.list()`
- [x] реализовать поле поиска с debounce, вызывающее `list(query=...)`
- [x] реализовать действия по строке: "повторить передачу" (переключает на Send/Receive
      с предзаполненными полями), "скопировать код", "удалить запись"
      *(переключение вкладок — через message `RepeatTransfer`, обрабатывается в Task 13)*
- [x] добавить Pilot-тесты: поиск фильтрует таблицу, "удалить" вызывает
      `HistoryRepository.delete` и убирает строку
- [x] запустить `pytest tests/ui/widgets/test_history_panel.py -q`

### Task 12: `SettingsPanel` и профили

**Files:**
- Create: `src/pycroc/ui/widgets/settings_panel.py`
- Create: `tests/ui/widgets/test_settings_panel.py`

- [x] реализовать список профилей с созданием/редактированием/удалением
      *(форма опций вынесена в переиспользуемый `options_form.py`, общий с SendPanel)*
- [x] реализовать выбор активного профиля (сохраняется через `ConfigStore`)
- [x] реализовать поле пути к бинарнику croc с кнопкой "проверить" (`check_binary()`)
- [x] добавить Pilot-тесты: создание профиля появляется в списке, попытка удалить `default`
      показывает ошибку, а не падает
- [x] запустить `pytest tests/ui/widgets/test_settings_panel.py -q`

### Task 13: Сборка приложения воедино

**Files:**
- Modify: `src/pycroc/ui/app.py`
- Create: `tests/ui/test_integration_flow.py`

- [x] заменить вкладки-заглушки из Task 7 на реальные `SendPanel`/`ReceivePanel`/
      `HistoryPanel`/`SettingsPanel` с инжекцией общих зависимостей
- [x] реализовать сквозные уведомления об ошибках через `self.notify(..., severity="error")`
      на любом `ErrorEvent`, независимо от вкладки
- [x] добавить end-to-end Pilot-тест с mock `CrocRunner`: полный цикл "заполнить форму Send"
      → "получить синтетический DoneEvent" → "открыть History" → "запись видна в таблице"
- [x] запустить `pytest tests/ui -q`

### Task 14: Проверка acceptance-критериев

- [ ] перезапустить все тесты: `pytest -q`
- [ ] запустить `ruff check .`
- [ ] запустить `mypy src --strict`
- [ ] вручную проверить (реальный `croc`, если установлен локально) happy-path отправки
      небольшого файла самому себе через `127.0.0.1` relay или два терминала на одной машине
- [ ] убедиться, что приложение не падает при отсутствии установленного `croc` (показывает
      предупреждение в Settings)

### Task 15: Документация и упаковка

**Files:**
- Modify: `README.md`
- Create: `CHANGELOG.md`

- [ ] описать в `README.md`: установку (`pip install pycroc`), требования (установленный
      бинарник `croc`), скриншот/описание вкладок, горячие клавиши
- [ ] описать формат профилей (`~/.config/pycroc/config.toml`) для ручного редактирования
- [ ] добавить `CHANGELOG.md` с записью `0.1.0 — initial release`
- [ ] тестовых изменений не требуется

### Task 16: Финальный wrap-up

- [ ] зафиксировать в `docs/notes.md` неочевидный готча: буферизация прогресс-строк croc по
      `\r` (см. Task 3) — единственный найденный при планировании неочевидный момент
- [ ] переместить этот план в `docs/plans/completed/pycroc-plan.md`
- [ ] тестовых изменений не требуется

---

## Post-Completion

*Требует ручной проверки или внешних систем — не автоматизируется.*

- Проверка реальной передачи между двумя физически разными машинами (например, между
  рабочим ноутбуком и Orange Pi/Synology NAS в локальной сети) — интеграционные тесты
  используют только подставной `fake_croc.py` и не проверяют настоящий сетевой обмен.
- Проверка передачи через публичный relay croc по умолчанию (интернет, не LAN) — важно для
  сценария "два компьютера в разных сетях".
- Проверка на Windows-терминале (кодировки, поддержка Unicode-прогресс-бара croc,
  поведение `DirectoryTree` с путями Windows) — если целевая аудитория не ограничена Linux.
- Проверка совместимости с версией croc, отличной от той, на которой собирались тестовые
  фикстуры (`croc --version`) — формат вывода менялся между v8/v9/v10.
- Ручная проверка сценария с очень большими файлами (сотни МБ/ГБ) — таймауты, память при
  чтении stderr, корректность отображения скорости передачи на длинных передачах.
- Решить, нужен ли отдельный релиз для PyPI (имя пакета `pycroc` может быть занято —
  проверить на PyPI перед публикацией) или ограничиться установкой из исходников/GitHub.
