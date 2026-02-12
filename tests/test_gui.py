import sys
import os
from unittest.mock import patch, MagicMock
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QMimeData, QUrl, Qt, QPointF
from PySide6.QtGui import QDropEvent
from src.animatic.main_window import AnimaticCreator

@pytest.fixture
def app(qtbot):
    test_app = QApplication.instance()
    if test_app is None:
        test_app = QApplication(sys.argv)
    return test_app

@pytest.fixture
def window(qtbot):
    win = AnimaticCreator()
    qtbot.addWidget(win)
    return win

def test_initial_state(window):
    """Check that variables are empty at start."""
    assert window.image_path is None
    assert window.audio_path is None
    assert "Drag 'n Drop" in window.label.text()

def test_drop_image(window):
    """Simulate dropping an image file."""
    mime_data = QMimeData()
    fake_url = QUrl.fromLocalFile("C:/fake/path/test_image.png")
    mime_data.setUrls([fake_url])
    
    event = QDropEvent(
        QPointF(0, 0), 
        Qt.DropAction.CopyAction, 
        mime_data, 
        Qt.MouseButton.LeftButton, 
        Qt.KeyboardModifier.NoModifier 
    )

    window.dropEvent(event)

    assert window.image_path.replace("\\", "/") == "C:/fake/path/test_image.png"
    assert "Loaded Image" in window.label.text()

def test_drop_audio(window):
    """Simulate dropping an audio file."""
    mime_data = QMimeData()
    fake_url = QUrl.fromLocalFile("C:/fake/path/test_audio.mp3")
    mime_data.setUrls([fake_url])
    
    event = QDropEvent(
        QPointF(0, 0), 
        Qt.DropAction.CopyAction, 
        mime_data, 
        Qt.MouseButton.LeftButton, 
        Qt.KeyboardModifier.NoModifier
    )

    window.dropEvent(event)

    assert window.audio_path.replace("\\", "/") == "C:/fake/path/test_audio.mp3"
    assert "Loaded Audio" in window.label.text()


@patch('src.animatic.main_window.QMessageBox.information') 
@patch('subprocess.run')
@patch('src.animatic.main_window.get_ffmpeg_exe')
def test_render_command(mock_get_ffmpeg, mock_subprocess, mock_popup, window):
    """
    Verify that the 'Generate' button constructs the correct FFmpeg command
    WITHOUT actually running FFmpeg OR showing a popup.
    """
    window.image_path = "C:/test/image.png"
    window.audio_path = "C:/test/audio.mp3"
    
    mock_get_ffmpeg.return_value = "ffmpeg_mock.exe"

    window.create_video()

    args, _ = mock_subprocess.call_args
    command_list = args[0]
    assert command_list[0] == "ffmpeg_mock.exe"
    assert "-loop" in command_list
    assert "-shortest" in command_list
    assert any("image.png" in arg for arg in command_list)

    mock_popup.assert_called_once()