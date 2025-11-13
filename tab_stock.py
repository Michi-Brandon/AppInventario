from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StockTab(QWidget):
    """Pestaña temporal para consultas de stock."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Sección en construcción: stock de productos."))
        layout.addStretch()
        self.setLayout(layout)

