import glob
import os
from datetime import datetime
from typing import Callable, Optional

import pandas as pd
from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from api_mercadolibre import NonPrintableError, descargar_etiqueta_mercadolibre, obtener_shipping_id
from api_zipnova import (
    descargar_etiqueta_zipnova_por_external_id,
    descargar_etiqueta_zipnova_por_nombre,
)
from api_enviame import (
    descargar_etiquetas_enviame_por_shipping,
    descargar_etiqueta_enviame_por_delivery,
    marcar_impreso_enviame_por_shipping,
)
from api_paris_cencosud import descargar_etiqueta_paris_cencosud

from movimientos_utils import forzar_columnas_texto_excel, guardar_movimientos_excel
from operadores import OPERADORES
from rutas_multivende import resolver_rutas_multivende


class LineaCodigoFija(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._force_focus = True

    def set_force_focus(self, enabled: bool):
        self._force_focus = enabled
        if enabled:
            self.setFocus()

    def focusOutEvent(self, event):
        # Ignora pérdida de foco cuando corresponde
        if self._force_focus:
            self.setFocus()
            event.ignore()
        else:
            super().focusOutEvent(event)

    def mousePressEvent(self, event):
        # Permite escribir normalmente, pero fuerza foco de nuevo si está habilitado
        if self._force_focus:
            self.setFocus()
        super().mousePressEvent(event)

    def event(self, e):
        # Evita que otras ventanas roben el foco solo cuando está habilitado
        if self._force_focus and e.type() == QEvent.Type.FocusOut:
            self.setFocus()
            return True
        return super().event(e)


class VerificacionTab(QWidget):
    def __init__(
        self,
        config: dict,
        parent=None,
        on_salida_generada: Optional[Callable[[], None]] = None,
        on_carga_multivende: Optional[Callable[[pd.DataFrame, int, int], None]] = None,
    ):
        super().__init__(parent)
        self.config = config
        self.on_salida_generada = on_salida_generada
        self.on_carga_multivende = on_carga_multivende
        # Editar operadores.py para agregar o quitar operadores disponibles en la UI.
        self.operadores = list(OPERADORES)
        self.df_multivende = None
        self.df_tabla = pd.DataFrame()
        self.df_actual = pd.DataFrame()
        self.vista_esquema = False
        self.codigo_actual_mostrado = ""
        self.codigo_actual_busqueda = ""
        self.nombre_cliente_actual = ""
        self._last_files_signature = None
        self.rutas = resolver_rutas_multivende(self.config)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        # Línea de búsqueda / escaneo
        linea_busqueda = QHBoxLayout()
        self.input_codigo = LineaCodigoFija()
        self.input_codigo.setPlaceholderText("Escanee o ingrese código de venta (columna H) y presione Enter…")
        self.input_codigo.returnPressed.connect(self.buscar_codigo_venta)
        linea_busqueda.addWidget(QLabel("Código de venta:"))
        linea_busqueda.addWidget(self.input_codigo)

        # Selector de operador + vista justo debajo del input
        self.operador_combo = QComboBox()
        self.operador_combo.addItems(self.operadores)
        self.operador_combo.setMinimumWidth(200)

        fila_operador_vista = QHBoxLayout()
        operador_box = QHBoxLayout()
        operador_box.addWidget(QLabel("Operador:"))
        operador_box.addWidget(self.operador_combo)
        fila_operador_vista.addLayout(operador_box)
        fila_operador_vista.addStretch()

        self.btn_modo_imp = QPushButton("Modo Impresión")
        self.btn_modo_imp.setCheckable(True)
        self.btn_modo_imp.setToolTip(
            "Si esta activo, al escanear una venta se descarga la etiqueta automaticamente."
        )
        self.btn_modo_imp.toggled.connect(self._actualizar_modo_imp_style)
        self._actualizar_modo_imp_style(False)

        vista_box = QHBoxLayout()
        lbl_vista = QLabel("Vista:")
        self.btn_tabla = QPushButton("Tabla")
        self.btn_tabla.setCheckable(True)
        self.btn_tabla.setChecked(True)
        self.btn_esquema = QPushButton("Esquema")
        self.btn_esquema.setCheckable(True)
        self.btn_tabla.clicked.connect(lambda: self.cambiar_vista(False))
        self.btn_esquema.clicked.connect(lambda: self.cambiar_vista(True))
        vista_box.addWidget(lbl_vista)
        vista_box.addWidget(self.btn_tabla)
        vista_box.addWidget(self.btn_esquema)

        vista_col = QVBoxLayout()
        vista_col.addWidget(self.btn_modo_imp, alignment=Qt.AlignmentFlag.AlignLeft)
        vista_col.addLayout(vista_box)

        fila_operador_vista.addLayout(vista_col)

        # Bloque de info grande (Cliente / Canal / Productos / Escaneados)
        fuente_titulo = QFont("Segoe UI", 18, QFont.Weight.Bold)
        self.lbl_cliente = QLabel("Cliente: —")
        self.lbl_cliente.setFont(fuente_titulo)
        self.lbl_canal = QLabel("Canal: —")
        self.lbl_canal.setFont(fuente_titulo)
        self.lbl_productos = QLabel("Productos: 0")
        self.lbl_productos.setFont(fuente_titulo)
        self.lbl_escaneados = QLabel("Escaneados: 0")
        self.lbl_escaneados.setFont(fuente_titulo)
        self.lbl_codigo = QLabel("Código venta: —")
        self.lbl_codigo.setFont(fuente_titulo)
        self.lbl_estado_impresion = QLabel("No impreso")
        self.lbl_estado_impresion.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.lbl_estado_impresion.setStyleSheet("color: gray; font-weight: bold; font-size: 18px;")

        info_col = QVBoxLayout()
        info_col.addWidget(self.lbl_cliente)
        info_col.addWidget(self.lbl_canal)
        info_col.addWidget(self.lbl_productos)
        info_col.addWidget(self.lbl_escaneados)
        info_col.addWidget(self.lbl_codigo)
        info_col.addWidget(self.lbl_estado_impresion)

        info_wrapper = QHBoxLayout()
        info_wrapper.addLayout(info_col)
        info_wrapper.addStretch()

        # Tabla con scroll
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(4)
        self.tabla.setHorizontalHeaderLabels(["Código Producto", "Nombre Producto", "Cantidad", "Escaneado"])
        tabla_scroll = QScrollArea()
        tabla_scroll.setWidgetResizable(True)
        tabla_scroll.setWidget(self.tabla)

        # Bloque de códigos incorrectos
        self.txt_incorrectos = QTextEdit()
        self.txt_incorrectos.setReadOnly(True)
        self.txt_incorrectos.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.txt_incorrectos.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.txt_incorrectos.setStyleSheet(
            """
            QTextEdit {
                background-color: #f9f9f9;
                border: 1px solid #ccc;
                color: #b00020;
                font-weight: 600;
                font-size: 12px;
                padding: 6px;
            }
        """
        )
        self.txt_incorrectos.setPlaceholderText("Códigos incorrectos escaneados aparecerán aquí...")

        contenedor_tabla = QVBoxLayout()
        contenedor_tabla.addWidget(tabla_scroll, stretch=7)
        contenedor_tabla.addWidget(self.txt_incorrectos, stretch=3)

        # Botones inferiores
        pie = QHBoxLayout()
        self.btn_generar_salida = QPushButton("Generar Salida")
        self.btn_imprimir = QPushButton("Imprimir etiqueta")
        self.btn_generar_salida.clicked.connect(self.generar_salida)
        self.btn_imprimir.clicked.connect(self.imprimir_etiqueta_automatica)
        pie.addStretch()
        pie.addWidget(self.btn_generar_salida)
        pie.addWidget(self.btn_imprimir)

        layout.addLayout(linea_busqueda)
        layout.addLayout(fila_operador_vista)
        layout.addLayout(info_wrapper)
        layout.addLayout(contenedor_tabla)
        layout.addLayout(pie)
        self.setLayout(layout)
        self.input_codigo.setFocus()

    # ------------------------------------------------------------------
    # Flujo principal
    # ------------------------------------------------------------------
    def cargar_excel(self, mostrar_mensaje=True):
        carpeta = self.rutas["archivos"]
        if not carpeta:
            if mostrar_mensaje:
                QMessageBox.warning(
                    self,
                    "Sin ruta",
                    "No hay ruta configurada para leer los Excel de Multivende.",
                )
            else:
                print("[AUTO] No hay ruta configurada para leer Multivende.")
            return
        archivos = glob.glob(os.path.join(carpeta, "*.xls*"))

        if not archivos:
            if mostrar_mensaje:
                QMessageBox.warning(self, "Sin archivos", f"No se encontraron archivos Excel en:\n{carpeta}")
            return

        # Evita reprocesar si la lista de archivos no cambió (solo en modo automático).
        firma_actual = sorted((os.path.basename(a), os.path.getmtime(a)) for a in archivos)
        if not mostrar_mensaje and self._last_files_signature == firma_actual:
            return

        dfs = []
        errores = []

        for archivo in archivos:
            try:
                df_temp = pd.read_excel(archivo)
                df_temp["ArchivoOrigen"] = os.path.basename(archivo)
                dfs.append(df_temp)
            except Exception as e:  # noqa: BLE001
                errores.append(f"{os.path.basename(archivo)} → {str(e)}")

        if not dfs:
            if mostrar_mensaje:
                QMessageBox.critical(self, "Error", "No se pudo leer ningún archivo Excel.")
            return

        df_total = pd.concat(dfs, ignore_index=True)

        if "ID Venta Multivende" in df_total.columns:
            archivo_fechas = {os.path.basename(a): os.path.getmtime(a) for a in archivos}
            df_total["FechaArchivo"] = df_total["ArchivoOrigen"].map(archivo_fechas)

            antes = len(df_total)
            ids_multifile = df_total.groupby("ID Venta Multivende")["ArchivoOrigen"].nunique()
            ids_multifile = ids_multifile[ids_multifile > 1].index.tolist()

            df_filtrado = []
            for venta_id, grupo in df_total.groupby("ID Venta Multivende"):
                if venta_id in ids_multifile:
                    archivo_reciente = grupo.loc[grupo["FechaArchivo"].idxmax(), "ArchivoOrigen"]
                    grupo = grupo[grupo["ArchivoOrigen"] == archivo_reciente]
                df_filtrado.append(grupo)

            df_total = pd.concat(df_filtrado, ignore_index=True)
            despues = len(df_total)
            print(f"[INFO] Eliminadas {antes - despues} filas duplicadas entre archivos por ID Venta Multivende.")
            df_total = df_total.drop(columns=["FechaArchivo"], errors="ignore")

        self.df_multivende = df_total
        total_filas = len(self.df_multivende)
        total_archivos = len(dfs)
        if self.on_carga_multivende:
            try:
                self.on_carga_multivende(self.df_multivende, total_archivos, total_filas)
            except Exception as exc:  # noqa: BLE001
                print("Callback on_carga_multivende falló:", exc)

        if mostrar_mensaje:
            mensaje = (
                f"{total_archivos} archivos cargados correctamente.\nTotal de filas combinadas: {total_filas}"
            )
            if errores:
                mensaje += f"\n\n Archivos con error:\n" + "\n".join(errores)
            QMessageBox.information(self, "Carga completa", mensaje)
        else:
            print(f"[AUTO] {datetime.now():%H:%M:%S} → {total_archivos} archivos cargados ({total_filas} filas).")

        # Actualiza la firma de archivos tras una carga exitosa.
        self._last_files_signature = firma_actual

    def buscar_codigo_venta(self):
        codigo = self.input_codigo.text().strip()
        self.input_codigo.clear()
        if not codigo:
            return

        codigo_original = codigo
        codigo_busqueda = self._normalizar_codigo_busqueda(codigo)

        if len(codigo) == 8:
            self.procesar_codigo_producto(codigo)
            return

        elif len(codigo) not in [13, 16]:
            print(f"[Aviso] Código de venta con longitud no estándar: {len(codigo)} → {codigo}")

        if self.df_multivende is None:
            QMessageBox.warning(self, "Sin archivo", "Primero carga el archivo de Multivende (menú Archivo).")
            return

        codigos_norm = self.df_multivende.iloc[:, 7].astype(str).apply(self._normalizar_codigo_busqueda)
        filas = self.df_multivende[codigos_norm == codigo_busqueda]
        if filas.empty:
            QMessageBox.information(self, "Sin resultados", f"No se encontraron filas con el código {codigo_original}.")
            return

        self.codigo_actual_mostrado = codigo_original
        self.codigo_actual_busqueda = codigo_busqueda
        self.lbl_codigo.setText(f"Código venta: {codigo_original}")
        self.nombre_cliente_actual = str(filas.iloc[0, 9])

        self.df_actual = filas.copy()
        self.df_actual["Escaneado"] = 0

        cliente = str(filas.iloc[0, 9])
        canal = str(filas.iloc[0, 5])
        self.total_productos_actual = 0
        total_cantidad = int(pd.to_numeric(filas.iloc[:, 14], errors="coerce").fillna(0).sum())
        self.total_productos_actual = total_cantidad

        self.lbl_cliente.setText(f"Cliente: {cliente}")
        self.lbl_canal.setText(f"Canal: {canal}")
        self.lbl_productos.setText(f"Productos: {total_cantidad}")
        self.lbl_escaneados.setText("Escaneados: 0")

        df = pd.DataFrame(
            {
                "Código Producto": filas.iloc[:, 11].astype(str),
                "Nombre Producto": filas.iloc[:, 12].astype(str),
                "Cantidad": filas.iloc[:, 14].astype(int),
                "Escaneado": 0,
            }
        )
        self.df_tabla = df.copy()

        self.mostrar_tabla(df)
        self.txt_incorrectos.setText("")
        self.input_codigo.setFocus()

        if self.btn_modo_imp.isChecked():
            # En modo IMP, dispara la descarga de etiqueta apenas se escanea la venta.
            QTimer.singleShot(50, self.imprimir_etiqueta_automatica)

    def procesar_codigo_producto(self, codigo_prod: str):
        if getattr(self, "df_tabla", None) is None or self.df_tabla.empty:
            QMessageBox.warning(self, "Sin nota activa", "Primero escanee una nota de venta antes de escanear productos.")
            return

        df = self.df_tabla.copy()
        codigo_col = df.columns[0]
        codigo_norm = self._normalizar_codigo(codigo_prod)
        candidatos = {codigo_norm} if codigo_norm else set()
        if codigo_norm and codigo_norm[0] in {'1', '2'} and codigo_norm[1:].isdigit():
            prefijo = '1' if codigo_norm[0] == '2' else '2'
            candidatos.add(f"{prefijo}{codigo_norm[1:]}")
        
        codigos_df = df[codigo_col].astype(str).map(self._normalizar_codigo)
        encontrados = df[codigos_df.isin(candidatos)] if candidatos else df.iloc[0:0]

        if not encontrados.empty:
            idx = encontrados.index[0]
            cantidad_actual = int(df.at[idx, "Escaneado"])
            cantidad_real = int(df.at[idx, "Cantidad"])

            if cantidad_actual < cantidad_real:
                df.at[idx, "Escaneado"] = cantidad_actual + 1
            else:
                QMessageBox.information(
                    self, "Límite alcanzado", f"El producto {codigo_prod} ya está completamente escaneado."
                )

            total_escaneados = int(df["Escaneado"].sum())
            self.lbl_escaneados.setText(f"Escaneados: {total_escaneados}")

            self.df_tabla = df
            self.mostrar_tabla(df)
        else:
            texto = self.txt_incorrectos.toPlainText()
            hora_actual = datetime.now().strftime("%H:%M:%S")
            linea_nueva = f"[{hora_actual}] Código incorrecto: {codigo_prod}"
            nuevos = texto + "\n" + linea_nueva if texto else linea_nueva
            self.txt_incorrectos.setPlainText(nuevos)
            self.txt_incorrectos.verticalScrollBar().setValue(
                self.txt_incorrectos.verticalScrollBar().maximum()
            )

    def configurar_foco_codigo(self, activo: bool):
        if hasattr(self, "input_codigo"):
            self.input_codigo.set_force_focus(activo)

    def enfocar_codigo_si_principal(self, index=None):  # noqa: ARG002
        if hasattr(self, "input_codigo"):
            self.input_codigo.setFocus()

    def mostrar_tabla(self, df):
        etiquetas_path = self.rutas["etiquetas"]
        os.makedirs(etiquetas_path, exist_ok=True)
        registro_path = self.rutas["registro_impresiones"]
        if os.path.exists(registro_path):
            df_imp = pd.read_excel(registro_path, dtype=str)
        else:
            df_imp = pd.DataFrame(columns=["CódigoVenta", "Operador", "Fecha", "Estado"])

        for col in ["CódigoVenta", "Operador", "Fecha", "Estado"]:
            if col not in df_imp.columns:
                df_imp[col] = ""
        df_imp["CódigoVenta"] = df_imp["CódigoVenta"].fillna("").astype(str)

        codigo_actual = self.codigo_actual_mostrado or self.lbl_codigo.text().replace("Código venta:", "").strip()
        codigo_busqueda = self.codigo_actual_busqueda or codigo_actual
        estado = "No impreso"
        df_imp_codigos = df_imp["CódigoVenta"].astype(str).str.strip().apply(self._normalizar_codigo_busqueda)
        for codigo_ref in [codigo_actual, codigo_busqueda]:
            if not codigo_ref:
                continue
            objetivo = self._normalizar_codigo_busqueda(codigo_ref)
            mask = df_imp_codigos == objetivo
            if mask.any():
                estado = df_imp.loc[mask, "Estado"].iloc[-1]
                break

        self._set_estado_impresion(estado)

        self.tabla.clearContents()
        self.tabla.setRowCount(len(df))
        self.tabla.setColumnCount(len(df.columns))
        self.tabla.setHorizontalHeaderLabels(df.columns)

        for i in range(len(df)):
            cantidad = int(df.iloc[i]["Cantidad"])
            escaneado = int(df.iloc[i]["Escaneado"])
            progreso = min(escaneado / cantidad, 1.0) if cantidad > 0 else 0.0

            r = int(255 - (255 - 100) * progreso)
            g = int(255 - (255 - 255) * progreso)
            b = int(255 - (255 - 100) * progreso)
            brush_bg = QBrush(QColor(r, g, b))

            for j, col in enumerate(df.columns):
                item = QTableWidgetItem(str(df.iat[i, j]))
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(brush_bg)
                self.tabla.setItem(i, j, item)

        self.tabla.resizeColumnsToContents()

    def imprimir_etiqueta_automatica(self):
        self._set_estado_impresion("Imprimiendo...")
        self.btn_imprimir.setEnabled(False)
        QApplication.processEvents()

        codigo_mostrado = self.codigo_actual_mostrado or self.lbl_codigo.text().replace("Código venta:", "").strip()
        codigo_venta = self.codigo_actual_busqueda or codigo_mostrado
        if not codigo_venta:
            QMessageBox.warning(self, "Sin código", "Primero escanee una nota de venta antes de imprimir.")
            return

        canal = self.lbl_canal.text().replace("Canal:", "").strip().lower()

        if "mercado" in canal:
            plataforma = "mercadolibre"
        elif len(codigo_venta) == 13 and codigo_venta.isdigit():
            plataforma = "walmart"
        elif "paris" in canal:
            plataforma = "paris"
        elif "ripley" in canal:
            plataforma = "ripley"
        elif "woocommerce" in canal:
            plataforma = "woocommerce"
        else:
            QMessageBox.warning(self, "Canal desconocido", f"No se reconoce el canal: {canal}")
            return

        estado = "Error"

        # --- WooCommerce via API Zipnova ---
        if plataforma == "woocommerce":
            external_id = codigo_mostrado or codigo_venta
            if external_id and not str(external_id).upper().startswith("W"):
                external_id = f"W{external_id}"
            try:
                etiqueta_path = descargar_etiqueta_zipnova_por_external_id(external_id, fmt="zpl")
                print(f"Woo/Zipnova: Etiqueta API guardada en {etiqueta_path}")
                estado = "Impreso"
            except Exception as exc:  # noqa: BLE001
                print("Woo/Zipnova: Error al obtener etiqueta via API:", exc)
                msg_lower = str(exc).lower()
                if "external_id" in msg_lower or "no se encontraron env" in msg_lower:
                    estado = "Error Pedido Procesando"
                    QMessageBox.information(
                        self,
                        "Etiqueta aun no completa",
                        "La etiqueta no esta en estado 'Completa' en la tienda online o es Recogida Local; avisar a Wendy.",
                    )
                else:
                    estado = "Error"

        # --- MercadoLibre via API ---
        elif plataforma == "mercadolibre":
            try:
                etiqueta_path = descargar_etiqueta_mercadolibre(order_id=codigo_venta, response_type="zpl2")
                print(f"M: Etiqueta API guardada en {etiqueta_path}")
                estado = "Impreso"
            except NonPrintableError as exc:
                QMessageBox.information(
                    self,
                    "Etiqueta se emitira en la tarde o manana",
                    f"Mercado Libre indica que este envio es para entregar a la colecta manana.\n{exc}",
                )
                estado = "Error Colecta Manana"
                print(f"M: Etiqueta API no emitida (colecta manana) para {codigo_venta}")
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if "INVALID_SHIPMENT_MODE" in msg or "ME1" in msg:
                    print("M: Shipment ME1, intentando via Zipnova (API)...")
                    try:
                        shipping_id = obtener_shipping_id(codigo_venta)
                        etiqueta_path = descargar_etiqueta_zipnova_por_external_id(
                            str(shipping_id), fmt="zpl", file_name=codigo_venta
                        )
                        print(f"M: Etiqueta Zipnova API guardada en {etiqueta_path} (shipping_id={shipping_id})")
                        estado = "Impreso"
                    except Exception as zexc:  # noqa: BLE001
                        print("M: Error Zipnova API por shipping_id, probando por nombre:", zexc)
                        try:
                            etiqueta_path = descargar_etiqueta_zipnova_por_nombre(
                                nombre_cliente=self.nombre_cliente_actual or "",
                                fmt="zpl",
                            )
                            print(f"M: Etiqueta Zipnova API guardada en {etiqueta_path}")
                            estado = "Impreso"
                        except Exception as zexc2:  # noqa: BLE001
                            print("M: Error Zipnova API por nombre:", zexc2)
                            estado = "Error"
                else:
                    print("M: Error al obtener etiqueta via API:", exc)
                    estado = "Error"

        # --- Walmart / Paris / Ripley via APIs ---
        elif plataforma in {"walmart", "paris", "ripley"}:
            try:
                if plataforma == "walmart":
                    stop_una_pagina = (self.total_productos_actual == 1)
                    rutas = descargar_etiquetas_enviame_por_shipping(codigo_venta, canal="walmart", stop_after_first_match=stop_una_pagina)
                    # Muestra solo nota de venta + folios (sin ruta completa)
                    folios = []
                    for ruta in rutas:
                        nombre = os.path.splitext(os.path.basename(ruta))[0]
                        partes = nombre.split("-")
                        if len(partes) >= 2:
                            folios.append(partes[1])
                    folios_unicos = sorted(set(folios))
                    folios_str = "-".join([f for f in folios_unicos if f])
                    etiqueta_msg = f"{codigo_venta}-{folios_str}" if folios_str else str(codigo_venta)
                    print(f"Walmart/Enviame: etiquetas guardadas: {etiqueta_msg}")
                    try:
                        resp_labels = marcar_impreso_enviame_por_shipping(
                            codigo_venta,
                            canal="walmart",
                            stop_after_first_match=stop_una_pagina,
                        )
                        print(f"Walmart/Enviame: deliveries marcados como impreso: {codigo_venta}")
                    except Exception as mark_exc:  # noqa: BLE001
                        print(f"Walmart/Enviame: no se pudo marcar como impreso -> {mark_exc}")
                    total_folios = len(folios_unicos)
                    estado = "Impreso"
                    if total_folios == 0:
                        estado = "Error Sin Etiquetas"
                        print(f"Walmart/Enviame: sin etiquetas generadas para {codigo_venta}")
                    elif total_folios < self.total_productos_actual:
                        estado = "Error Faltan Etiquetas"
                        print(
                            f"Walmart/Enviame: folios obtenidos ({total_folios}) no coinciden con productos ({self.total_productos_actual})"
                        )
                    if estado.startswith("Error"):
                        QMessageBox.information(
                            self,
                            "Etiquetas incompletas en Walmart",
                            "Walmart aun no crea todas las etiquetas, avisar a Wendy",
                        )
                elif plataforma == "paris":
                    ruta = descargar_etiqueta_paris_cencosud(codigo_venta)
                    print(f"Paris/Cencosud: etiqueta guardada {ruta}")
                    estado = "Impreso"
                else:
                    ruta = descargar_etiqueta_enviame_por_delivery(codigo_venta, canal=plataforma)
                    print(f"{plataforma.capitalize()}/Enviame: etiqueta guardada {ruta}")
                    estado = "Impreso"
            except Exception as exc:  # noqa: BLE001
                msg_lower = str(exc).lower()
                if plataforma == "walmart" and "rechazado" in msg_lower:
                    print(f"API ({plataforma}) fallo: envio {codigo_venta} rechazado por courier.")
                    QMessageBox.information(
                        self,
                        "Etiqueta Walmart NO creada",
                        "Etiqueta Walmart NO creada, informar a Wendy el numero de envio",
                    )
                    estado = "Error"
                elif plataforma == "walmart" and ("no se pudo obtener etiqueta" in msg_lower or "no generadas" in msg_lower):
                    print(f"API ({plataforma}) fallo: etiquetas no creadas en Walmart/Enviame para {codigo_venta}")
                    QMessageBox.information(
                        self,
                        "Etiquetas incompletas en Walmart",
                        "Walmart aun no crea todas las etiquetas, avisar a Wendy",
                    )
                    estado = "Error Sin Etiquetas"
                elif plataforma == "ripley" and ("404" in msg_lower or "no existe ninguna instancia" in msg_lower):
                    print(f"API ({plataforma}) fallo: pedido sin etiquetas en Enviame para {codigo_venta} -> {exc}")
                    QMessageBox.information(
                        self,
                        "Pedido sin etiquetas",
                        "El pedido no esta creado en Enviame, avisar a Wendy.",
                    )
                    estado = "Error Sin Etiquetas"
                else:
                    print(f"API ({plataforma}) fallo:", exc)
                    estado = "Error"
        # Estado en UI
        self._set_estado_impresion(estado)

        self._registrar_impresion(codigo_mostrado or codigo_venta, estado)
        self.btn_imprimir.setEnabled(True)

        if hasattr(self, "df_tabla"):
            self.mostrar_tabla(self.df_tabla)

    def generar_salida(self):
        if getattr(self, "df_tabla", None) is None or self.df_tabla.empty:
            QMessageBox.warning(self, "Sin datos", "Primero escanee una nota de venta y sus productos.")
            return

        codigo_venta = self.codigo_actual_mostrado or self.lbl_codigo.text().replace("Código venta:", "").strip()
        if not codigo_venta:
            QMessageBox.warning(self, "Sin nota", "Debe seleccionar una nota de venta antes de generar la salida.")
            return

        operador = self.operador_combo.currentText()
        if operador == "-- Seleccione --":
            QMessageBox.warning(self, "Operador requerido", "Seleccione el operador que genera la salida.")
            return

        pendientes = self.df_tabla[self.df_tabla["Escaneado"] != self.df_tabla["Cantidad"]]
        if not pendientes.empty:
            QMessageBox.warning(
                self,
                "Escaneo incompleto",
                "Para generar la salida, todos los productos deben estar completamente escaneados.",
            )
            return

        movimientos_dir = self.rutas["movimientos"]
        movimientos_path = self.rutas["movimientos_excel"]
        if not movimientos_dir or not movimientos_path:
            QMessageBox.critical(self, "Ruta no configurada", "No se pudo determinar la carpeta de Movimientos.")
            return
        os.makedirs(movimientos_dir, exist_ok=True)

        columnas = [
            "Tipo Movimiento",
            "Nota de Venta",
            "Orden de Compra",
            "Codigo",
            "Cantidad",
            "Operador",
            "Fecha",
        ]

        if os.path.exists(movimientos_path):
            df_mov = pd.read_excel(movimientos_path)
        else:
            df_mov = pd.DataFrame(columns=columnas)
        for columna in columnas:
            if columna not in df_mov.columns:
                df_mov[columna] = ""
        df_mov = df_mov[columnas].copy()

        nuevas_filas = []
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for _, fila in self.df_tabla.iterrows():
            nuevas_filas.append(
                {
                    "Tipo Movimiento": "SALIDA",
                    "Nota de Venta": codigo_venta,
                    "Orden de Compra": "",
                    "Codigo": fila["Código Producto"],
                    "Cantidad": int(fila["Escaneado"]),
                    "Operador": operador,
                    "Fecha": fecha_actual,
                }
            )

        for fila in nuevas_filas:
            df_mov.loc[len(df_mov)] = fila

        guardar_movimientos_excel(df_mov, movimientos_path)

        QMessageBox.information(self, "Salida generada", "La salida fue registrada correctamente.")
        if self.on_salida_generada:
            self.on_salida_generada()

    def cambiar_vista(self, esquema: bool):
        self.vista_esquema = esquema
        self.btn_tabla.setChecked(not esquema)
        self.btn_esquema.setChecked(esquema)

    def _actualizar_modo_imp_style(self, activo: bool):
        if not hasattr(self, "btn_modo_imp"):
            return
        if activo:
            self.btn_modo_imp.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold;")
        else:
            self.btn_modo_imp.setStyleSheet("")

    def _registrar_impresion(self, codigo_venta: str, estado: str):
        etiquetas_path = self.rutas["etiquetas"]
        os.makedirs(etiquetas_path, exist_ok=True)
        registro_path = self.rutas["registro_impresiones"]

        df_registro = (
            pd.read_excel(registro_path, dtype=str)
            if os.path.exists(registro_path)
            else pd.DataFrame(columns=["CódigoVenta", "Operador", "Fecha", "Estado"])
        )
        for col in ["CódigoVenta", "Operador", "Fecha", "Estado"]:
            if col not in df_registro.columns:
                df_registro[col] = ""

        df_registro["CódigoVenta"] = df_registro["CódigoVenta"].fillna("").astype(str)
        df_registro["Operador"] = df_registro["Operador"].fillna("").astype(str)
        df_registro["Fecha"] = df_registro["Fecha"].fillna("").astype(str)
        df_registro["Estado"] = df_registro["Estado"].fillna("").astype(str)

        codigo_excel = str(codigo_venta)
        operador = self.operador_combo.currentText() if hasattr(self, "operador_combo") else ""

        nuevo = pd.DataFrame(
            [[codigo_excel, operador, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), estado]],
            columns=["CódigoVenta", "Operador", "Fecha", "Estado"],
        )
        df_registro = pd.concat([df_registro, nuevo], ignore_index=True)
        df_registro.to_excel(registro_path, index=False)
        forzar_columnas_texto_excel(registro_path, df_registro.columns, ["CódigoVenta"])

    def _normalizar_codigo(self, codigo: str) -> str:
        if codigo is None:
            return ""
        texto = str(codigo).strip()
        if texto.startswith("'"):
            texto = texto.lstrip("'")
        if texto.startswith('="') and texto.endswith('"'):
            texto = texto[2:-1]
        return texto

    def _normalizar_codigo_busqueda(self, codigo: str) -> str:
        """
        Normaliza el codigo de venta para busqueda, considerando '-' y "'" como equivalentes.
        Esto permite que los codigos generados por algunos lectores (que devuelven ' en lugar de -)
        encuentren el valor correcto guardado en Excel.
        """
        texto = self._normalizar_codigo(codigo)
        return texto.replace("'", "-")

    def _set_estado_impresion(self, estado: str):
        texto = estado if estado else "No impreso"
        estado_norm = texto.strip().lower()
        if "error" in estado_norm:
            color = "red"
        elif estado_norm.startswith("impreso"):
            color = "green"
        elif estado_norm.startswith("imprimiendo"):
            color = "#0078d4"
        elif estado_norm == "no impreso":
            color = "gray"
        else:
            color = "gray"
        self.lbl_estado_impresion.setText(texto)
        self.lbl_estado_impresion.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 18px;")
