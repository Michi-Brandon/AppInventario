import glob
import os
import socket
import subprocess
import time
from datetime import datetime

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
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager


class LineaCodigoFija(QLineEdit):
    def focusOutEvent(self, event):
        # Ignora pérdida de foco, lo recupera inmediatamente
        self.setFocus()
        event.ignore()

    def mousePressEvent(self, event):
        # Permite escribir normalmente, pero fuerza foco de nuevo
        self.setFocus()
        super().mousePressEvent(event)

    def event(self, e):
        # Evita que otras ventanas roben el foco
        if e.type() == QEvent.Type.FocusOut:
            self.setFocus()
            return True
        return super().event(e)


class VerificacionTab(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        # Editar esta lista para agregar o quitar operadores disponibles en la UI.
        self.operadores = [
            "-- Seleccione --",
            "Operador1",
            "Operador2",
            "Operador3",
            "Operador4",
        ]
        self.df_multivende = None
        self.df_tabla = pd.DataFrame()
        self.df_actual = pd.DataFrame()
        self.vista_esquema = False
        self.codigo_actual_mostrado = ""
        self.codigo_actual_busqueda = ""

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
        fila_operador_vista.addLayout(vista_box)

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

        info_col = QVBoxLayout()
        info_col.addWidget(self.lbl_cliente)
        info_col.addWidget(self.lbl_canal)
        info_col.addWidget(self.lbl_productos)
        info_col.addWidget(self.lbl_escaneados)
        info_col.addWidget(self.lbl_codigo)

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

        # Indicador visual sobre el botón de imprimir
        self.lbl_estado_impresion = QLabel("")
        self.lbl_estado_impresion.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_estado_impresion.setStyleSheet(
            """
            QLabel {
                color: #0078d4;
                font-weight: bold;
                font-size: 13px;
                margin-top: 4px;
            }
        """
        )
        pie.addWidget(self.lbl_estado_impresion)
        self.lbl_estado_impresion.hide()

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
        carpeta = self.config["carpeta_multivende"]
        archivos = glob.glob(os.path.join(carpeta, "*.xls*"))

        if not archivos:
            if mostrar_mensaje:
                QMessageBox.warning(self, "Sin archivos", f"No se encontraron archivos Excel en:\n{carpeta}")
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

        if mostrar_mensaje:
            mensaje = (
                f"{total_archivos} archivos cargados correctamente.\nTotal de filas combinadas: {total_filas}"
            )
            if errores:
                mensaje += f"\n\n Archivos con error:\n" + "\n".join(errores)
            QMessageBox.information(self, "Carga completa", mensaje)
        else:
            print(f"[AUTO] {datetime.now():%H:%M:%S} → {total_archivos} archivos cargados ({total_filas} filas).")

    def buscar_codigo_venta(self):
        codigo = self.input_codigo.text().strip()
        self.input_codigo.clear()
        if not codigo:
            return

        codigo_original = codigo
        codigo_busqueda = codigo

        if len(codigo) == 8:
            self.procesar_codigo_producto(codigo)
            return

        if len(codigo) == 10:
            codigo_busqueda = codigo[:9]
        elif len(codigo) not in [13, 16]:
            print(f"[Aviso] Código de venta con longitud no estándar: {len(codigo)} → {codigo}")

        if self.df_multivende is None:
            QMessageBox.warning(self, "Sin archivo", "Primero carga el archivo de Multivende (menú Archivo).")
            return

        filas = self.df_multivende[self.df_multivende.iloc[:, 7].astype(str) == codigo_busqueda]
        if filas.empty:
            QMessageBox.information(self, "Sin resultados", f"No se encontraron filas con el código {codigo_original}.")
            return

        self.codigo_actual_mostrado = codigo_original
        self.codigo_actual_busqueda = codigo_busqueda
        self.lbl_codigo.setText(f"Código venta: {codigo_original}")

        self.df_actual = filas.copy()
        self.df_actual["Escaneado"] = 0

        cliente = str(filas.iloc[0, 9])
        canal = str(filas.iloc[0, 5])
        total_cantidad = int(pd.to_numeric(filas.iloc[:, 14], errors="coerce").fillna(0).sum())

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

    def procesar_codigo_producto(self, codigo_prod: str):
        if getattr(self, "df_tabla", None) is None or self.df_tabla.empty:
            QMessageBox.warning(self, "Sin nota activa", "Primero escanee una nota de venta antes de escanear productos.")
            return

        df = self.df_tabla.copy()
        encontrados = df[df["Código Producto"].astype(str) == codigo_prod]

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

    def enfocar_codigo_si_principal(self, index=None):  # noqa: ARG002
        if hasattr(self, "input_codigo"):
            self.input_codigo.setFocus()

    def mostrar_tabla(self, df):
        etiquetas_path = os.path.join(self.config["carpeta_multivende"], "Etiquetas")
        os.makedirs(etiquetas_path, exist_ok=True)
        registro_path = os.path.join(etiquetas_path, "registro_impresiones.xlsx")
        if os.path.exists(registro_path):
            df_imp = pd.read_excel(registro_path)
        else:
            df_imp = pd.DataFrame(columns=["CódigoVenta", "Fecha", "Estado"])

        codigo_actual = self.codigo_actual_mostrado or self.lbl_codigo.text().replace("Código venta:", "").strip()
        codigo_busqueda = self.codigo_actual_busqueda or codigo_actual
        estado = "No impreso"
        for codigo_ref in [codigo_actual, codigo_busqueda]:
            if codigo_ref and codigo_ref in df_imp["CódigoVenta"].astype(str).values:
                estado = df_imp.loc[df_imp["CódigoVenta"].astype(str) == codigo_ref, "Estado"].iloc[-1]
                break

        df["Etiqueta"] = estado

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
        self.lbl_estado_impresion.setText("Imprimiendo...")
        self.lbl_estado_impresion.setStyleSheet(
            """
            QLabel {
                color: #0078d4;
                font-weight: bold;
                font-size: 13px;
            }
        """
        )
        self.lbl_estado_impresion.show()
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

        perfiles = {
            "mercadolibre": (
                r"C:\Users\bmonsalve\AppData\Local\Google\Chrome\Selenium",
                9222,
                "https://www.mercadolibre.cl/ventas/omni/listado?filters=TAB_TODAY",
            ),
            "walmart": (
                r"C:\Users\bmonsalve\AppData\Local\Google\Chrome\Walmart",
                9223,
                "https://app.enviame.io/deliveries/create#pickups",
            ),
            "paris": (
                r"C:\Users\bmonsalve\AppData\Local\Google\Chrome\Paris",
                9224,
                "https://app.enviame.io/deliveries/create#printed",
            ),
            "ripley": (
                r"C:\Users\bmonsalve\AppData\Local\Google\Chrome\Ripley",
                9225,
                "https://app.enviame.io/deliveries/create#pickups",
            ),
            "woocommerce": (
                r"C:\Users\bmonsalve\AppData\Local\Google\Chrome\Woo",
                9226,
                "https://app.zipnova.cl/shipments",
            ),
        }

        user_data_dir, port, url_base = perfiles[plataforma]
        chrome_path = r"C:\Users\bmonsalve\AppData\Local\Google\Chrome\Application\chrome.exe"

        def puerto_abierto(puerto):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect(("127.0.0.1", puerto))
                s.close()
                return True
            except Exception:  # noqa: BLE001
                return False

        if not puerto_abierto(port):
            subprocess.Popen(
                [
                    chrome_path,
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={user_data_dir}",
                ]
            )
            time.sleep(5)

        estado = "Error"
        try:
            chrome_options = Options()
            chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

            base_handle = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(url_base)

            if plataforma == "mercadolibre":
                tarjetas = driver.find_elements(By.CSS_SELECTOR, "div.andes-card.sc-row.sc-row-marketplace")
                encontrado = None
                for tarjeta in tarjetas:
                    try:
                        pack_id = tarjeta.find_element(By.CSS_SELECTOR, "div.left-column__pack-id")
                        if codigo_venta in pack_id.text:
                            encontrado = tarjeta
                            break
                    except Exception:  # noqa: BLE001
                        continue

                if encontrado:
                    boton = encontrado.find_element(By.XPATH, ".//button[contains(., 'Imprimir etiqueta')]")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", boton)
                    time.sleep(0.5)
                    try:
                        boton.click()
                    except Exception:  # noqa: BLE001
                        driver.execute_script("arguments[0].click();", boton)
                    print("M: Botón de etiqueta presionado")
                    estado = "Impreso"
                    self.lbl_estado_impresion.setText("Impreso")
                    self.lbl_estado_impresion.setStyleSheet("color: green; font-weight: bold; font-size: 13px;")
                else:
                    print("M: No se encontró la venta ", codigo_venta)
                    estado = "Error"
                    self.lbl_estado_impresion.setText("Error")
                    self.lbl_estado_impresion.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")

            elif len(codigo_venta) == 5:
                estado = "Error"
                try:
                    filas = driver.find_elements(By.CSS_SELECTOR, "tr.cursor-pointer")
                    encontrados = []
                    for fila in filas:
                        texto = fila.text.replace("W", "")
                        if codigo_venta in texto:
                            encontrados.append(fila)

                    if encontrados:
                        print(f"Z: Encontrados {len(encontrados)} envíos con código {codigo_venta}")

                        for fila in encontrados:
                            checkbox = fila.find_element(By.CSS_SELECTOR, "input.checks")
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", checkbox)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", checkbox)
                            time.sleep(0.3)

                        boton_imprimir = driver.find_element(By.ID, "mass_download")
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", boton_imprimir)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", boton_imprimir)
                        print("Z: Botón imprimir presionado")

                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div.modal-content"))
                        )
                        print("Z: Modal detectado")

                        boton_zpl = driver.find_element(
                            By.XPATH, "//div[contains(@class, 'option-card')][@data-format='zpl']"
                        )
                        driver.execute_script("arguments[0].click();", boton_zpl)
                        print("Z: Opción ZPL seleccionada")

                        boton_descargar = driver.find_element(By.XPATH, "//button[contains(., 'Descargar')]")
                        driver.execute_script("arguments[0].click();", boton_descargar)
                        print("Z: Botón descargar presionado")

                        estado = "Impreso"
                        print("Z: Etiqueta ZPL descargada correctamente para ", codigo_venta)
                    else:
                        print("Z: No se encontraron envíos para ", codigo_venta)
                        estado = "Error"

                    carpeta_descargas = os.path.join(os.path.expanduser("~"), "Downloads")
                    timeout = time.time() + 20
                    while not any(
                        f.endswith(".crdownload") or f.endswith(".zip") for f in os.listdir(carpeta_descargas)
                    ):
                        if time.time() > timeout:
                            print("Z: Timeout esperando descarga ZPL")
                            break
                        time.sleep(1)

                    time.sleep(1)
                    print("Z: Pestaña cerrada, Chrome base sigue abierto.")

                except Exception as e:  # noqa: BLE001
                    print("Z: Error durante impresión Zipnova:", e)
                    estado = "Error"

            else:
                filas = self._esperar_filas(driver, "table tbody tr, tr", timeout=10, min_text_len=2)
                objetivos = []

                for fila in filas:
                    try:
                        if codigo_venta in (fila.text or ""):
                            objetivos.append(fila)
                    except Exception:  # noqa: BLE001
                        continue

                if not objetivos:
                    print("E: No se encontraron filas para ", codigo_venta)
                    estado = "Error"
                    self.lbl_estado_impresion.setText("Error")
                    self.lbl_estado_impresion.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
                else:
                    print(f"E: Se encontraron {len(objetivos)} filas para {codigo_venta}")
                    for fila in objetivos:
                        try:
                            checkbox = fila.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                            if not checkbox.is_selected():
                                ActionChains(driver).move_to_element(checkbox).click().perform()
                                print("E: Checkbox marcado correctamente (click real)")
                            time.sleep(0.3)
                        except Exception as e:  # noqa: BLE001
                            print("E: Error marcando checkbox:", e)

                    try:
                        boton_print = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Reimprimir')]"))
                        )
                        print("E: Botón Reimprimir habilitado, intentando clic real...")
                        ActionChains(driver).move_to_element(boton_print).pause(0.2).click().perform()
                    except Exception as e:  # noqa: BLE001
                        print("E: Error al presionar Reimprimir:", e)
                        self.lbl_estado_impresion.setText("Error")
                        self.lbl_estado_impresion.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
                        return

                    try:
                        boton_zpl = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[.//span[normalize-space()='ZPL']]"))
                        )
                        print("E: Botón ZPL detectado, clic real...")
                        ActionChains(driver).move_to_element(boton_zpl).pause(0.2).click().perform()
                    except Exception as e:  # noqa: BLE001
                        print("E: No se encontró el botón ZPL:", e)
                        estado = "Error"
                        self.lbl_estado_impresion.setText("Error")
                        self.lbl_estado_impresion.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
                        return

                    download_dir = os.path.expanduser(r"C:\Users\bmonsalve\Downloads")
                    print("E: Esperando archivo ZPL en descargas...")

                    before_files = set(glob.glob(os.path.join(download_dir, "*.txt")))
                    start_time = time.time()
                    downloaded = False

                    while time.time() - start_time < 20:
                        current_files = set(glob.glob(os.path.join(download_dir, "*.txt")))
                        new_files = current_files - before_files
                        if new_files:
                            for file in new_files:
                                with open(file, "r", encoding="utf-8", errors="ignore") as handle:
                                    content = handle.read()
                                    if "^XA" in content or "ZPL" in content or "QZ" in content:
                                        print(f"Archivo ZPL detectado: {os.path.basename(file)}")
                                        downloaded = True
                                        break
                        if downloaded:
                            break
                        time.sleep(1)

                    if downloaded:
                        print("E: Etiqueta ZPL descargada correctamente para ", codigo_venta)
                        estado = "Impreso"
                        self.lbl_estado_impresion.setText("Impreso")
                        self.lbl_estado_impresion.setStyleSheet("color: green; font-weight: bold; font-size: 13px;")
                    else:
                        print("E: No se detectó descarga del archivo ZPL para ", codigo_venta)
                        estado = "Error"
                        self.lbl_estado_impresion.setText("Error")
                        self.lbl_estado_impresion.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")

            driver.close()
            driver.switch_to.window(base_handle)

        except Exception as e:  # noqa: BLE001
            print("Error en Selenium:", e)
            estado = "Error"

        etiquetas_path = os.path.join(self.config["carpeta_multivende"], "Etiquetas")
        os.makedirs(etiquetas_path, exist_ok=True)
        registro_path = os.path.join(etiquetas_path, "registro_impresiones.xlsx")

        df_registro = (
            pd.read_excel(registro_path)
            if os.path.exists(registro_path)
            else pd.DataFrame(columns=["CódigoVenta", "Fecha", "Estado"])
        )

        nuevo = pd.DataFrame(
            [[codigo_mostrado, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), estado]],
            columns=["CódigoVenta", "Fecha", "Estado"],
        )
        df_registro = pd.concat([df_registro, nuevo], ignore_index=True)
        df_registro.to_excel(registro_path, index=False)

        QTimer.singleShot(3000, lambda: self.lbl_estado_impresion.hide())
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

        movimientos_dir = os.path.join(self.config["carpeta_multivende"], "Movimientos")
        os.makedirs(movimientos_dir, exist_ok=True)
        movimientos_path = os.path.join(movimientos_dir, "movimientos.xlsx")

        columnas = ["Nota de Venta", "Codigo", "Cantidad", "Operador", "Fecha"]

        if os.path.exists(movimientos_path):
            df_mov = pd.read_excel(movimientos_path)
        else:
            df_mov = pd.DataFrame(columns=columnas)

        nuevas_filas = []
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for _, fila in self.df_tabla.iterrows():
            nuevas_filas.append(
                {
                    "Nota de Venta": codigo_venta,
                    "Codigo": fila["Código Producto"],
                    "Cantidad": int(fila["Escaneado"]),
                    "Operador": operador,
                    "Fecha": fecha_actual,
                }
            )

        df_mov = pd.concat([df_mov, pd.DataFrame(nuevas_filas, columns=columnas)], ignore_index=True)
        df_mov.to_excel(movimientos_path, index=False)

        QMessageBox.information(self, "Salida generada", "La salida fue registrada correctamente.")

    def cambiar_vista(self, esquema: bool):
        self.vista_esquema = esquema
        self.btn_tabla.setChecked(not esquema)
        self.btn_esquema.setChecked(esquema)

    def _esperar_filas(self, driver, css_selector="table tbody tr, tr", timeout=10, min_text_len=2):
        """Espera hasta timeout a que existan filas visibles con texto."""
        inicio = time.time()
        filas_visibles = []

        while time.time() - inicio < timeout:
            try:
                filas = driver.find_elements(By.CSS_SELECTOR, css_selector)
            except Exception:  # noqa: BLE001
                filas = []

            filas_visibles = []
            for fila in filas:
                try:
                    texto = (fila.text or "").strip()
                    if fila.is_displayed() and len(texto) >= min_text_len:
                        filas_visibles.append(fila)
                except StaleElementReferenceException:
                    continue

            if filas_visibles:
                print(f"E: Filas detectadas: {len(filas_visibles)} visibles.")
                return filas_visibles

            try:
                driver.execute_script("window.scrollBy(0, 200);")
            except Exception:  # noqa: BLE001
                pass

            time.sleep(0.25)

        print("E: No aparecieron filas dentro del tiempo de espera.")
        return filas_visibles
