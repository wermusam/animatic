import sys
import os

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QWidget,
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLineEdit,
    QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from engine import AnimaticEngine
from typing import Optional


class AnimaticCreator(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pirates Animatic")
        self.resize(800, 600)
        self.setAcceptDrops(True)

        self.image_path: Optional[str] = None
        self.audio_path: Optional[str] = None
        self.output_path: Optional[str] = None
        self.engine: AnimaticEngine = AnimaticEngine()

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.layout.setSpacing(20)
        self.layout.setContentsMargins(40, 40, 40, 40)

        self.title_label = QLabel("Pirate Animatic")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(
            "font-size: 32px; font-weight: bold; color: #ff3366;"
        )
        self.layout.addWidget(self.title_label)

        self.label = QLabel(
            "RRRR Matey!!\n Drag 'n Drop the goods here!\n (Image then Audio please)"
        )
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setObjectName("DropLabel")
        self.layout.addWidget(self.label)

        self.status_label = QLabel("Image: None | Audio: None")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #888; font-size: 14px;")
        self.layout.addWidget(self.status_label)

        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("Enter Duration (seconds), e.g. 5.0")
        self.duration_input.setObjectName("InputBox")
        self.layout.addWidget(self.duration_input)

        self.output_row = QHBoxLayout()
        self.output_path_input = QLineEdit()
        self.output_path_input.setPlaceholderText("Save location will appear here...")
        self.output_path_input.setObjectName("InputBox")
        self.browse_btn = QPushButton("📁")
        self.browse_btn.setFixedWidth(40)
        self.browse_btn.setObjectName("BrowseBtn")
        self.browse_btn.clicked.connect(self.browse_output_path)
        self.output_row.addWidget(self.output_path_input)
        self.output_row.addWidget(self.browse_btn)
        self.layout.addLayout(self.output_row)

        self.render_btn = QPushButton("Generate Animatic")
        self.render_btn.setObjectName("ActionBtn")
        self.render_btn.clicked.connect(self.create_video)
        self.layout.addWidget(self.render_btn)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".png", ".jpg", ".jpeg"]:
                self.image_path = file_path
                if not self.output_path:
                    default_name = os.path.splitext(os.path.basename(file_path))[0]
                    self.output_path_input.setText(
                        os.path.join(
                            os.path.dirname(file_path), f"{default_name}_video.mp4"
                        )
                    )
                self.label.setText(f"Loaded Image: {os.path.basename(file_path)}")
                self.label.setStyleSheet("border-color: #00ff00;")
            elif ext in [".mp3", ".wav", ".m4a"]:
                self.audio_path = file_path
                self.label.setText(f"Loaded Audio: {os.path.basename(file_path)}")
                self.label.setStyleSheet("border-color: #33ccff;")
            else:
                self.label.setText("Invalid File Type")
                self.label.setStyleSheet("border-color: #ff3366;")
            img_name = os.path.basename(self.image_path) if self.image_path else "None"
            aud_name = os.path.basename(self.audio_path) if self.audio_path else "None"
            self.status_label.setText(f"Image: {img_name}  |  Audio: {aud_name}")

    def browse_output_path(self) -> None:
        """Opens a save dialog so the user can choose where to save the video."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Video As", "", "MP4 Files (*.mp4)"
        )
        if path:
            self.output_path = path
            self.output_path_input.setText(path)

    def create_video(self) -> None:
        """Handles the UI logic for gathering paths and triggering the render engine."""
        if not self.image_path:
            QMessageBox.warning(self, "Error", "Please drag an image in first!")
            return

        if self.output_path:
            output_path = self.output_path
        else:
            folder: str = os.path.dirname(self.image_path)
            filename: str = os.path.splitext(os.path.basename(self.image_path))[0]
            output_path = os.path.join(folder, f"{filename}_video.mp4")

        self.label.setText("Rendering...")
        QApplication.processEvents()

        try:
            self.engine.generate_video(
                image_path=self.image_path,
                output_path=output_path,
                audio_path=self.audio_path,
            )

            self.label.setText(f"Success! Saved to:\n{output_path}")
            QMessageBox.information(self, "Success", f"Video created!\n{output_path}")

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"An error occurred during render:\n{e}"
            )

    def _apply_styles(self) -> None:
        dark_bg = "#1e1e1e"
        text_color = "#ffffff"
        accent_pink = "#ff3366"
        style_sheet = f"""
            QMainWindow {{ background-color: {dark_bg}; }}
            QWidget {{ color: {text_color}; font-family: 'Segoe UI', 'Roboto', sans-serif; font-size: 14px; }}
            QLineEdit#InputBox {{ padding: 10px; border: 2px solid #444; border-radius: 5px; background-color: #2d2d2d; font-size: 16px; color: white; }}
            QPushButton#ActionBtn {{ background-color: {accent_pink}; color: white; border: none; padding: 15px; border-radius: 5px; font-weight: bold; font-size: 16px; }}
            QPushButton#ActionBtn:hover {{ background-color: #ff6688; }}
            QPushButton#BrowseBtn {{ background-color: #2d2d2d; border: 2px solid #444; border-radius: 5px; font-size: 18px; }}
            QLabel#DropLabel {{ border: 2px dashed {accent_pink}; border-radius: 10px; background-color: #2d2d2d; font-size: 24px; color: #aaa; }}
            QMessageBox {{ background-color: #2d2d2d; }}
            QMessageBox QLabel {{ color: white; }}
            QMessageBox QPushButton {{ background-color: {accent_pink}; color: white; border-radius: 3px; padding: 5px 15px; }}
        """
        self.setStyleSheet(style_sheet)


def main() -> None:
    app = QApplication(sys.argv)
    window = AnimaticCreator()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
