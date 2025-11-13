from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class MovimientosTab(QWidget):
    """Pestaña temporal para futuros reportes de movimientos del día."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Sección en construcción: movimientos del día."))
        layout.addStretch()
        self.setLayout(layout)

