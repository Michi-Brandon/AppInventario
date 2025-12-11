import os
from datetime import datetime

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rutas_multivende import resolver_rutas_multivende


class StockTab(QWidget):
    """Resumen de stock a partir del Excel de movimientos."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.rutas = resolver_rutas_multivende(self.config)
        self.columnas_tabla = ["Codigo", "Entradas", "Salidas", "Stock"]
        self.movimientos_path = self.rutas["movimientos_excel"]
        self.df_stock = pd.DataFrame(columns=self.columnas_tabla)
        self.ultima_actualizacion = None

        self._build_ui()
        self.actualizar_stock()

    def _build_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        self.setLayout(layout)

        izquierda = QVBoxLayout()
        izquierda.setSpacing(10)
        layout.addLayout(izquierda, stretch=2)

        controles_layout = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_actualizar.clicked.connect(self.actualizar_stock)
        controles_layout.addStretch(1)
        controles_layout.addWidget(self.btn_actualizar)
        izquierda.addLayout(controles_layout)

        self.lbl_estado = QLabel("Cargando stock...")
        izquierda.addWidget(self.lbl_estado)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(len(self.columnas_tabla))
        self.tabla.setHorizontalHeaderLabels(self.columnas_tabla)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.setStyleSheet(
            "QTableWidget::item:selected{background-color:#d4d4d4;color:#000;}"
        )
        izquierda.addWidget(self.tabla, stretch=1)

        derecha = QVBoxLayout()
        derecha.setSpacing(15)
        layout.addLayout(derecha, stretch=1)

        self.busqueda_codigo = QLineEdit()
        self.busqueda_codigo.setPlaceholderText("Buscar por codigo exacto")
        self.busqueda_codigo.textChanged.connect(self._actualizar_panel_derecho)
        self.busqueda_codigo.returnPressed.connect(self._procesar_busqueda_confirmada)
        derecha.addWidget(self.busqueda_codigo)

        self.lbl_foto = QLabel("Foto del producto\n(Pendiente)")
        self.lbl_foto.setFixedHeight(200)
        self.lbl_foto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_foto.setStyleSheet("border: 1px dashed #999; color: #666;")
        derecha.addWidget(self.lbl_foto)

        self.lbl_codigo_detalle = QLabel("Codigo: ---")
        self.lbl_codigo_detalle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fuente_codigo = QFont()
        fuente_codigo.setPointSize(16)
        fuente_codigo.setBold(True)
        self.lbl_codigo_detalle.setFont(fuente_codigo)
        self.lbl_nombre = QLabel("Nombre del producto: (pendiente)")
        self.lbl_categoria = QLabel("Categoria: (pendiente)")
        derecha.addWidget(self.lbl_codigo_detalle)
        derecha.addWidget(self.lbl_nombre)
        derecha.addWidget(self.lbl_categoria)

        self.lbl_stock_detalle = QLabel("Stock: ---")
        fuente_stock = QFont()
        fuente_stock.setPointSize(18)
        fuente_stock.setBold(True)
        self.lbl_stock_detalle.setFont(fuente_stock)
        self.lbl_stock_detalle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        derecha.addWidget(self.lbl_stock_detalle)
        derecha.addStretch(1)

    def enfocar_busqueda(self):
        self.busqueda_codigo.setFocus()
        self.busqueda_codigo.selectAll()

    def actualizar_stock(self):
        if not os.path.exists(self.movimientos_path):
            self.df_stock = pd.DataFrame(columns=self.columnas_tabla)
            self.ultima_actualizacion = None
            self._poblar_tabla(self.df_stock)
            self.lbl_estado.setText(f"No se encontro el archivo: {self.movimientos_path}")
            self._actualizar_panel_derecho()
            return

        try:
            df = pd.read_excel(self.movimientos_path)
        except Exception as exc:  # noqa: BLE001
            self.lbl_estado.setText(f"Error al abrir el archivo: {exc}")
            return

        columnas_necesarias = ["Tipo Movimiento", "Codigo", "Cantidad"]
        for columna in columnas_necesarias:
            if columna not in df.columns:
                df[columna] = None

        df["Codigo"] = df["Codigo"].fillna("").astype(str).str.strip()
        df = df[df["Codigo"] != ""].copy()
        if df.empty:
            self.df_stock = pd.DataFrame(columns=self.columnas_tabla)
        else:
            df["Cantidad"] = pd.to_numeric(df["Cantidad"], errors="coerce").fillna(0)
            df["Tipo Normalizado"] = df["Tipo Movimiento"].astype(str).str.strip().str.lower()

            mask_entradas = df["Tipo Normalizado"].str.startswith("entrada")
            mask_salidas = df["Tipo Normalizado"].str.startswith("salida")

            entradas = df.loc[mask_entradas].groupby("Codigo")["Cantidad"].sum()
            salidas = df.loc[mask_salidas].groupby("Codigo")["Cantidad"].sum()
            codigos = sorted(set(entradas.index).union(set(salidas.index)))

            data = []
            for codigo in codigos:
                ent = float(entradas.get(codigo, 0.0))
                sal = float(salidas.get(codigo, 0.0))
                stock = ent - sal
                data.append({"Codigo": codigo, "Entradas": ent, "Salidas": sal, "Stock": stock})

            self.df_stock = pd.DataFrame(data, columns=self.columnas_tabla)
            if not self.df_stock.empty:
                self.df_stock.sort_values(by="Stock", ascending=False, inplace=True, ignore_index=True)

        self.ultima_actualizacion = datetime.now()
        self._poblar_tabla(self.df_stock)
        self._actualizar_estado()
        self._actualizar_panel_derecho()

    def _poblar_tabla(self, df: pd.DataFrame):
        self.tabla.setSortingEnabled(False)
        self.tabla.setRowCount(len(df))

        for fila_idx, (_, fila) in enumerate(df.iterrows()):
            for col_idx, columna in enumerate(self.columnas_tabla):
                valor = fila.get(columna, 0) if columna != "Codigo" else fila.get(columna, "")
                texto = self._formatear_valor(valor, columna)
                item = QTableWidgetItem(texto)
                if columna == "Codigo":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabla.setItem(fila_idx, col_idx, item)

        self.tabla.setSortingEnabled(True)
        if not df.empty:
            self.tabla.sortItems(self.columnas_tabla.index("Stock"), Qt.SortOrder.DescendingOrder)

    def _formatear_valor(self, valor, columna):
        if columna == "Codigo":
            return "" if pd.isna(valor) else str(valor)
        if pd.isna(valor):
            return "0"
        if float(valor).is_integer():
            return f"{int(valor)}"
        return f"{valor:.2f}"

    def _actualizar_estado(self):
        if self.df_stock.empty:
            self.lbl_estado.setText("No hay movimientos para calcular stock.")
            return
        total = len(self.df_stock)
        if self.ultima_actualizacion:
            marca = self.ultima_actualizacion.strftime("%d-%m-%Y %H:%M")
            self.lbl_estado.setText(f"Productos: {total}. Ultima actualizacion: {marca}")
        else:
            self.lbl_estado.setText(f"Productos: {total}.")

    def _actualizar_panel_derecho(self):
        codigo = self.busqueda_codigo.text().strip()
        self._mostrar_detalle_codigo(codigo)

    def _procesar_busqueda_confirmada(self):
        codigo = self.busqueda_codigo.text().strip()
        self._mostrar_detalle_codigo(codigo)
        self.busqueda_codigo.setSelection(0, len(self.busqueda_codigo.text()))

    def _mostrar_detalle_codigo(self, codigo: str):
        if not codigo:
            self.lbl_codigo_detalle.setText("Codigo: ---")
            self.lbl_stock_detalle.setText("Stock: ---")
            self.tabla.clearSelection()
            return

        coincidencias = self.df_stock[self.df_stock["Codigo"].str.casefold() == codigo.casefold()]
        if coincidencias.empty:
            self.lbl_codigo_detalle.setText(f"Codigo: {codigo} (sin registros)")
            self.lbl_stock_detalle.setText("Stock: 0")
            self.tabla.clearSelection()
            return

        registro = coincidencias.iloc[0]
        stock = registro.get("Stock", 0)
        self.lbl_codigo_detalle.setText(f"Codigo: {registro['Codigo']}")
        if float(stock).is_integer():
            stock_txt = str(int(stock))
        else:
            stock_txt = f"{stock:.2f}"
        self.lbl_stock_detalle.setText(f"Stock: {stock_txt}")
        self._seleccionar_codigo_en_tabla(registro["Codigo"])

    def _seleccionar_codigo_en_tabla(self, codigo: str):
        self.tabla.clearSelection()
        if not codigo:
            return

        codigo_norm = codigo.strip().casefold()
        for fila in range(self.tabla.rowCount()):
            item_codigo = self.tabla.item(fila, 0)
            if not item_codigo:
                continue
            if item_codigo.text().strip().casefold() == codigo_norm:
                self.tabla.selectRow(fila)
                self.tabla.scrollToItem(item_codigo, QAbstractItemView.ScrollHint.PositionAtCenter)
                break
