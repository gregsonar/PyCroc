# PyCroc

TUI GUI-клиент для [croc](https://github.com/schollz/croc) на Python + [Textual](https://github.com/Textualize/textual).

> Статус: MVP в разработке, приватный репозиторий.

## Требования

- Python 3.11+
- Установленный бинарник `croc` в `PATH` (сам PyCroc его не устанавливает)

## Установка (разработка)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Запуск тестов

```bash
pytest -q
ruff check .
mypy src --strict
```

## Запуск приложения

```bash
pycroc
```

Подробный план разработки: [`docs/plans/pycroc-tui-plan.md`](docs/plans/pycroc-tui-plan.md).
