"""Multi-select выбор файлов/папок на базе DirectoryTree.

Textual не имеет нативного multi-select file picker; здесь поверх
``DirectoryTree`` ведётся множество отмеченных путей, а метка узла
дорисовывается чекбоксом. Обход файловой системы остаётся асинхронным —
слой выбора не трогает загрузку дерева (см. граничный случай плана про
длинные списки файлов).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich.style import Style
from rich.text import Text
from textual import on
from textual.binding import Binding, BindingType
from textual.widgets import DirectoryTree
from textual.widgets.directory_tree import DirEntry
from textual.widgets.tree import TreeNode


class MultiSelectDirectoryTree(DirectoryTree):
    """DirectoryTree с чекбоксами.

    Отметка: space на любом узле, либо клик/Enter по файлу (клик по папке —
    стандартное разворачивание).
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        # не "Отметить": визуально путается с "Отменить" (пункт 6 конспекта)
        Binding("space", "toggle_selected", "Выбрать"),
    ]

    def __init__(self, path: str | Path, *, id: str | None = None) -> None:
        super().__init__(path, id=id)
        self._selected: set[Path] = set()

    def selected_paths(self) -> list[str]:
        """Отмеченные пути (строками, отсортированы) для build_send_args."""
        return [str(path) for path in sorted(self._selected)]

    def toggle(self, path: Path) -> None:
        """Переключает отметку пути; используется биндингом, кликом и тестами."""
        if path in self._selected:
            self._selected.discard(path)
        else:
            self._selected.add(path)
        self._refresh_labels()

    def clear_selection(self) -> None:
        self._selected.clear()
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        # Tree кеширует отрендеренные метки; ключ кеша включает счётчик
        # _updates каждого узла в path строки, а root входит в path всех
        # строк — bump root инвалидирует все метки разом. Обычный refresh()
        # кеш не сбрасывает, и галочка не перерисовывалась до следующего
        # события (пункт 1 конспекта, готча №13 notes.md).
        self.root.refresh()
        self.refresh()

    def action_toggle_selected(self) -> None:
        node = self.cursor_node
        if node is None or node.data is None:
            return
        self.toggle(node.data.path)

    @on(DirectoryTree.FileSelected)
    def _file_clicked(self, event: DirectoryTree.FileSelected) -> None:
        # клик мышью (и Enter) по файлу переключает отметку (пункт 4
        # конспекта); у папок клик оставлен под разворачивание
        event.stop()
        self.toggle(event.path)

    def render_label(
        self, node: TreeNode[DirEntry], base_style: Style, style: Style
    ) -> Text:
        label = super().render_label(node, base_style, style)
        if node.data is None:
            return label
        marker = "☑ " if node.data.path in self._selected else "☐ "
        result = Text(marker, style=base_style)
        result.append_text(label)
        return result
