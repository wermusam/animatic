import sys
from unittest.mock import patch
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QMimeData, QUrl, Qt, QPointF
from PySide6.QtGui import QDropEvent
from main_window import AnimaticCreator


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
        Qt.KeyboardModifier.NoModifier,
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
        Qt.KeyboardModifier.NoModifier,
    )

    window.dropEvent(event)

    assert window.audio_path.replace("\\", "/") == "C:/fake/path/test_audio.mp3"
    assert "Loaded Audio" in window.label.text()


@patch("src.animatic.main_window.QMessageBox.information")
@patch("subprocess.run")
def test_render_command(mock_subprocess, mock_popup, window):
    """
    Verify that the 'Generate' button constructs the correct FFmpeg command
    WITHOUT actually running FFmpeg OR showing a popup.
    """
    window.image_path = "C:/test/image.png"
    window.audio_path = "C:/test/audio.mp3"

    window.create_video()

    assert mock_subprocess.called

    args, _ = mock_subprocess.call_args
    command_list = args[0]

    assert "-loop" in command_list
    assert "-shortest" in command_list

    assert any("image.png" in arg for arg in command_list)

    mock_popup.assert_called_once()


def test_drop_image_sets_default_output_path(window):
    """When an image is dropped, the output path field should auto-populate."""
    mime_data = QMimeData()
    fake_url = QUrl.fromLocalFile("C:/fake/path/test_image.png")
    mime_data.setUrls([fake_url])

    event = QDropEvent(
        QPointF(0, 0),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    window.dropEvent(event)

    assert "test_image_video.mp4" in window.output_path_input.text().replace("\\", "/")


def test_browse_sets_output_path(window):
    """When browse dialog returns a path, it should be stored and shown."""
    with patch(
        "main_window.QFileDialog.getSaveFileName",
        return_value=("C:/chosen/output.mp4", ""),
    ):
        window.browse_output_path()

    assert window.output_path == "C:/chosen/output.mp4"
    assert window.output_path_input.text() == "C:/chosen/output.mp4"


def test_existing_output_path_not_overwritten(window):
    """If user already chose a save path, dropping an image should not overwrite it."""
    window.output_path = "C:/my/chosen/path.mp4"

    mime_data = QMimeData()
    fake_url = QUrl.fromLocalFile("C:/fake/path/test_image.png")
    mime_data.setUrls([fake_url])

    event = QDropEvent(
        QPointF(0, 0),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    window.dropEvent(event)

    assert window.output_path == "C:/my/chosen/path.mp4"
