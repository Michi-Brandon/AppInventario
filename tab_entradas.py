import os
from datetime import datetime

import pandas as pd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from movimientos_utils import guardar_movimientos_excel
from operadores import OPERADORES


class EntradasTab(QWidget):
    """Gestiona el registro de entradas y muestra solo los movimientos de tipo ENTRADA."""

    def __init__(self, config: dict, parent=None, on_entrada_registrada=None):
        super().__init__(parent)
        self.config = config
        self.on_entrada_registrada = on_entrada_registrada
        self.columnas = [
            "Tipo Movimiento",
            "Nota de Venta",
            "Orden de Compra",
            "Codigo",
            "Cantidad",
            "Operador",
            "Fecha",
        ]
        self.movimientos_path = os.path.join(
            self.config.get("carpeta_multivende", ""),
            "Movimientos",
            "movimientos.xlsx",
        )
        self.df_movimientos = pd.DataFrame(columns=self.columnas)

        self.auto_focus_activo = True
        self._app = QApplication.instance()
        if self._app:
            self._app.focusChanged.connect(self._manejar_cambio_foco)
        self.destroyed.connect(self._desconectar_autofoco)

        self._build_ui()
        self.cargar_movimientos()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        self.setLayout(layout)

        fila_datos = QHBoxLayout()
        fila_datos.addWidget(QLabel("Orden de compra (opcional):"))
        self.input_orden_compra = QLineEdit()
        self.input_orden_compra.setPlaceholderText("Ej: OC-123456")
        fila_datos.addWidget(self.input_orden_compra)

        fila_datos.addWidget(QLabel("Operador:"))
        self.operador_combo = QComboBox()
        self.operador_combo.addItems(OPERADORES)
        self.operador_combo.setMinimumWidth(180)
        fila_datos.addWidget(self.operador_combo)
        fila_datos.addStretch()
        layout.addLayout(fila_datos)

        fila_scan = QHBoxLayout()
        fila_scan.addWidget(QLabel("Codigo producto:"))
        self.input_codigo = QLineEdit()
        self.input_codigo.setPlaceholderText("Escanee o escriba el codigo del producto y presione Enter")
        self.input_codigo.returnPressed.connect(self.registrar_entrada)
        fila_scan.addWidget(self.input_codigo, stretch=1)

        self.btn_registrar = QPushButton("Agregar entrada")
        self.btn_registrar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_registrar.clicked.connect(self.registrar_entrada)
        fila_scan.addWidget(self.btn_registrar)

        self.btn_recargar = QPushButton("Actualizar listado")
        self.btn_recargar.clicked.connect(self.cargar_movimientos)
        fila_scan.addWidget(self.btn_recargar)

        self.btn_autofoco = QPushButton("Liberar foco")
        self.btn_autofoco.setCheckable(True)
        self.btn_autofoco.setToolTip("Permite escribir en otros campos sin regresar al lector automaticamente.")
        self.btn_autofoco.toggled.connect(self._toggle_autofoco)
        fila_scan.addWidget(self.btn_autofoco)

        layout.addLayout(fila_scan)

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
        layout.addWidget(self.tabla, 1)
        self._enfocar_codigo()

    def registrar_entrada(self):
        codigo = self.input_codigo.text().strip()
        if not codigo:
            self.lbl_estado.setText("Ingrese o escanee un codigo valido.")
            self.input_codigo.setFocus()
            return
        self.input_codigo.clear()

        operador = self.operador_combo.currentText()
        if operador == OPERADORES[0]:
            QMessageBox.warning(self, "Operador requerido", "Seleccione el operador que recibe los productos.")
            self.operador_combo.setFocus()
            return

        orden_compra = self.input_orden_compra.text().strip()
        fecha_actual = datetime.now()

        df = self._leer_movimientos()
        nueva_fila = {
            "Tipo Movimiento": "ENTRADA",
            "Nota de Venta": "",
            "Orden de Compra": orden_compra,
            "Codigo": codigo,
            "Cantidad": 1,
            "Operador": operador,
            "Fecha": fecha_actual,
        }
        df.loc[len(df)] = nueva_fila

        self._actualizar_cache(df)

        try:
            guardar_movimientos_excel(df, self.movimientos_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la entrada.\n\n{exc}")
            self.input_codigo.setText(codigo)
            self.input_codigo.setFocus()
            self.cargar_movimientos()
            return

        self.input_codigo.setFocus()
        self.lbl_estado.setText(f"{codigo} registrado como ENTRADA ({fecha_actual.strftime('%Y-%m-%d %H:%M')}).")

        if self.on_entrada_registrada:
            self.on_entrada_registrada()

    def cargar_movimientos(self):
        df = self._leer_movimientos()
        self._actualizar_cache(df)

    def _actualizar_cache(self, df_total: pd.DataFrame):
        df_vista = df_total.copy()
        if not df_vista.empty:
            df_vista["Fecha"] = pd.to_datetime(df_vista["Fecha"], errors="coerce")
            df_vista = df_vista[df_vista["Tipo Movimiento"].astype(str).str.upper() == "ENTRADA"]
            df_vista = df_vista.sort_values(by="Fecha", ascending=False, na_position="last")
        else:
            df_vista = pd.DataFrame(columns=self.columnas)

        self.df_movimientos = df_vista
        self._poblar_tabla(df_vista)
        self._actualizar_lbl_estado(df_vista)

    def _leer_movimientos(self):
        columnas = self.columnas
        carpeta = os.path.dirname(self.movimientos_path)
        os.makedirs(carpeta, exist_ok=True)
        if not os.path.exists(self.movimientos_path):
            return pd.DataFrame(columns=columnas)

        try:
            df = pd.read_excel(self.movimientos_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al cargar", f"No se pudo abrir el archivo de movimientos.\n\n{exc}")
            return pd.DataFrame(columns=columnas)

        for columna in columnas:
            if columna not in df.columns:
                df[columna] = "" if columna != "Cantidad" else 0
        return df[columnas].copy()

    def _actualizar_lbl_estado(self, df: pd.DataFrame):
        if df.empty:
            self.lbl_estado.setText("No hay entradas registradas.")
            return
        primera = df.iloc[0]
        codigo = primera.get("Codigo", "")
        fecha = ""
        if pd.notna(primera.get("Fecha")):
            fecha_dt = primera["Fecha"]
            fecha = fecha_dt.strftime("%Y-%m-%d %H:%M") if hasattr(fecha_dt, "strftime") else str(fecha_dt)
        self.lbl_estado.setText(f"Mostrando {len(df)} entradas registradas. Ultima: {codigo} ({fecha})")

    def _poblar_tabla(self, df: pd.DataFrame):
        self.tabla.setRowCount(len(df))
        self.tabla.setSortingEnabled(False)

        for fila_idx, (_, fila) in enumerate(df.iterrows()):
            for col_idx, columna in enumerate(self.columnas):
                valor = fila.get(columna, "")
                if columna == "Fecha" and pd.notna(valor):
                    texto = valor.strftime("%Y-%m-%d %H:%M") if hasattr(valor, "strftime") else str(valor)
                else:
                    texto = "" if pd.isna(valor) else str(valor)
                item = QTableWidgetItem(texto)
                if columna == "Cantidad":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.tabla.setItem(fila_idx, col_idx, item)

        self.tabla.setSortingEnabled(True)

    def _toggle_autofoco(self, liberado: bool):
        """Si liberado es True, se desactiva el autofoco."""
        self.auto_focus_activo = not liberado
        if liberado:
            self.btn_autofoco.setText("Volver a autofoco")
        else:
            self.btn_autofoco.setText("Liberar foco")
            self._enfocar_codigo()

    def _widgets_permitidos_autofoco(self):
        permitidos = {
            self.input_codigo,
            self.input_orden_compra,
            self.operador_combo,
            self.btn_registrar,
            self.btn_recargar,
            self.btn_autofoco,
        }
        try:
            vista_combo = self.operador_combo.view()
        except Exception:  # noqa: BLE001
            vista_combo = None
        if vista_combo is not None:
            permitidos.add(vista_combo)
        return permitidos

    def _manejar_cambio_foco(self, anterior, nuevo):
        if not self.auto_focus_activo or not self.isVisible():
            return
        if nuevo in self._widgets_permitidos_autofoco():
            return
        if nuevo is None:
            QTimer.singleShot(0, self._enfocar_codigo)
            return
        if QApplication.focusWidget() is self.input_codigo:
            return
        QTimer.singleShot(0, self._enfocar_codigo)

    def _enfocar_codigo(self):
        if not self.isVisible():
            return
        self.input_codigo.setFocus()
        self.input_codigo.selectAll()

    def _desconectar_autofoco(self):
        if self._app:
            try:
                self._app.focusChanged.disconnect(self._manejar_cambio_foco)
            except TypeError:
                pass
