import os
from datetime import datetime, timedelta

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rutas_multivende import resolver_rutas_multivende


class MovimientosTab(QWidget):
    """Muestra el Excel de movimientos con filtros rapidos y buscadores."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.rutas = resolver_rutas_multivende(self.config)
        self.columnas = [
            "Tipo Movimiento",
            "Nota de Venta",
            "Orden de Compra",
            "Codigo",
            "Cantidad",
            "Operador",
            "Fecha",
        ]
        self.rango_activo = "dia"
        self.movimientos_path = self.rutas["movimientos_excel"]
        self.df_movimientos = pd.DataFrame(columns=self.columnas)
        self.ultima_actualizacion = None

        self._build_ui()
        self.cargar_movimientos()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.setLayout(layout)

        rango_layout = QHBoxLayout()
        rango_layout.addWidget(QLabel("Rango rapido:"))
        self.rango_group = QButtonGroup(self)
        self.rango_group.setExclusive(True)
        botones = [
            ("dia", "Ultimo dia"),
            ("semana", "Ultima semana"),
            ("mes", "Ultimo mes"),
            ("todo", "Todo"),
        ]
        for key, texto in botones:
            btn = QPushButton(texto)
            btn.setCheckable(True)
            btn.setProperty("rango", key)
            btn.setMinimumWidth(110)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if key == self.rango_activo:
                btn.setChecked(True)
            self.rango_group.addButton(btn)
            rango_layout.addWidget(btn)
        self.rango_group.buttonClicked.connect(self._cambiar_rango)

        rango_layout.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_actualizar.clicked.connect(self.cargar_movimientos)
        rango_layout.addWidget(self.btn_actualizar)
        layout.addLayout(rango_layout)

        busqueda_layout = QHBoxLayout()
        busqueda_layout.addWidget(QLabel("Nota de venta:"))
        self.busqueda_nota = QLineEdit()
        self.busqueda_nota.setPlaceholderText("Ej: NV123456")
        self.busqueda_nota.textChanged.connect(self._aplicar_filtros)
        busqueda_layout.addWidget(self.busqueda_nota)

        busqueda_layout.addWidget(QLabel("Operador:"))
        self.busqueda_operador = QLineEdit()
        self.busqueda_operador.setPlaceholderText("Nombre o parte del nombre")
        self.busqueda_operador.textChanged.connect(self._aplicar_filtros)
        busqueda_layout.addWidget(self.busqueda_operador)

        layout.addLayout(busqueda_layout)

        self.lbl_estado = QLabel("")
        layout.addWidget(self.lbl_estado)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(len(self.columnas))
        self.tabla.setHorizontalHeaderLabels(self.columnas)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().setVisible(False)
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setSortingEnabled(True)
        self.tabla.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.tabla, 1)

    def cargar_movimientos(self):
        if not os.path.exists(self.movimientos_path):
            self.df_movimientos = pd.DataFrame(columns=self.columnas)
            self.ultima_actualizacion = None
            self._aplicar_filtros()
            self.lbl_estado.setText(f"No se encontro el archivo: {self.movimientos_path}")
            return

        try:
            df = pd.read_excel(self.movimientos_path)
        except Exception as exc:  # noqa: BLE001
            self.lbl_estado.setText(f"Error al abrir el archivo: {exc}")
            return

        for columna in self.columnas:
            if columna not in df.columns:
                df[columna] = ""

        df = df[self.columnas].copy()
        if not df.empty:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        self.df_movimientos = df
        self.ultima_actualizacion = datetime.now()
        self._aplicar_filtros()

    def _cambiar_rango(self, button):
        rango = button.property("rango")
        if rango and rango != self.rango_activo:
            self.rango_activo = rango
            self._aplicar_filtros()

    def _aplicar_filtros(self):
        df = self.df_movimientos.copy()
        total = len(df)

        if not df.empty and self.rango_activo != "todo":
            dias = {"dia": 1, "semana": 7, "mes": 30}.get(self.rango_activo, 30)
            limite = datetime.now() - timedelta(days=dias)
            df = df[df["Fecha"] >= limite]

        nota = self.busqueda_nota.text().strip()
        if nota:
            df = df[df["Nota de Venta"].astype(str).str.contains(nota, case=False, na=False)]

        operador = self.busqueda_operador.text().strip()
        if operador:
            df = df[df["Operador"].astype(str).str.contains(operador, case=False, na=False)]

        df = df.sort_values(by="Fecha", ascending=False, na_position="last")
        self._poblar_tabla(df)

        if self.ultima_actualizacion:
            marca = self.ultima_actualizacion.strftime("%d-%m-%Y %H:%M")
            estado_txt = f"Mostrando {len(df)} de {total} movimientos. Ultima actualizacion: {marca}"
        else:
            estado_txt = f"Mostrando {len(df)} de {total} movimientos."
        self.lbl_estado.setText(estado_txt)

    def _poblar_tabla(self, df: pd.DataFrame):
        self.tabla.setRowCount(len(df))
        self.tabla.setSortingEnabled(False)

        for fila_idx, (_, fila) in enumerate(df.iterrows()):
            for col_idx, columna in enumerate(self.columnas):
                valor = fila.get(columna, "")
                if columna == "Fecha" and pd.notna(valor):
                    texto = valor.strftime("%Y-%m-%d %H:%M")
                else:
                    texto = "" if pd.isna(valor) else str(valor)
                item = QTableWidgetItem(texto)
                if columna == "Cantidad":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.tabla.setItem(fila_idx, col_idx, item)

        self.tabla.setSortingEnabled(True)
