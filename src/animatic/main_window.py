import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout
from PySide6.QtCore import Qt

class AnimaticCreator(QMainWindow):
    """
    THe main application window for the Animatic Creator tool.
    Inherits from QMainWindow to provide a standard application layout.
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Animatic Creator")
        self.resize(800, 600)

        self.setAcceptDrops(True)

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Initialize all UI widgets and layouts"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.label = QLabel("Drag and Drop images here RRRR")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setObjectName("DropLabel")

        layout.addWidget(self.label)

    def _apply_styles(self) -> None:
        """
        Apply a global QSS (Qt Style Sheet) to mimic the dark VFX tool look.
        """

        dark_bg = "#1e1e1e"
        text_color = "#ffffff"
        accent_pink = "#ff3366" 

        style_sheet = f"""
            QMainWindow {{
                background-color: {dark_bg};
            }}
            QWidget {{
                color: {text_color};
                font-family: 'Segoe UI', 'Roboto', sans-serif;
                font-size: 14px;
            }}
            /* Specific styling for our Drop Label to show the accent color */
            QLabel#DropLabel {{
                border: 2px dashed {accent_pink};
                border-radius: 10px;
                background-color: #2d2d2d;
                font-size: 24px;
                color: #888;
            }}
        """
        self.setStyleSheet(style_sheet)

def main() -> None:
    "Entry point for the application."
    app = QApplication(sys.argv)

    window = AnimaticCreator()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()