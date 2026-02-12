import sys
import os
import subprocess
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QWidget, 
                               QVBoxLayout, QPushButton, QLineEdit, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage
from imageio_ffmpeg import get_ffmpeg_exe 

class AnimaticCreator(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pirates Animatic")
        self.resize(800, 600)
        self.setAcceptDrops(True)
        self.image_path = None
        self.audio_path = None
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
        self.title_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #ff3366;")
        self.layout.addWidget(self.title_label)

        self.label = QLabel("RRRR Matey!!\n Drag 'n Drop the goods here!\n (Image then Audio please)")
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
            if ext in ['.png', '.jpg', '.jpeg']:
                self.image_path = file_path
                self.label.setText(f"Loaded Image: {os.path.basename(file_path)}")
                self.label.setStyleSheet("border-color: #00ff00;")
            elif ext in ['.mp3', '.wav', '.m4a']:
                self.audio_path = file_path
                self.label.setText(f"Loaded Audio: {os.path.basename(file_path)}")
                self.label.setStyleSheet("border-color: #33ccff;")
            else:
                self.label.setText("Invalid File Type")
                self.label.setStyleSheet("border-color: #ff3366;")
            img_name = os.path.basename(self.image_path) if self.image_path else "None"
            aud_name = os.path.basename(self.audio_path) if self.audio_path else "None"
            self.status_label.setText(f"Image: {img_name}  |  Audio: {aud_name}")

    def create_video(self) -> None:
        if not self.image_path:
            QMessageBox.warning(self, "Error", "Please drag an image in first!")
            return

        folder = os.path.dirname(self.image_path)
        filename = os.path.splitext(os.path.basename(self.image_path))[0]
        output_path = os.path.join(folder, f"{filename}_video.mp4")
        
        self.label.setText("Optimizing Image...")
        QApplication.processEvents()
        
        input_image_arg = self.image_path
        temp_image_path = None

        try:
            img = QImage(self.image_path)
            # If image is bigger than 1080p, resize it now
            if img.height() > 1080:
                img = img.scaledToHeight(1080, Qt.TransformationMode.SmoothTransformation)
                temp_image_path = os.path.join(folder, "temp_fast_render.jpg")
                img.save(temp_image_path, "JPG")
                input_image_arg = temp_image_path
        except Exception as e:
            print(f"Warning: Image optimization failed, using original. {e}")

        ffmpeg_exe = get_ffmpeg_exe()
        print(f"DEBUG: Using FFmpeg at: {ffmpeg_exe}")

        cmd = [ffmpeg_exe, "-y"]
        cmd.extend(["-loop", "1", "-i", input_image_arg])

        if self.audio_path:
            cmd.extend(["-i", self.audio_path])
            cmd.extend(["-shortest"])
        else:
            try:
                duration = float(self.duration_input.text())
                cmd.extend(["-t", str(duration)])
            except ValueError:
                QMessageBox.warning(self, "Error", "Please enter a valid duration.")
                return

        cmd.extend([
            "-c:v", "libx264", 
            "-preset", "ultrafast",   
            "-tune", "stillimage",
            "-c:a", "copy",       
            "-pix_fmt", "yuv420p"
        ])

        cmd.append(output_path)

        self.label.setText("Rendering...")
        QApplication.processEvents()

        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            subprocess.run(cmd, check=True, startupinfo=startupinfo)
            
            self.label.setText(f"Success! Saved to:\n{output_path}")
            QMessageBox.information(self, "Success", f"Video created!\n{output_path}")

        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "FFmpeg not found! Please install FFmpeg.")
        except subprocess.CalledProcessError:
            QMessageBox.critical(self, "Error", "FFmpeg failed to create the video.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred:\n{e}")
        finally:
            if temp_image_path and os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                except:
                    pass

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