import json
import os
import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QMenu, QMenuBar, QTabWidget

from tab_bodegas import BodegasTab
from tab_entradas import EntradasTab
from tab_movimientos import MovimientosTab
from tab_stock import StockTab
from tab_verificacion import VerificacionTab
from tab_multivende import MultivendeTab


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

        self.tabs.currentChanged.connect(self._enfocar_codigo_si_principal)

    def _crear_menu(self):
        barra = QMenuBar(self)
        menu_archivo = QMenu("Archivo", self)
        act_cargar = menu_archivo.addAction("Cargar Multivende (\u00faltimo archivo)")
        # Se conecta mas adelante cuando verificacion esta disponible.
        self.menu_accion_cargar = act_cargar
        barra.addMenu(menu_archivo)
        self.setMenuBar(barra)

    def _crear_tabs(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Se mantienen instanciados para no romper callbacks internos,
        # pero no se agregan al QTabWidget principal.
        self.multivende_tab = MultivendeTab(self)
        self.movimientos_tab = MovimientosTab(self.config, self)
        self.verificacion_tab = VerificacionTab(
            self.config,
            self,
            on_salida_generada=self.movimientos_tab.cargar_movimientos,
            on_carga_multivende=self.multivende_tab.set_data,
        )
        self.entradas_tab = EntradasTab(
            self.config,
            self,
            on_entrada_registrada=self.movimientos_tab.cargar_movimientos,
        )
        self.bodegas_tab = BodegasTab(self)
        self.stock_tab = StockTab(self.config, self)

        self.tabs.addTab(self.verificacion_tab, "Verificaci\u00f3n de pedidos")
        self.tabs.addTab(self.multivende_tab, "Datos Multivende")

        self.menu_accion_cargar.triggered.connect(self.verificacion_tab.cargar_excel)
        self.verificacion_tab.cargar_excel(mostrar_mensaje=False)
        self._enfocar_codigo_si_principal(self.tabs.currentIndex())

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
