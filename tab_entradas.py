from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EntradasTab(QWidget):
    """Pestaña temporal para controlar las entradas de productos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Sección en construcción: entradas de productos."))
        layout.addStretch()
        self.setLayout(layout)

