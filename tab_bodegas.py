from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class BodegasTab(QWidget):
    """Pestaña temporal para movimientos entre bodegas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Sección en construcción: movimientos entre bodegas."))
        layout.addStretch()
        self.setLayout(layout)

