"""Скрипт-заглушка croc для интеграционных тестов CrocRunner.

Печатает в stderr заранее заданный сценарий строк с задержками. Сценарий —
JSON-файл, путь к которому передаётся через env-переменную
``PYCROC_FAKE_CROC_SCENARIO``:

{
  "steps": [
    {"line": "Code is: a-b-c"},                  // печать строки в stderr
    {"line": "...прогресс...", "end": "\r"},     // произвольный разделитель ("" — без)
    {"line": "...", "delay": 0.05},              // сон (сек) перед печатью
    {"delay": 30},                               // просто сон (для теста cancel)
    {"wait_stdin": true}                         // блокирующее чтение строки из stdin
  ],
  "exit_code": 0,
  "stdin_capture": "/path/file"                  // куда дописывать прочитанное из stdin
}

Спец-случай: при ``--version`` в аргументах печатает версию в stdout и
выходит с кодом 0 (для тестов ``check_binary``). stderr пишется байтами в
UTF-8, чтобы не зависеть от локали консоли Windows.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any


def _emit(text: str) -> None:
    sys.stderr.buffer.write(text.encode("utf-8"))
    sys.stderr.buffer.flush()


def main() -> int:
    if "--version" in sys.argv[1:]:
        sys.stdout.write("croc version v10.0.0-fake\n")
        return 0

    scenario_path = os.environ.get("PYCROC_FAKE_CROC_SCENARIO")
    if not scenario_path:
        _emit("fake_croc: env PYCROC_FAKE_CROC_SCENARIO is not set\n")
        return 2
    with open(scenario_path, encoding="utf-8") as fh:
        scenario: dict[str, Any] = json.load(fh)

    # Для тестов CROC_SECRET: пишем полученные argv и код из окружения в файл,
    # чтобы проверить, что кодовая фраза пришла через env, а не через argv.
    invocation_path = scenario.get("invocation_capture")
    if invocation_path:
        with open(invocation_path, "w", encoding="utf-8") as out:
            json.dump(
                {"argv": sys.argv[1:], "croc_secret": os.environ.get("CROC_SECRET")},
                out,
            )

    capture_path = scenario.get("stdin_capture")
    for step in scenario.get("steps", []):
        if "delay" in step:
            time.sleep(step["delay"])
        if "line" in step:
            _emit(step["line"] + step.get("end", "\n"))
        if step.get("wait_stdin"):
            answer = sys.stdin.readline()
            if capture_path:
                with open(capture_path, "a", encoding="utf-8") as out:
                    out.write(answer)
    return int(scenario.get("exit_code", 0))


if __name__ == "__main__":
    sys.exit(main())
