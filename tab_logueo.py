import socket
import subprocess
import time
import webbrowser

from PyQt6.QtWidgets import (
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)


class LogueoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        lbl_info = QLabel("Usa estos botones para abrir los navegadores y loguearte manualmente.")
        lbl_info.setStyleSheet("font-weight: bold; color: #333; margin-bottom: 8px;")
        layout.addWidget(lbl_info)

        self.perfiles = {
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

        btn_todos = QPushButton("Abrir todas las páginas")
        btn_todos.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold; padding: 6px;")
        btn_todos.clicked.connect(self.abrir_todos_los_perfiles)
        layout.addWidget(btn_todos)

        botones = [
            ("Mercado Libre", "mercadolibre"),
            ("Walmart (Envíame)", "walmart"),
            ("París (Envíame)", "paris"),
            ("Ripley (Envíame)", "ripley"),
            ("WooCommerce (Zipnova)", "woocommerce"),
        ]

        fila_botones = QHBoxLayout()
        for texto, clave in botones:
            btn = QPushButton(texto)
            btn.setStyleSheet("padding: 6px; font-weight: 500;")
            btn.clicked.connect(lambda _, k=clave: self.abrir_perfil(k))
            fila_botones.addWidget(btn)

        layout.addLayout(fila_botones)
        layout.addStretch()
        self.setLayout(layout)

    def abrir_perfil(self, clave):
        """Abre una ventana Chrome para el perfil indicado."""
        if clave not in self.perfiles:
            print(f"[Error] Perfil '{clave}' no encontrado.")
            return

        user_data_dir, port, url_base = self.perfiles[clave]
        chrome_path = r"C:\Users\bmonsalve\AppData\Local\Google\Chrome\Application\chrome.exe"

        def puerto_abierto(puerto):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                sock.connect(("127.0.0.1", puerto))
                sock.close()
                return True
            except Exception:  # noqa: BLE001
                return False

        if not puerto_abierto(port):
            print(f"Iniciando Chrome perfil '{clave}' en puerto {port}...")
            subprocess.Popen(
                [
                    chrome_path,
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={user_data_dir}",
                    url_base,
                ]
            )
        else:
            print(f"Chrome ya abierto para '{clave}', abriendo nueva pestaña...")
            webbrowser.open(url_base)

    def abrir_todos_los_perfiles(self):
        """Abre todos los perfiles de Chrome configurados."""
        for clave in self.perfiles.keys():
            self.abrir_perfil(clave)
            time.sleep(1)

