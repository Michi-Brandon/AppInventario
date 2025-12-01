import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
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
    """Visualiza los datos cargados desde Multivende con filtros basicos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.df_base = pd.DataFrame()
        self.total_archivos = 0
        self.total_filas = 0
        self.estado_orden_fecha = None
        self._indice_fecha_actual = None
        self.alias_columnas_visibles = {
            "Código de venta": ["Código de venta", "Codigo de venta", "Nota de venta", "ID Venta Multivende"],
            "Fecha Venta": ["Fecha Venta", "Fecha de venta", "Fecha venta", "Fecha"],
            "Hora Venta": ["Hora Venta", "Hora de venta", "Hora"],
            "Canal de Venta": ["Canal de Venta", "Canal"],
            "SKU padre": ["SKU padre", "SKU Padre"],
            "Producto": ["Producto", "Nombre Producto"],
            "Cantidad": ["Cantidad"],
            "Cliente": ["Cliente", "Nombre cliente", "Nombre Cliente"],
            "Courier": ["Courier", "Carrier"],
            "Clase de envío": ["Clase de envío", "Clase de envio"],
            "Fecha límite de entrega al courier": [
                "Fecha límite de entrega al courier",
                "Fecha limite de entrega al courier",
            ],
            "Precio de venta": ["Precio de venta"],
            "Precio con descuento": ["Precio con descuento"],
            "Despacho": ["Despacho"],
            "Total pagado": ["Total pagado"],
            "ArchivoOrigen": ["ArchivoOrigen"],
        }
        self.columnas_visibles = list(self.alias_columnas_visibles.keys())
        self.alias_filtros = {
            "nota": self.alias_columnas_visibles["Código de venta"],
            "canal": self.alias_columnas_visibles["Canal de Venta"],
            "cliente": self.alias_columnas_visibles["Cliente"],
            "fecha": self.alias_columnas_visibles["Fecha Venta"],
        }
        self.opciones_canal = ["Walmart", "Paris", "Mercadolibre", "Woocommercem", "Ripley"]
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Nota de venta:"))
        self.filtro_nota = QLineEdit()
        self.filtro_nota.returnPressed.connect(self.aplicar_filtros)
        self.filtro_nota.textChanged.connect(self._aplicar_si_vacio)
        filtros.addWidget(self.filtro_nota)

        filtros.addWidget(QLabel("Canal:"))
        self.filtro_canal = QComboBox()
        self.filtro_canal.addItem("Todos")
        for canal in self.opciones_canal:
            self.filtro_canal.addItem(canal)
        self.filtro_canal.currentTextChanged.connect(self.aplicar_filtros)
        filtros.addWidget(self.filtro_canal)

        filtros.addWidget(QLabel("Nombre cliente:"))
        self.filtro_nombre = QLineEdit()
        self.filtro_nombre.returnPressed.connect(self.aplicar_filtros)
        self.filtro_nombre.textChanged.connect(self._aplicar_si_vacio)
        filtros.addWidget(self.filtro_nombre)

        filtros.addWidget(QLabel("Fecha venta:"))
        self.filtro_fecha = QLineEdit()
        self.filtro_fecha.setPlaceholderText("dd/mm/aaaa")
        self.filtro_fecha.returnPressed.connect(self.aplicar_filtros)
        self.filtro_fecha.textChanged.connect(self._aplicar_si_vacio)
        filtros.addWidget(self.filtro_fecha)

        btn_aplicar = QPushButton("Aplicar filtros")
        btn_aplicar.clicked.connect(self.aplicar_filtros)
        filtros.addWidget(btn_aplicar)
        layout.addLayout(filtros)

        self.lbl_info = QLabel("Sin datos cargados.")
        layout.addWidget(self.lbl_info)

        self.tabla = QTableWidget()
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(False)
        self.tabla.horizontalHeader().sectionClicked.connect(self._manejar_click_header)
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
        df = self._normalizar_columnas(self.df_base.copy())
        if df.empty:
            self.tabla.clear()
            self.tabla.setRowCount(0)
            return

        df = self._filtrar_texto(df, self.alias_filtros["nota"], self.filtro_nota.text().strip())
        canal = self.filtro_canal.currentText()
        canal_valor = "" if canal == "Todos" else canal.strip()
        df = self._filtrar_texto(df, self.alias_filtros["canal"], canal_valor, exacto=True)
        df = self._filtrar_texto(df, self.alias_filtros["cliente"], self.filtro_nombre.text().strip())
        df = self._filtrar_fecha(df, self.alias_filtros["fecha"], self.filtro_fecha.text().strip())
        df = self._ordenar_por_fecha(df, self.alias_filtros["fecha"])
        df = self._solo_columnas_visibles(df)
        self._pintar_tabla(df)

    def _pintar_tabla(self, df: pd.DataFrame):
        self.tabla.clear()
        self.tabla.setRowCount(len(df))
        self.tabla.setColumnCount(len(df.columns))
        self.tabla.setHorizontalHeaderLabels([str(c) for c in df.columns])
        self._indice_fecha_actual = None

        for i in range(len(df)):
            for j, col in enumerate(df.columns):
                val = df.iat[i, j]
                texto = "" if pd.isna(val) else str(val)
                item = QTableWidgetItem(texto)
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.tabla.setItem(i, j, item)
                if self._indice_fecha_actual is None and self._es_columna_fecha(col):
                    self._indice_fecha_actual = j

        header = self.tabla.horizontalHeader()
        if self.estado_orden_fecha is None or self._indice_fecha_actual is None:
            header.setSortIndicatorShown(False)
        else:
            orden_qt = (
                Qt.SortOrder.DescendingOrder if self.estado_orden_fecha == "desc" else Qt.SortOrder.AscendingOrder
            )
            header.setSortIndicatorShown(True)
            header.setSortIndicator(self._indice_fecha_actual, orden_qt)
        self.tabla.resizeColumnsToContents()

    def _aplicar_si_vacio(self, texto: str):
        if texto == "":
            self.aplicar_filtros()

    def _buscar_columna(self, df: pd.DataFrame, candidatos: list[str]):
        columnas_lower = {str(c).lower(): str(c) for c in df.columns}
        for candidato in candidatos:
            key = str(candidato).lower()
            if key in columnas_lower:
                return columnas_lower[key]
        return None

    def _filtrar_texto(self, df: pd.DataFrame, candidatos: list[str], valor: str, exacto: bool = False):
        if not valor:
            return df
        columna = self._buscar_columna(df, candidatos)
        if not columna:
            return df
        serie = df[columna].astype(str)
        if exacto:
            mascara = serie.str.casefold() == valor.casefold()
        else:
            mascara = serie.str.contains(valor, case=False, na=False)
        return df[mascara]

    def _filtrar_fecha(self, df: pd.DataFrame, candidatos: list[str], valor: str):
        if not valor:
            return df
        columna = self._buscar_columna(df, candidatos)
        if not columna:
            return df

        fecha_obj = pd.to_datetime(valor, errors="coerce", dayfirst=True)
        serie_fecha = pd.to_datetime(df[columna], errors="coerce", dayfirst=True)

        if pd.isna(fecha_obj):
            mascara = df[columna].astype(str).str.contains(valor, case=False, na=False)
            return df[mascara]

        mascara_fecha = serie_fecha.dt.date == fecha_obj.date()
        mascara_texto = df[columna].astype(str).str.contains(valor, case=False, na=False)
        return df[mascara_fecha | mascara_texto]

    def _ordenar_por_fecha(self, df: pd.DataFrame, candidatos: list[str]):
        columna = self._buscar_columna(df, candidatos)
        if not columna or self.estado_orden_fecha is None:
            return df

        fechas = pd.to_datetime(df[columna], errors="coerce", dayfirst=True)
        df = df.assign(_fecha_tmp=fechas)
        asc = self.estado_orden_fecha == "asc"
        df = df.sort_values(by="_fecha_tmp", ascending=asc, na_position="last").drop(columns=["_fecha_tmp"])
        return df

    def _solo_columnas_visibles(self, df: pd.DataFrame):
        columnas_presentes = [col for col in self.columnas_visibles if col in df.columns]
        if columnas_presentes:
            return df[columnas_presentes]
        return df

    def _es_columna_fecha(self, nombre: str):
        return str(nombre).lower() in {n.lower() for n in self.alias_filtros["fecha"]}

    def _manejar_click_header(self, indice: int):
        item = self.tabla.horizontalHeaderItem(indice)
        if not item or not self._es_columna_fecha(item.text()):
            return

        if self.estado_orden_fecha is None:
            self.estado_orden_fecha = "desc"
        elif self.estado_orden_fecha == "desc":
            self.estado_orden_fecha = "asc"
        else:
            self.estado_orden_fecha = None

        self.aplicar_filtros()

    def _normalizar_columnas(self, df: pd.DataFrame):
        renombres = {}
        columnas_lower = {str(c).lower(): str(c) for c in df.columns}
        for canonico, alias in self.alias_columnas_visibles.items():
            for nombre in alias:
                clave = str(nombre).lower()
                if clave in columnas_lower:
                    renombres[columnas_lower[clave]] = canonico
                    break
        return df.rename(columns=renombres)
