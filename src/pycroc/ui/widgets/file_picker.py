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
from textual.binding import Binding, BindingType
from textual.widgets import DirectoryTree
from textual.widgets.directory_tree import DirEntry
from textual.widgets.tree import TreeNode


class MultiSelectDirectoryTree(DirectoryTree):
    """DirectoryTree с чекбоксами; выбор — space на файле или папке."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_selected", "Отметить"),
    ]

    def __init__(self, path: str | Path, *, id: str | None = None) -> None:
        super().__init__(path, id=id)
        self._selected: set[Path] = set()

    def selected_paths(self) -> list[str]:
        """Отмеченные пути (строками, отсортированы) для build_send_args."""
        return [str(path) for path in sorted(self._selected)]

    def toggle(self, path: Path) -> None:
        """Переключает отметку пути; используется биндингом и тестами."""
        if path in self._selected:
            self._selected.discard(path)
        else:
            self._selected.add(path)
        self.refresh()

    def clear_selection(self) -> None:
        self._selected.clear()
        self.refresh()

    def action_toggle_selected(self) -> None:
        node = self.cursor_node
        if node is None or node.data is None:
            return
        self.toggle(node.data.path)

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
