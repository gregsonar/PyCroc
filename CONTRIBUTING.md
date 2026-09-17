# Contributing

Процесс разработки этого проекта описан в
[`docs/style-guide/`](docs/style-guide/README.md) -- это точка входа и **единый
источник истины**. Здесь -- только то, что нужно под рукой сразу; за правилами
идите по ссылкам.

| Документ | О чём |
| --- | --- |
| [Процесс разработки](docs/style-guide/01-development-process.md) | Одна задача за раз, гейт из трёх проверок, ревью между задачами |
| [Ветвление и worktree](docs/style-guide/02-branching-and-worktrees.md) | Worktree, ветка на фичу, PR, мердж в dev/main, теги, SemVer |
| [Коммиты](docs/style-guide/03-commit-conventions.md) | Conventional Commits, тело коммита, ссылка на тесты |
| [Задачи и баги](docs/style-guide/04-tasks-and-bugs.md) | Формат задачи в плане и формат баг-репорта |
| [Документация и стиль](docs/style-guide/05-documentation-and-style.md) | Где что фиксируется, язык, без эмодзи, ссылки на тесты по имени |

## Quickstart

```bash
git clone https://github.com/gregsonar/PyCroc.git && cd PyCroc
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pycroc
```

## Гейт: прогнать перед завершением задачи (все три чисто)

```bash
pytest -q
ruff check .
mypy src --strict
```

Переход к следующей задаче запрещён, пока гейт не зелёный. То же гоняет CI.

## Поток работы

- Агент всегда работает в **своём git worktree** -- основной репозиторий не
  трогается.
- Каждая фича -- **отдельная ветка**.
- Готовую фичу (тесты прошли, ревью с человеком пройдено) вливаем в `dev`
  **через Pull Request** (прямой push -- исключение, по прямой команде).
- В `main` мёржит **только человек** и только по своему решению -- там всегда
  стабильная версия. Теги релизов -- по SemVer.

## Памятка

- **Коммиты:** `type(scope): summary (Task N / BUG-###)`, тело с root cause /
  verification / строкой `Tests:`. Без трейлеров вроде `Co-Authored-By`. Заголовок
  и тело -- по-английски. Подробнее -> [коммиты](docs/style-guide/03-commit-conventions.md).
- **Баги:** через скилл `bug-report-tracker`, по умолчанию в `.claude/bugs/`.
  Подробнее -> [задачи и баги](docs/style-guide/04-tasks-and-bugs.md).
- **Стиль:** без эмодзи (стрелки -- ASCII `->`/`<-`); проза по-русски, код и
  коммиты по-английски; про тесты пишем **по имени кейса**. Подробнее ->
  [документация и стиль](docs/style-guide/05-documentation-and-style.md).
- **Ничего не коммитим, не пушим, не мёржим и не тегируем без команды владельца.**
