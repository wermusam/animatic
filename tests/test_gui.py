"""Tests for the multi-panel AnimaticCreator GUI."""

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QMimeData, QUrl, Qt, QPointF, QEvent
from PySide6.QtGui import QDropEvent, QImage, QKeyEvent

from animatic.main_window import AnimaticCreator


@pytest.fixture
def app(qtbot):
    """Ensure a QApplication exists."""
    test_app = QApplication.instance()
    if test_app is None:
        test_app = QApplication(sys.argv)
    return test_app


@pytest.fixture
def window(qtbot):
    """Create a fresh AnimaticCreator window."""
    win = AnimaticCreator()
    qtbot.addWidget(win)
    return win


@pytest.fixture
def temp_images(tmp_path):
    """Create small temporary PNG files for testing.

    Returns:
        A list of 3 image file paths.
    """
    paths = []
    for i in range(3):
        img = QImage(10, 10, QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.red)
        path = str(tmp_path / f"panel{i + 1}.png")
        img.save(path)
        paths.append(path)
    return paths


@pytest.fixture
def temp_audio(tmp_path):
    """Create a temporary audio file path for testing.

    Returns:
        A path to a fake .mp3 file (empty but exists on disk).
    """
    path = str(tmp_path / "dialogue.mp3")
    with open(path, "wb") as f:
        f.write(b"\x00" * 100)
    return path


def _make_drop_event(file_paths: list[str]) -> tuple[QDropEvent, QMimeData]:
    """Create a QDropEvent with the given file paths.

    Returns both the event and mime data so the mime data
    doesn't get garbage collected before dropEvent uses it.

    Args:
        file_paths: List of file paths to include in the drop.

    Returns:
        A tuple of (QDropEvent, QMimeData).
    """
    mime_data = QMimeData()
    urls = [QUrl.fromLocalFile(p) for p in file_paths]
    mime_data.setUrls(urls)
    event = QDropEvent(
        QPointF(0, 0),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    return event, mime_data


class TestInitialState:
    """Tests for the window's initial state."""

    def test_empty_project(self, window: AnimaticCreator) -> None:
        """New window should have an empty project."""
        assert len(window.project.panels) == 0
        assert window.project.audio_path is None

    def test_drop_zone_text(self, window: AnimaticCreator) -> None:
        """Main display should show the drop prompt."""
        assert "Drop" in window.main_display.text() or "Add Images" in window.main_display.text()

    def test_buttons_disabled(self, window: AnimaticCreator) -> None:
        """Play, stop, export, remove should be disabled with no panels."""
        assert not window.play_btn.isEnabled()
        assert not window.stop_btn.isEnabled()
        assert not window.export_btn.isEnabled()
        assert not window.remove_btn.isEnabled()


class TestDropImages:
    """Tests for dragging and dropping images."""

    def test_drop_single_image(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Dropping one image should create one panel."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        assert len(window.project.panels) == 1
        assert window.panel_strip.count() == 1

    def test_drop_multiple_images(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Dropping multiple images should create a panel for each."""
        event, _mime = _make_drop_event(temp_images)
        window.dropEvent(event)

        assert len(window.project.panels) == 3
        assert window.panel_strip.count() == 3

    def test_drop_image_enables_buttons(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Buttons should be enabled after adding a panel."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        assert window.play_btn.isEnabled()
        assert window.export_btn.isEnabled()

    def test_drop_sets_default_output_path(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """First image drop should auto-populate the output path."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        output_text = window.output_path_input.text()
        assert "animatic_" in output_text
        assert output_text.endswith(".mp4")

    def test_existing_output_not_overwritten(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """User-set output path should not be overwritten by new drops."""
        window.output_path_input.setText("C:/my/chosen/path.mp4")

        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        assert window.output_path_input.text() == "C:/my/chosen/path.mp4"

    def test_panel_strip_shows_duration(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Panel strip items should show the default duration."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        item = window.panel_strip.item(0)
        assert "3.0s" in item.text()


class TestDropAudio:
    """Tests for dragging and dropping audio files."""

    def test_drop_audio(self, window: AnimaticCreator, temp_audio: str) -> None:
        """Dropping audio should set the project audio path."""
        event, _mime = _make_drop_event([temp_audio])
        window.dropEvent(event)

        assert window.project.audio_path is not None
        assert "dialogue.mp3" in window.project.audio_path

    def test_audio_label_updates(self, window: AnimaticCreator, temp_audio: str) -> None:
        """Audio label should show the filename after drop."""
        event, _mime = _make_drop_event([temp_audio])
        window.dropEvent(event)

        assert "dialogue" in window.panel_audio_label.text()

    def test_invalid_file_ignored(self, window: AnimaticCreator, tmp_path) -> None:
        """Dropping an unsupported file type should not add panels or audio."""
        txt_path = str(tmp_path / "readme.txt")
        with open(txt_path, "w") as f:
            f.write("hello")

        event, _mime = _make_drop_event([txt_path])
        window.dropEvent(event)

        assert len(window.project.panels) == 0
        assert window.project.audio_path is None


class TestPanelControls:
    """Tests for panel selection, duration editing, and removal."""

    def test_duration_edit_updates_panel(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Changing the duration spinbox should update the selected panel."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        window.duration_spin.setValue(5.5)

        assert window.project.panels[0].duration == 5.5

    def test_duration_edit_updates_strip_label(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Changing duration should update the strip item text."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        window.duration_spin.setValue(7.0)

        item = window.panel_strip.item(0)
        assert "7.0s" in item.text()

    def test_remove_panel(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Removing a panel should update both project and strip."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window.panel_strip.setCurrentRow(0)
        window._remove_selected_panel()

        assert len(window.project.panels) == 1
        assert window.panel_strip.count() == 1

    def test_remove_last_panel_disables_buttons(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Removing all panels should disable buttons and show drop text."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        window._remove_selected_panel()

        assert not window.play_btn.isEnabled()
        assert not window.export_btn.isEnabled()
        assert "Drop" in window.main_display.text() or "Add Images" in window.main_display.text()

    def test_total_duration_label(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Total duration label should reflect all panel durations."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        assert "6.0s" in window.total_label.text()
        assert "2 panels" in window.total_label.text()


class TestExport:
    """Tests for the export workflow."""

    @patch("animatic.main_window.QMessageBox.information")
    def test_export_calls_engine(
        self, mock_popup, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """Export should invoke FFmpeg via background thread."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)
        window.output_path_input.setText("C:/fake/output.mp4")

        mock_proc = MagicMock()
        mock_proc.stderr = iter([])
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            window._export_video()
            window._export_thread.wait(5000)
            QApplication.processEvents()

        mock_popup.assert_called_once()

    def test_export_no_panels_warns(self, window: AnimaticCreator) -> None:
        """Export with no panels should show a warning."""
        with patch("animatic.main_window.QMessageBox.warning") as mock_warn:
            window._export_video()
            mock_warn.assert_called_once()


class TestBrowse:
    """Tests for the browse output path dialog."""

    def test_browse_sets_output_path(self, window: AnimaticCreator) -> None:
        """Browse dialog result should update the output path."""
        with patch(
            "animatic.main_window.QFileDialog.getSaveFileName",
            return_value=("C:/chosen/output.mp4", ""),
        ):
            window.browse_output_path()

        assert window.project.output_path == "C:/chosen/output.mp4"
        assert window.output_path_input.text() == "C:/chosen/output.mp4"


class TestPanelNotes:
    """Tests for panel notes/dialogue."""

    def test_notes_input_updates_panel(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Typing in the notes field should update the panel's notes."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        window.notes_input.setText("Hero enters the cave")
        assert window.project.panels[0].notes == "Hero enters the cave"

    def test_notes_populated_on_select(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Selecting a panel should populate the notes field."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window.project.panels[0].notes = "Panel one notes"
        window.project.panels[1].notes = "Panel two notes"

        window.panel_strip.setCurrentRow(0)
        assert window.notes_input.text() == "Panel one notes"

        window.panel_strip.setCurrentRow(1)
        assert window.notes_input.text() == "Panel two notes"


class TestRemoveAudio:
    """Tests for removing audio from a panel."""

    def test_remove_audio_clears_panel(self, window: AnimaticCreator, temp_images: list[str], temp_audio: str) -> None:
        """Remove audio button should clear the panel's audio path."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        # Set audio on the panel
        audio_event, _audio_mime = _make_drop_event([temp_audio])
        window.dropEvent(audio_event)
        assert window.project.panels[0].audio_path is not None

        window._remove_panel_audio()
        assert window.project.panels[0].audio_path is None
        assert "None" in window.panel_audio_label.text()

    def test_remove_audio_button_disabled_when_no_audio(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Remove audio button should be disabled when panel has no audio."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)
        assert not window.remove_audio_btn.isEnabled()


class TestDuplicate:
    """Tests for panel duplication."""

    def test_duplicate_adds_panel(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Duplicating should add a new panel to project and strip."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        window._duplicate_selected_panel()

        assert len(window.project.panels) == 2
        assert window.panel_strip.count() == 2
        assert window.project.panels[0].image_path == window.project.panels[1].image_path

    def test_duplicate_preserves_duration(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Duplicated panel should have the same duration."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)
        window.duration_spin.setValue(7.5)

        window._duplicate_selected_panel()
        assert window.project.panels[1].duration == 7.5

    def test_duplicate_inserts_after_selected(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Duplicate should insert after the selected panel, not at the end."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window.panel_strip.setCurrentRow(0)
        window._duplicate_selected_panel()

        assert len(window.project.panels) == 3
        assert window.project.panels[0].image_path == window.project.panels[1].image_path

    def test_duplicate_updates_total(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Total duration should update after duplication."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        window._duplicate_selected_panel()
        assert "6.0s" in window.total_label.text()


class TestSaveLoad:
    """Tests for project save/load."""

    def test_save_creates_file(self, window: AnimaticCreator, temp_images: list[str], tmp_path) -> None:
        """Saving should create an .animatic file."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)
        window.project.panels[0].notes = "Test note"

        path = str(tmp_path / "test.animatic")
        with patch(
            "animatic.main_window.QFileDialog.getSaveFileName",
            return_value=(path, ""),
        ):
            window._save_project()

        assert os.path.exists(path)

    def test_load_restores_panels(self, window: AnimaticCreator, temp_images: list[str], tmp_path) -> None:
        """Loading should restore panels into the UI."""
        # Create and save a project
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)
        window.project.panels[0].notes = "Restored note"

        path = str(tmp_path / "test.animatic")
        window.project.save(path)

        # Create a fresh window and load
        fresh = AnimaticCreator()
        fresh._load_project(path)

        assert len(fresh.project.panels) == 2
        assert fresh.panel_strip.count() == 2
        assert fresh.project.panels[0].notes == "Restored note"

    def test_drop_animatic_file(self, window: AnimaticCreator, temp_images: list[str], tmp_path) -> None:
        """Dropping an .animatic file should load the project."""
        # Save a project first
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)
        path = str(tmp_path / "test.animatic")
        window.project.save(path)

        # Drop the .animatic file onto a fresh window
        fresh = AnimaticCreator()
        drop_event, _drop_mime = _make_drop_event([path])
        fresh.dropEvent(drop_event)

        assert len(fresh.project.panels) == 2
        assert fresh.panel_strip.count() == 2


class TestReorder:
    """Tests for keyboard reordering with Ctrl+Left/Right."""

    def test_move_panel_left(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Ctrl+Left should move the selected panel left."""
        event, _mime = _make_drop_event(temp_images[:3])
        window.dropEvent(event)

        window.panel_strip.setCurrentRow(2)
        original_id = window.project.panels[2].panel_id
        window._move_panel_left()

        assert window.project.panels[1].panel_id == original_id
        assert window.panel_strip.currentRow() == 1

    def test_move_panel_right(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Ctrl+Right should move the selected panel right."""
        event, _mime = _make_drop_event(temp_images[:3])
        window.dropEvent(event)

        window.panel_strip.setCurrentRow(0)
        original_id = window.project.panels[0].panel_id
        window._move_panel_right()

        assert window.project.panels[1].panel_id == original_id
        assert window.panel_strip.currentRow() == 1

    def test_move_first_panel_left_noop(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Moving the first panel left should be a no-op."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window.panel_strip.setCurrentRow(0)
        original_order = [p.panel_id for p in window.project.panels]
        window._move_panel_left()

        assert [p.panel_id for p in window.project.panels] == original_order

    def test_move_last_panel_right_noop(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Moving the last panel right should be a no-op."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window.panel_strip.setCurrentRow(1)
        original_order = [p.panel_id for p in window.project.panels]
        window._move_panel_right()

        assert [p.panel_id for p in window.project.panels] == original_order


class TestKeyboard:
    """Tests for keyboard shortcuts."""

    def test_space_toggles_playback(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Space key should toggle play/pause."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        window.eventFilter(window, key_event)

        assert window.play_btn.text() == "Pause"

    def test_arrow_keys_navigate_panels(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Left/Right arrow keys should navigate between panels without loading the player."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)
        assert window.panel_strip.currentRow() == 1  # last added is selected

        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        left = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
        window.eventFilter(window, left)
        assert window.panel_strip.currentRow() == 0

        right = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        window.eventFilter(window, right)
        assert window.panel_strip.currentRow() == 1


class TestScrubBar:
    """Tests for scrub bar interactions."""

    def test_scrub_value_shows_correct_panel(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Moving scrub bar to midpoint should update timecode display."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        # Panels are 3.0s each = 6.0s total. Slider at 500 = 3.0s = start of panel 2.
        window.scrub_slider.setValue(500)
        QApplication.processEvents()

        # Timecode should reflect ~3.0s
        assert "3" in window.timecode_label.text()

    def test_scrub_to_zero(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Scrub bar at 0 should show the beginning."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window.scrub_slider.setValue(0)
        QApplication.processEvents()

        assert "0:00.0" in window.timecode_label.text()

    def test_scrub_pressed_pauses_playback(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Pressing the scrub bar while playing should pause."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window._toggle_playback()
        assert window.player.is_playing()

        window._on_scrub_pressed()
        assert not window.player.is_playing()
        assert window._scrubbing

    def test_scrub_released_resumes_playback(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Releasing the scrub bar should resume if was playing before."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window._toggle_playback()
        window._on_scrub_pressed()
        window._on_scrub_released()

        assert not window._scrubbing
        assert window.player.is_playing()


class TestExportFailure:
    """Tests for the export error path."""

    @patch("animatic.main_window.QMessageBox.critical")
    def test_export_error_shows_dialog(
        self, mock_critical, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """Export failure should show a critical error dialog and re-enable button."""
        event, _mime = _make_drop_event(temp_images[:1])
        window.dropEvent(event)
        window.output_path_input.setText("/tmp/out.mp4")

        with patch("subprocess.Popen", side_effect=Exception("ffmpeg crashed")):
            window._export_video()
            window._export_thread.wait(5000)
            QApplication.processEvents()

            mock_critical.assert_called_once()
            assert "ffmpeg crashed" in mock_critical.call_args[0][2]

        assert window.export_btn.isEnabled()
        assert window.export_btn.text() == "Export Video"

    def test_export_success_restores_button(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """After successful export, button should be re-enabled with original text."""
        event, _mime = _make_drop_event(temp_images[:1])
        window.dropEvent(event)

        # Simulate the success callback directly (avoids thread timing issues)
        window.export_btn.setEnabled(False)
        window.export_btn.setText("Exporting...")

        with patch("animatic.main_window.QMessageBox.information"):
            window._on_export_success("/tmp/out.mp4")

        assert window.export_btn.isEnabled()
        assert window.export_btn.text() == "Export Video"


class TestBrowseDialogs:
    """Tests for file browse dialogs."""

    def test_browse_images_adds_panels(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Browse images dialog should add panels to the project."""
        with patch(
            "animatic.main_window.QFileDialog.getOpenFileNames",
            return_value=(temp_images[:2], ""),
        ):
            window._browse_images()

        assert len(window.project.panels) == 2
        assert window.panel_strip.count() == 2

    def test_browse_images_cancelled(self, window: AnimaticCreator) -> None:
        """Cancelling browse images should not add panels."""
        with patch(
            "animatic.main_window.QFileDialog.getOpenFileNames",
            return_value=([], ""),
        ):
            window._browse_images()

        assert len(window.project.panels) == 0

    def test_browse_audio_sets_panel_audio(
        self, window: AnimaticCreator, temp_images: list[str], temp_audio: str
    ) -> None:
        """Browse audio should assign audio to the selected panel."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        with patch(
            "animatic.main_window.QFileDialog.getOpenFileName",
            return_value=(temp_audio, ""),
        ), patch.object(window.engine, "get_audio_duration", return_value=None):
            window._browse_audio()

        assert window.project.panels[0].audio_path == temp_audio

    def test_browse_audio_cancelled(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """Cancelling browse audio should not change anything."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        with patch(
            "animatic.main_window.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ):
            window._browse_audio()

        assert window.project.panels[0].audio_path is None


class TestSetAudioDuration:
    """Tests for _set_audio auto-duration detection."""

    def test_set_audio_updates_duration(
        self, window: AnimaticCreator, temp_images: list[str], temp_audio: str
    ) -> None:
        """Setting audio with a detectable duration should update the panel duration."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        with patch.object(window.engine, "get_audio_duration", return_value=7.3):
            window._set_audio(temp_audio)

        assert window.project.panels[0].duration == 7.3
        assert window.project.panels[0].audio_path == temp_audio
        assert "7.3" in window.panel_audio_label.text()

    def test_set_audio_no_duration_keeps_default(
        self, window: AnimaticCreator, temp_images: list[str], temp_audio: str
    ) -> None:
        """When duration can't be detected, panel duration should remain unchanged."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        with patch.object(window.engine, "get_audio_duration", return_value=None):
            window._set_audio(temp_audio)

        assert window.project.panels[0].duration == 3.0  # default
        assert window.project.panels[0].audio_path == temp_audio

    def test_set_audio_no_panel_sets_global(
        self, window: AnimaticCreator, temp_audio: str
    ) -> None:
        """Setting audio with no panel selected should set global audio."""
        window._set_audio(temp_audio)
        assert window.project.audio_path == temp_audio


class TestDragReorderSync:
    """Tests for _sync_panel_order after drag-and-drop reorder."""

    def test_sync_reorders_project_panels(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """_sync_panel_order should match project.panels to the strip's visual order."""
        event, _mime = _make_drop_event(temp_images[:3])
        window.dropEvent(event)

        original_ids = [p.panel_id for p in window.project.panels]
        assert len(original_ids) == 3

        # Manually swap items in the strip to simulate drag (move last to first)
        item = window.panel_strip.takeItem(2)
        window.panel_strip.insertItem(0, item)

        # Trigger sync
        window._sync_panel_order()

        new_ids = [p.panel_id for p in window.project.panels]
        assert new_ids[0] == original_ids[2]
        assert new_ids[1] == original_ids[0]
        assert new_ids[2] == original_ids[1]

    def test_sync_preserves_panel_data(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """Reordering should preserve all panel attributes."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window.project.panels[0].notes = "First panel"
        window.project.panels[0].duration = 5.0
        window.project.panels[1].notes = "Second panel"

        # Swap in strip
        item = window.panel_strip.takeItem(1)
        window.panel_strip.insertItem(0, item)
        window._sync_panel_order()

        assert window.project.panels[0].notes == "Second panel"
        assert window.project.panels[1].notes == "First panel"
        assert window.project.panels[1].duration == 5.0


class TestKeyboardCtrl:
    """Tests for Ctrl+ keyboard shortcuts."""

    def test_ctrl_s_saves_project(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Ctrl+S should trigger save dialog."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        with patch("animatic.main_window.QFileDialog.getSaveFileName", return_value=("", "")) as mock_save:
            key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
            window.eventFilter(window, key)
            mock_save.assert_called_once()

    def test_ctrl_d_duplicates_panel(self, window: AnimaticCreator, temp_images: list[str]) -> None:
        """Ctrl+D should duplicate the selected panel."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
        window.eventFilter(window, key)

        assert len(window.project.panels) == 2


class TestBugFixes:
    """Tests for the 4 reliability bug fixes."""

    def test_preview_panel_changed_updates_notes(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """Bug 1: notes_input should update when preview advances panels."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        window.project.panels[0].notes = "Panel one notes"
        window.project.panels[1].notes = "Panel two notes"

        # Simulate preview advancing to panel index 1
        window._on_preview_panel_changed(1)
        assert window.notes_input.text() == "Panel two notes"

        # Advance back to panel 0
        window._on_preview_panel_changed(0)
        assert window.notes_input.text() == "Panel one notes"

    def test_drag_reorder_pushes_undo(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """Bug 2: reordering panels via drag should push to undo stack."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        undo_len_before = len(window._undo_stack._undo)

        # Simulate a drag reorder by swapping strip items and calling sync
        item0 = window.panel_strip.takeItem(0)
        window.panel_strip.insertItem(1, item0)
        window._sync_panel_order()

        assert len(window._undo_stack._undo) == undo_len_before + 1

    def test_per_panel_audio_warns_about_global(
        self, window: AnimaticCreator, temp_images: list[str], temp_audio: str
    ) -> None:
        """Bug 3: setting per-panel audio when global audio exists should warn."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        # Set global audio
        window.project.audio_path = "/fake/global.mp3"

        # Select the panel
        window.panel_strip.setCurrentRow(0)

        # Mock both QMessageBox.information and get_audio_duration
        with patch("animatic.main_window.QMessageBox.information") as mock_info, \
             patch.object(window.engine, "get_audio_duration", return_value=2.0):
            window._set_audio(temp_audio)
            mock_info.assert_called_once()
            assert "global audio" in mock_info.call_args[0][2].lower()

    def test_export_confirms_overwrite(
        self, window: AnimaticCreator, temp_images: list[str], tmp_path
    ) -> None:
        """Bug 4: exporting to existing file should ask for confirmation."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        # Create a file that already exists
        output = str(tmp_path / "output.mp4")
        with open(output, "w") as f:
            f.write("existing")
        window.output_path_input.setText(output)

        # User clicks No — export should abort
        with patch("animatic.main_window.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.No) as mock_q:
            window._export_video()
            mock_q.assert_called_once()

        # export_btn should still be enabled (export was cancelled)
        assert window.export_btn.isEnabled()


class TestRound2BugFixes:
    """Tests for the 8 reliability bug fixes (round 2)."""

    def test_export_thread_initialized(self, window: AnimaticCreator) -> None:
        """C1: _export_thread should be initialized to None in __init__."""
        assert window._export_thread is None

    def test_double_export_guard(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """M3: second export call while running should be a no-op."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        # Simulate a running export thread
        window._export_thread = MagicMock()
        window._export_thread.isRunning.return_value = True

        window.output_path_input.setText("/tmp/test_output.mp4")
        # This should return early without creating a new thread
        window._export_video()
        # The mock should still be the same object (not replaced)
        assert window._export_thread.isRunning.return_value is True

    def test_remove_panel_stops_playback(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """M1: removing a panel during playback should stop the player."""
        event, _mime = _make_drop_event(temp_images[:2])
        window.dropEvent(event)

        # Mock player as playing
        window.player.is_playing = MagicMock(return_value=True)
        window.player.stop = MagicMock()

        window.panel_strip.setCurrentRow(0)
        window._remove_selected_panel()

        window.player.stop.assert_called_once()
        assert window.play_btn.text() == "Play"

    def test_drop_stops_playback(
        self, window: AnimaticCreator, temp_images: list[str]
    ) -> None:
        """M2: dropping images during playback should stop the player."""
        event, _mime = _make_drop_event([temp_images[0]])
        window.dropEvent(event)

        # Mock player as playing
        window.player.is_playing = MagicMock(return_value=True)
        window.player.stop = MagicMock()

        event2, _mime2 = _make_drop_event([temp_images[1]])
        window.dropEvent(event2)

        window.player.stop.assert_called_once()

    def test_corrupt_project_shows_error(
        self, window: AnimaticCreator, tmp_path
    ) -> None:
        """M5: loading a corrupt .animatic file should show error, not crash."""
        corrupt_file = str(tmp_path / "corrupt.animatic")
        with open(corrupt_file, "w") as f:
            f.write("NOT VALID JSON{{{")

        with patch("animatic.main_window.QMessageBox.critical") as mock_crit:
            window._load_project(corrupt_file)
            mock_crit.assert_called_once()
            assert "Failed to load" in mock_crit.call_args[0][2]

    def test_notes_undo_timer_exists(self, window: AnimaticCreator) -> None:
        """M4: notes undo timer should be set up in __init__."""
        assert hasattr(window, "_notes_undo_timer")
        assert window._notes_undo_timer.isSingleShot()
        assert window._notes_undo_timer.interval() == 500
