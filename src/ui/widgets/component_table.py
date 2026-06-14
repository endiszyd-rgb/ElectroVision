from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import QTableView, QHeaderView, QWidget, QVBoxLayout, QLineEdit, QLabel, QHBoxLayout
from src.core.models.component import Component

COLUMNS = ["Ref", "Wartość", "Typ", "Footprint", "Warstwa", "Ilość", "Producent", "Nr kat.", "Datasheet"]


class ComponentTableModel(QAbstractTableModel):
    def __init__(self, components: list[Component] | None = None) -> None:
        super().__init__()
        self._data: list[Component] = components or []

    def set_components(self, components: list[Component]) -> None:
        self.beginResetModel()
        self._data = components
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        comp = self._data[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return [
                comp.reference,
                comp.value,
                comp.component_type,
                comp.footprint.split(":")[-1] if ":" in comp.footprint else comp.footprint,
                comp.layer,
                str(comp.quantity),
                comp.manufacturer,
                comp.manufacturer_pn,
                comp.datasheet,
            ][col]
        if role == Qt.UserRole:
            return comp
        return None

    def component_at(self, row: int) -> Component | None:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None


class ComponentTableWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Szukaj:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filtruj po ref, wartości, typie…")
        filter_bar.addWidget(self._filter_edit)
        self._count_label = QLabel("0 komponentów")
        filter_bar.addWidget(self._count_label)
        layout.addLayout(filter_bar)

        self._model = ComponentTableModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        self._filter_edit.textChanged.connect(self._proxy.setFilterFixedString)
        self._model.modelReset.connect(self._update_count)

    def set_components(self, components: list[Component]) -> None:
        self._model.set_components(components)

    def _update_count(self) -> None:
        self._count_label.setText(f"{self._model.rowCount()} komponentów")

    def selected_component(self) -> Component | None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        source_idx = self._proxy.mapToSource(indexes[0])
        return self._model.component_at(source_idx.row())
