import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QWidget, 
                               QVBoxLayout, QPushButton, QLineEdit, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from moviepy import ImageClip

class AnimaticCreator(QMainWindow):
    """
    The main application window for the Pirates Animatic tool.
    Allows dragging an image, setting a duration, and saving as MP4.
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Pirates Animatic")
        self.resize(800, 600)
        self.setAcceptDrops(True)

        self.image_path = None

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Initialize all UI widgets and layouts"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        self.layout = QVBoxLayout(central_widget)
        self.layout.setSpacing(20)
        self.layout.setContentsMargins(40, 40, 40, 40)


        self.label = QLabel("Drag and Drop an Image Here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setObjectName("DropLabel")
        self.layout.addWidget(self.label)

        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("Enter Duration (seconds), e.g. 5.0")
        self.duration_input.setObjectName("InputBox")
        self.layout.addWidget(self.duration_input)

        self.render_btn = QPushButton("Create Video")
        self.render_btn.setObjectName("ActionBtn")
        self.render_btn.clicked.connect(self.create_video) 
        self.layout.addWidget(self.render_btn)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept dragging if it contains a file."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle the file drop."""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ['.png', '.jpg', '.jpeg']:
                self.image_path = file_path
                self.label.setText(f"Loaded: {os.path.basename(file_path)}")
                self.label.setStyleSheet("border-color: #00ff00;") 
            else:
                self.label.setText("Please drop an Image (.png or .jpg)")
                self.label.setStyleSheet("border-color: #ff3366;")
    def create_video(self) -> None:
        """The Logic: Uses MoviePy to convert image to video."""
        if not self.image_path:
            QMessageBox.warning(self, "Error", "Please drag an image in first!")
            return
        
        try:
            duration = float(self.duration_input.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter a valid number for duration (e.g. 5)")
            return

        folder = os.path.dirname(self.image_path)
        filename = os.path.splitext(os.path.basename(self.image_path))[0]
        output_path = os.path.join(folder, f"{filename}_video.mp4")

        self.label.setText("Rendering... Please Wait...")
        QApplication.processEvents() 

        try:
            clip = ImageClip(self.image_path)
            clip = clip.with_duration(duration)
            clip.fps = 24
            
            clip.write_videofile(output_path, codec="libx264", audio=False)

            self.label.setText(f"Success! Saved to:\n{output_path}")
            QMessageBox.information(self, "Success", f"Video created!\n{output_path}")

        except Exception as e:
            self.label.setText(f"Error: {str(e)}")
            print(f"Error details: {e}")

    def _apply_styles(self) -> None:
        """Apply the Dark & Pink Theme."""
        dark_bg = "#1e1e1e"
        text_color = "#ffffff"
        accent_pink = "#ff3366" 

        style_sheet = f"""
            QMainWindow {{ background-color: {dark_bg}; }}
            QWidget {{ 
                color: {text_color}; 
                font-family: 'Segoe UI', 'Roboto', sans-serif; 
                font-size: 14px; 
            }}
            /* Styling for the Input Box */
            QLineEdit#InputBox {{
                padding: 10px;
                border: 2px solid #444;
                border-radius: 5px;
                background-color: #2d2d2d;
                font-size: 16px;
                color: white;
            }}
            /* Styling for the Button */
            QPushButton#ActionBtn {{
                background-color: {accent_pink};
                color: white;
                border: none;
                padding: 15px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 16px;
            }}
            QPushButton#ActionBtn:hover {{
                background-color: #ff6688;
            }}
            /* Styling for the Drop Zone */
            QLabel#DropLabel {{
                border: 2px dashed {accent_pink};
                border-radius: 10px;
                background-color: #2d2d2d;
                font-size: 24px;
                color: #aaa;
            }}
        """
        self.setStyleSheet(style_sheet)

def main() -> None:
    app = QApplication(sys.argv)
    window = AnimaticCreator()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()