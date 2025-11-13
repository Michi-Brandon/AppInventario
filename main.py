import json
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QMenu, QMenuBar, QTabWidget

from tab_bodegas import BodegasTab
from tab_entradas import EntradasTab
from tab_logueo import LogueoTab
from tab_movimientos import MovimientosTab
from tab_stock import StockTab
from tab_verificacion import VerificacionTab


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Verificador de Pedidos - AuraHome")
        self.resize(1200, 700)

        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.abspath(os.path.dirname(sys.argv[0]))

        config_path = os.path.join(base_path, "config.json")

        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                self.config = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"No se pudo abrir config.json\n{config_path}\n\n{str(exc)}")
            sys.exit(1)

        self._crear_menu()
        self._crear_tabs()
        self._configurar_actualizacion()

        self.tabs.currentChanged.connect(self._enfocar_codigo_si_principal)

    def _crear_menu(self):
        barra = QMenuBar(self)
        menu_archivo = QMenu("Archivo", self)
        act_cargar = menu_archivo.addAction("Cargar Multivende (último archivo)")
        # Se conecta más adelante cuando verificación está disponible.
        self.menu_accion_cargar = act_cargar
        barra.addMenu(menu_archivo)
        self.setMenuBar(barra)

    def _crear_tabs(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.movimientos_tab = MovimientosTab(self.config, self)
        self.verificacion_tab = VerificacionTab(
            self.config,
            self,
            on_salida_generada=self.movimientos_tab.cargar_movimientos,
        )
        self.entradas_tab = EntradasTab(
            self.config,
            self,
            on_entrada_registrada=self.movimientos_tab.cargar_movimientos,
        )
        self.bodegas_tab = BodegasTab(self)
        self.stock_tab = StockTab(self.config, self)
        self.logueo_tab = LogueoTab(self)

        self.tabs.addTab(self.verificacion_tab, "Verificación de pedidos")
        self.tabs.addTab(self.movimientos_tab, "Movimientos del día")
        self.tabs.addTab(self.entradas_tab, "Entradas de productos")
        self.tabs.addTab(self.bodegas_tab, "Movimientos entre bodegas")
        self.tabs.addTab(self.stock_tab, "Stock de productos")
        self.tabs.addTab(self.logueo_tab, "Logueo a páginas")

        self.menu_accion_cargar.triggered.connect(self.verificacion_tab.cargar_excel)
        self.verificacion_tab.cargar_excel(mostrar_mensaje=True)
        self._enfocar_codigo_si_principal(self.tabs.currentIndex())

    def _configurar_actualizacion(self):
        self.timer_actualizacion = QTimer(self)
        self.timer_actualizacion.timeout.connect(lambda: self.verificacion_tab.cargar_excel(mostrar_mensaje=False))
        self.timer_actualizacion.start(60_000)

    def _enfocar_codigo_si_principal(self, index):  # noqa: ARG002
        es_verificacion = self.tabs.currentWidget() is self.verificacion_tab
        self.verificacion_tab.configurar_foco_codigo(es_verificacion)
        if es_verificacion:
            self.verificacion_tab.enfocar_codigo_si_principal()
        if self.tabs.currentWidget() is self.stock_tab:
            self.stock_tab.actualizar_stock()
            self.stock_tab.enfocar_busqueda()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ventana = VentanaPrincipal()
    ventana.show()
    sys.exit(app.exec())
