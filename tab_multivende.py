import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class MultivendeTab(QWidget):
    """Visualiza los datos cargados desde Multivende con filtros básicos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.df_base = pd.DataFrame()
        self.total_archivos = 0
        self.total_filas = 0
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Nota de venta:"))
        self.filtro_nota = QLineEdit()
        filtros.addWidget(self.filtro_nota)

        filtros.addWidget(QLabel("Canal:"))
        self.filtro_canal = QLineEdit()
        filtros.addWidget(self.filtro_canal)

        filtros.addWidget(QLabel("Nombre cliente:"))
        self.filtro_nombre = QLineEdit()
        filtros.addWidget(self.filtro_nombre)

        filtros.addWidget(QLabel("Fecha:"))
        self.filtro_fecha = QLineEdit()
        filtros.addWidget(self.filtro_fecha)

        btn_aplicar = QPushButton("Aplicar filtros")
        btn_aplicar.clicked.connect(self.aplicar_filtros)
        filtros.addWidget(btn_aplicar)
        layout.addLayout(filtros)

        self.lbl_info = QLabel("Sin datos cargados.")
        layout.addWidget(self.lbl_info)

        self.tabla = QTableWidget()
        self.tabla.setAlternatingRowColors(True)
        layout.addWidget(self.tabla)

        self.setLayout(layout)

    def set_data(self, df: pd.DataFrame, total_archivos: int = 0, total_filas: int = 0):
        self.df_base = df.copy()
        self.total_archivos = total_archivos
        self.total_filas = total_filas
        self.lbl_info.setText(
            f"Archivos: {total_archivos} | Filas cargadas: {total_filas}"
        )
        self.aplicar_filtros()

    def aplicar_filtros(self):
        df = self.df_base.copy()
        if df.empty:
            self.tabla.clear()
            self.tabla.setRowCount(0)
            return

        def filtra(col_idx: int, valor: str, frame: pd.DataFrame) -> pd.DataFrame:
            if not valor:
                return frame
            if col_idx >= len(frame.columns):
                return frame
            return frame[frame.iloc[:, col_idx].astype(str).str.contains(valor, case=False, na=False)]

        df = filtra(7, self.filtro_nota.text().strip(), df)
        df = filtra(5, self.filtro_canal.text().strip(), df)
        df = filtra(9, self.filtro_nombre.text().strip(), df)
        df = filtra(0, self.filtro_fecha.text().strip(), df)

        self._pintar_tabla(df)

    def _pintar_tabla(self, df: pd.DataFrame):
        self.tabla.clear()
        self.tabla.setRowCount(len(df))
        self.tabla.setColumnCount(len(df.columns))
        self.tabla.setHorizontalHeaderLabels([str(c) for c in df.columns])

        for i in range(len(df)):
            for j, col in enumerate(df.columns):
                val = df.iat[i, j]
                texto = "" if pd.isna(val) else str(val)
                item = QTableWidgetItem(texto)
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.tabla.setItem(i, j, item)

        self.tabla.resizeColumnsToContents()

