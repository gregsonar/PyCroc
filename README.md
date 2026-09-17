<a id="top"></a>
# PyCroc

**English** · [Русский](#ru)

TUI client for [croc](https://github.com/schollz/croc) built on Python + [Textual](https://github.com/Textualize/textual):
forms instead of CLI flags, a live progress bar, a QR code for the code phrase, transfer history and settings profiles.

> Compatible with croc v11 (verified on v11.5.0): the `--transport` flag
> (auto/derp/relay), stored transfers (`--store`), the new code-output format
> (v11 dropped the `Code is:` line) and a parser resilient to colored output.
> End-to-end transfer over a local relay verified on croc v11.5.0 and v10.2.7;
> output formats v8/v9/v10 are still supported.

## Requirements

- Python 3.11+
- An installed `croc` binary (PyCroc does not install it):
  `choco install croc` / `scoop install croc` / [GitHub releases](https://github.com/schollz/croc/releases).
  You can set the binary path on the Settings tab — it does not have to be on `PATH`.

## Installation

From source (not yet published to PyPI):

```bash
git clone https://github.com/gregsonar/PyCroc.git && cd PyCroc
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install .
```

For development: `pip install -e ".[dev]"`.

## Running

```bash
pycroc
```

Without an installed croc the app shows a warning and disables the Send/Receive
tabs — set the binary path in Settings and click Verify («Проверить»).

## Tabs

- **Send** — a file tree with checkboxes (space or a click on a file selects it),
  the croc options form (relay, password, socks5, throttle, encryption curve,
  transport `--transport` auto/derp/relay, exclude patterns, stored transfer
  `--store` with a download count and lifetime, etc.; an empty field = default
  value), send and cancel buttons. The code phrase and QR code appear right
  after the transfer starts — the code can be copied with a button, the QR
  scanned with a phone.
- **Receive** — a code-phrase field with autocompletion from history (accept a
  suggestion with the right arrow), a destination folder (`--out`), auto-confirm
  of overwrites (`--yes`). With auto-confirm off, an overwrite conflict is shown
  as a Yes/No modal.
- **History** — a table of past transfers (date, file, size, direction, status)
  with search by file name (case-insensitive, including Cyrillic). Per-row
  actions: repeat a transfer (opens Send/Receive with the code prefilled), copy
  the code, delete the record.
- **Settings** — options profiles (create/edit/delete/activate; the `default`
  profile is protected from deletion), the croc binary path with a version
  check. The active profile provides the defaults for Send/Receive.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Tab` / `Shift+Tab` | next / previous field or element |
| `↑` / `↓` | in forms — move between fields; in the tree and tables — move the cursor |
| `Space` | mark a file/folder in the selection tree |
| `Enter` | expand a folder in the tree; select a row |
| `Ctrl+P` | Textual command palette |
| `Ctrl+Q` | quit |

## Configuration and profiles

The config file is hand-editable (comments are preserved on write):

- Windows: `%LOCALAPPDATA%\pycroc\pycroc\config.toml`
- Linux: `~/.config/pycroc/config.toml`
- macOS: `~/Library/Application Support/pycroc/config.toml`

```toml
active_profile = "home"
binary_path = "C:/tools/croc.exe"   # empty / no key = "croc" from PATH

[profiles.home]
relay = "my-relay.example.com:9009" # your own relay (--relay)
pass = "s3cret"                     # relay password or a path to a file with it
curve = "p256"                      # p256 | p384 | p521 | siec | ed25519
transport = "auto"                  # auto | derp | relay (croc v11.3)
hash_algo = "xxhash"                # xxhash | imohash | md5 (send only)
no_compress = false
ask = false
auto_accept = true                  # --yes and auto-answer to the overwrite prompt
exclude = ["node_modules", ".git"]  # send only, comma-joined for croc
transfers = 4                       # send only
store = false                       # stored transfer, send only (croc v11.1)
store_downloads = 1                 # download count for --store
store_expiration = "1d"             # lifetime for --store, e.g. "3d"
```

A corrupted file does not crash the app: the default profile is used and a
warning with the file path is shown in the UI.

## Transfer history and security

History is stored in SQLite:

- Windows: `%LOCALAPPDATA%\pycroc\pycroc\history.db`
- Linux: `~/.local/share/pycroc/history.db`

The code phrase is passed to croc via the `CROC_SECRET` environment variable
rather than command-line arguments — so it is not visible in the OS process list.

⚠️ **Code phrases are stored in the database in plain text** — a deliberate
decision for the "copy code" and "repeat transfer" features. The file is
protected only by your OS user permissions. If you reuse code phrases (a
persistent code), remember: a leak of the history file exposes working codes.
Recommendations: do not share the DB file with third parties, delete sensitive
records via History → Delete («Удалить»), do not reuse codes for important
transfers.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
mypy src --strict
```

Integration tests use the `tests/fixtures/fake_croc.py` stub — a real croc and
network are not required. Non-obvious gotchas are collected in
[docs/notes.md](docs/notes.md); the development plan is
[docs/plans/completed/pycroc-plan.md](docs/plans/completed/pycroc-plan.md).

---

<a id="ru"></a>
# PyCroc · Русская версия

[English](#top)

TUI-клиент для [croc](https://github.com/schollz/croc) на Python + [Textual](https://github.com/Textualize/textual):
формы вместо CLI-флагов, живой прогресс-бар, QR-код кодовой фразы, история передач и профили настроек.

> Совместимо с croc v11 (проверено на v11.5.0): флаг `--transport`
> (auto/derp/relay), stored-передачи (`--store`), новый формат вывода кода
> (в v11 строка `Code is:` убрана) и устойчивость парсера к цветному выводу.
> Сквозная передача через локальный relay проверена на croc v11.5.0 и v10.2.7;
> форматы вывода v8/v9/v10 по-прежнему поддерживаются.

## Требования

- Python 3.11+
- Установленный бинарник `croc` (сам PyCroc его не устанавливает):
  `choco install croc` / `scoop install croc` / [релизы GitHub](https://github.com/schollz/croc/releases).
  Путь к бинарнику можно указать во вкладке Settings — в `PATH` он быть не обязан.

## Установка

Из исходников (публикация на PyPI пока не выполнялась):

```bash
git clone https://github.com/gregsonar/PyCroc.git && cd PyCroc
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install .
```

Для разработки: `pip install -e ".[dev]"`.

## Запуск

```bash
pycroc
```

Без установленного croc приложение покажет предупреждение и заблокирует вкладки
Send/Receive — укажите путь к бинарнику в Settings и нажмите «Проверить».

## Вкладки

- **Send** — дерево файлов с чекбоксами (space или клик по файлу — выбрать),
  форма опций croc (relay, пароль, socks5, throttle, кривая шифрования,
  транспорт `--transport` auto/derp/relay, exclude-шаблоны, stored-передача
  `--store` с числом выдач и сроком жизни и т.д.; пустое поле = значение по
  умолчанию), кнопка отправки и отмены. Кодовая фраза и QR-код появляются сразу
  после запуска передачи — код можно скопировать кнопкой, QR отсканировать
  телефоном.
- **Receive** — поле кодовой фразы с автодополнением из истории (принять
  подсказку — стрелка вправо), папка назначения (`--out`), авто-подтверждение
  перезаписи (`--yes`). При выключенном авто-подтверждении конфликт перезаписи
  показывается модальным окном «Да/Нет».
- **History** — таблица прошлых передач (дата, файл, размер, направление,
  статус) с поиском по имени файла (регистронезависимо, включая кириллицу).
  Действия по строке: повторить передачу (открывает Send/Receive с
  предзаполненным кодом), скопировать код, удалить запись.
- **Settings** — профили опций (создание/редактирование/удаление/активация;
  профиль `default` защищён от удаления), путь к бинарнику croc с проверкой
  версии. Активный профиль даёт значения по умолчанию для Send/Receive.

## Горячие клавиши

| Клавиша | Действие |
| --- | --- |
| `Tab` / `Shift+Tab` | следующее / предыдущее поле или элемент |
| `↑` / `↓` | в формах — переход между полями; в дереве и таблицах — курсор |
| `Space` | отметить файл/папку в дереве выбора |
| `Enter` | развернуть папку в дереве; выбрать строку |
| `Ctrl+P` | палитра команд Textual |
| `Ctrl+Q` | выход |

## Конфигурация и профили

Файл конфигурации редактируем вручную (комментарии сохраняются при записи):

- Windows: `%LOCALAPPDATA%\pycroc\pycroc\config.toml`
- Linux: `~/.config/pycroc/config.toml`
- macOS: `~/Library/Application Support/pycroc/config.toml`

```toml
active_profile = "home"
binary_path = "C:/tools/croc.exe"   # пусто/нет ключа = "croc" из PATH

[profiles.home]
relay = "my-relay.example.com:9009" # свой relay (--relay)
pass = "s3cret"                     # пароль relay или путь к файлу с ним
curve = "p256"                      # p256 | p384 | p521 | siec | ed25519
transport = "auto"                  # auto | derp | relay (croc v11.3)
hash_algo = "xxhash"                # xxhash | imohash | md5 (только send)
no_compress = false
ask = false
auto_accept = true                  # --yes и авто-ответ на запрос перезаписи
exclude = ["node_modules", ".git"]  # только send, через запятую в croc
transfers = 4                       # только send
store = false                       # stored-передача, только send (croc v11.1)
store_downloads = 1                 # число выдач для --store
store_expiration = "1d"             # срок жизни для --store, напр. "3d"
```

Повреждённый файл не роняет приложение: используется профиль по умолчанию,
а в интерфейсе показывается предупреждение с путём к файлу.

## История передач и безопасность

История хранится в SQLite:

- Windows: `%LOCALAPPDATA%\pycroc\pycroc\history.db`
- Linux: `~/.local/share/pycroc/history.db`

Кодовая фраза передаётся croc через переменную окружения `CROC_SECRET`, а не
через аргументы командной строки — поэтому она не видна в списке процессов ОС.

⚠️ **Кодовые фразы хранятся в БД открытым текстом** — это осознанное решение
ради функций «скопировать код» и «повторить передачу». Файл защищён только
правами вашего пользователя ОС. Если вы переиспользуете кодовые фразы
(постоянный код), помните: утечка файла истории раскрывает действующие
коды. Рекомендации: не передавайте файл БД третьим лицам, удаляйте
чувствительные записи через History → «Удалить», не переиспользуйте коды для
важных передач.

## Разработка

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
mypy src --strict
```

Интеграционные тесты используют заглушку `tests/fixtures/fake_croc.py` —
реальный croc и сеть не требуются. Неочевидные готчи собраны в
[docs/notes.md](docs/notes.md); план разработки —
[docs/plans/completed/pycroc-plan.md](docs/plans/completed/pycroc-plan.md).
