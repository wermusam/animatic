"""Main window for the animatic application.

Provides a multi-panel storyboard GUI with drag-and-drop,
instant preview with timecode overlay, and FFmpeg export.
"""

import copy
import os
import sys
import tempfile
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from animatic.engine import AnimaticEngine
from animatic.models import Panel, Project
from animatic.player import PreviewPlayer


class ExportThread(QThread):
    """Runs FFmpeg export in a background thread to prevent UI freeze."""

    succeeded = Signal(str)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        engine: AnimaticEngine,
        panels: list,
        output_path: str,
        audio_path: str | None = None,
        total_duration: float = 0.0,
        burn_notes: bool = False,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.panels = panels
        self.output_path = output_path
        self.audio_path = audio_path
        self.total_duration = total_duration
        self.burn_notes = burn_notes

    def run(self) -> None:
        """Execute the FFmpeg render and report progress."""
        import re
        import subprocess

        try:
            cmd = self.engine._build_multi_panel_cmd(
                self.panels,
                self.output_path,
                self.audio_path,
                burn_notes=self.burn_notes,
            )

            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                universal_newlines=True,
            )

            time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
            try:
                for line in proc.stderr:
                    match = time_pattern.search(line)
                    if match and self.total_duration > 0:
                        h = float(match.group(1))
                        m = float(match.group(2))
                        s = float(match.group(3))
                        current = h * 3600 + m * 60 + s
                        pct = min(int((current / self.total_duration) * 100), 99)
                        self.progress.emit(pct)
            except Exception:
                proc.kill()
                raise
            finally:
                proc.wait()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd)

            self.progress.emit(100)
            self.succeeded.emit(self.output_path)
        except Exception as e:
            self.failed.emit(str(e))


class JumpSlider(QSlider):
    """A slider that jumps to the clicked position and supports dragging.

    Qt's default QSlider moves by a small page step when you click
    the groove. This subclass handles all three mouse events so
    clicking jumps to position AND dragging works smoothly.
    """

    def mousePressEvent(self, event) -> None:
        """Jump handle to click position and start drag tracking."""
        if event.button() == Qt.MouseButton.LeftButton:
            # setSliderDown first so sliderPressed fires before valueChanged
            self.setSliderDown(True)
            val = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                int(event.position().x()),
                self.width(),
            )
            self.setSliderPosition(val)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Update slider position while dragging."""
        if self.isSliderDown():
            val = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                int(event.position().x()),
                self.width(),
            )
            self.setSliderPosition(val)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """End drag tracking."""
        if self.isSliderDown():
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class PanelStrip(QListWidget):
    """Horizontal strip of storyboard panel thumbnails.

    Supports drag-to-reorder via internal move and displays
    thumbnails with panel duration labels.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setIconSize(QSize(120, 80))
        self.setFixedHeight(120)
        self.setSpacing(8)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


class UndoStack:
    """Simple undo/redo stack that stores project snapshots."""

    def __init__(self) -> None:
        self._undo: list[dict] = []
        self._redo: list[dict] = []

    def push(self, project: "Project") -> None:
        """Save the current project state before a change."""
        self._undo.append(project.to_dict())
        self._redo.clear()

    def undo(self, project: "Project") -> Optional["Project"]:
        """Restore the previous state. Returns the restored Project or None."""
        if not self._undo:
            return None
        self._redo.append(project.to_dict())
        data = self._undo.pop()
        return Project.from_dict(data)

    def redo(self, project: "Project") -> Optional["Project"]:
        """Re-apply the last undone change. Returns the restored Project or None."""
        if not self._redo:
            return None
        self._undo.append(project.to_dict())
        data = self._redo.pop()
        return Project.from_dict(data)

    def can_undo(self) -> bool:
        return len(self._undo) > 0

    def can_redo(self) -> bool:
        return len(self._redo) > 0


class AnimaticCreator(QMainWindow):
    """Main application window for the animatic tool.

    Supports dragging multiple storyboard images, setting per-panel
    durations, instant preview with timecode, and MP4 export.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Storyboard Animatic")
        self.resize(900, 700)
        self.setMinimumSize(600, 500)
        self.setAcceptDrops(True)

        self.project = Project()
        self.engine = AnimaticEngine()
        self._pixmap_cache: dict[str, QPixmap] = {}
        self._undo_stack = UndoStack()
        self._export_thread: Optional[ExportThread] = None
        self._notes_undo_timer = QTimer(self)
        self._notes_undo_timer.setSingleShot(True)
        self._notes_undo_timer.setInterval(500)
        self._notes_undo_timer.timeout.connect(self._push_notes_undo)
        self._recorder = None
        self._capture_session = None
        self._audio_input = None
        self._recording_path: Optional[str] = None

        self._setup_ui()
        self._setup_player()
        self._apply_styles()
        self._update_button_states()

        # Install event filter on the app so keyboard shortcuts work
        # regardless of which widget has focus
        QApplication.instance().installEventFilter(self)

    def _setup_ui(self) -> None:
        """Build the GUI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 8, 12, 8)

        # Title
        self.title_label = QLabel("Storyboard Animatic")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setObjectName("TitleLabel")
        layout.addWidget(self.title_label)

        # Main image display
        self.main_display = QLabel("Drop images here or click Add Images")
        self.main_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_display.setObjectName("MainDisplay")
        self.main_display.setMinimumHeight(200)
        self.main_display.setScaledContents(False)
        layout.addWidget(self.main_display, stretch=1)

        # Notes display below image
        self.dialogue_label = QLabel("")
        self.dialogue_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dialogue_label.setWordWrap(True)
        self.dialogue_label.setStyleSheet(
            "color: #ffcc00; font-size: 16px; font-weight: bold; padding: 6px;"
        )
        layout.addWidget(self.dialogue_label)

        # Import buttons row
        import_row = QHBoxLayout()

        self.add_images_btn = QPushButton("\U0001f4c2 Add Images")
        self.add_images_btn.setObjectName("ImportBtn")
        self.add_images_btn.clicked.connect(self._browse_images)
        import_row.addWidget(self.add_images_btn, stretch=1)

        self.add_audio_btn = QPushButton("\U0001f50a Add Audio")
        self.add_audio_btn.setObjectName("ImportBtn")
        self.add_audio_btn.clicked.connect(self._browse_audio)
        import_row.addWidget(self.add_audio_btn, stretch=1)

        self.record_btn = QPushButton("\U0001f534 Record")
        self.record_btn.setObjectName("RecordBtn")
        self.record_btn.setToolTip("Record audio from microphone for the selected panel")
        self.record_btn.clicked.connect(self._toggle_recording)
        import_row.addWidget(self.record_btn, stretch=1)

        self.save_btn = QPushButton("\U0001f4be Save Project")
        self.save_btn.setObjectName("ProjectBtn")
        self.save_btn.clicked.connect(self._save_project)
        import_row.addWidget(self.save_btn, stretch=1)

        self.load_btn = QPushButton("\U0001f4c2 Load Project")
        self.load_btn.setObjectName("ProjectBtn")
        self.load_btn.setToolTip("Open a saved .animatic project file")
        self.load_btn.clicked.connect(self._browse_load_project)
        import_row.addWidget(self.load_btn, stretch=1)

        layout.addLayout(import_row)

        # Panel strip
        self.panel_strip = PanelStrip()
        self.panel_strip.setFixedHeight(110)
        self.panel_strip.currentItemChanged.connect(self._on_panel_selected)
        self.panel_strip.model().rowsMoved.connect(self._on_panels_reordered)
        layout.addWidget(self.panel_strip)

        # Controls row: duration, remove, audio status
        controls = QHBoxLayout()

        controls.addWidget(QLabel("Duration (s):"))
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.1, 300.0)
        self.duration_spin.setValue(3.0)
        self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setObjectName("InputBox")
        self.duration_spin.valueChanged.connect(self._on_duration_changed)
        controls.addWidget(self.duration_spin)

        self.duplicate_btn = QPushButton("Duplicate")
        self.duplicate_btn.setObjectName("BrowseBtn")
        self.duplicate_btn.clicked.connect(self._duplicate_selected_panel)
        controls.addWidget(self.duplicate_btn)

        self.remove_btn = QPushButton("Remove Panel")
        self.remove_btn.setObjectName("RemoveBtn")
        self.remove_btn.clicked.connect(self._remove_selected_panel)
        controls.addWidget(self.remove_btn)

        controls.addStretch()

        self.panel_audio_label = QLabel("Panel Audio: None")
        self.panel_audio_label.setObjectName("AudioLabel")
        controls.addWidget(self.panel_audio_label)

        self.remove_audio_btn = QPushButton("Remove Audio")
        self.remove_audio_btn.setObjectName("RemoveBtn")
        self.remove_audio_btn.setToolTip("Remove audio from this panel")
        self.remove_audio_btn.clicked.connect(self._remove_panel_audio)
        controls.addWidget(self.remove_audio_btn)

        self.total_label = QLabel("Total: 0.0s")
        self.total_label.setStyleSheet("color: #888; font-size: 14px;")
        controls.addWidget(self.total_label)

        layout.addLayout(controls)

        # Notes field (shown in preview, optionally burned into export)
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Notes for this panel (action, dialogue, direction)...")
        self.notes_input.setObjectName("InputBox")
        self.notes_input.textChanged.connect(self._on_notes_changed)
        layout.addWidget(self.notes_input)

        # Preview controls: play/pause, stop, scrub bar, timecode
        preview_row = QHBoxLayout()

        self.play_btn = QPushButton("Play")
        self.play_btn.setObjectName("ActionBtn")
        self.play_btn.setFixedWidth(80)
        self.play_btn.clicked.connect(self._toggle_playback)
        preview_row.addWidget(self.play_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("BrowseBtn")
        self.stop_btn.setFixedWidth(60)
        self.stop_btn.clicked.connect(self._stop_playback)
        preview_row.addWidget(self.stop_btn)

        self.scrub_slider = JumpSlider(Qt.Orientation.Horizontal)
        self.scrub_slider.setRange(0, 1000)
        self.scrub_slider.setValue(0)
        self.scrub_slider.setTracking(True)
        self.scrub_slider.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.scrub_slider.sliderPressed.connect(self._on_scrub_pressed)
        self.scrub_slider.sliderReleased.connect(self._on_scrub_released)
        self.scrub_slider.sliderMoved.connect(self._on_scrub_moved)
        self.scrub_slider.valueChanged.connect(self._on_scrub_value_changed)
        preview_row.addWidget(self.scrub_slider, stretch=1)

        self.timecode_label = QLabel("0:00.0")
        self.timecode_label.setObjectName("StatusBar")
        self.timecode_label.setFixedWidth(90)
        preview_row.addWidget(self.timecode_label)

        layout.addLayout(preview_row)

        # Green status bar (like video player status line)
        self.status_bar = QLabel("Panel 0/0  |  00:00.0 / 00:00.0  |  Stopped")
        self.status_bar.setObjectName("StatusBar")
        self.status_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_bar.setFixedHeight(28)
        layout.addWidget(self.status_bar)

        # Output row
        output_row = QHBoxLayout()
        self.output_path_input = QLineEdit()
        self.output_path_input.setPlaceholderText("Save location (auto-generated or browse)")
        self.output_path_input.setObjectName("InputBox")
        output_row.addWidget(self.output_path_input)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setObjectName("BrowseBtn")
        self.browse_btn.clicked.connect(self.browse_output_path)
        output_row.addWidget(self.browse_btn)

        layout.addLayout(output_row)

        # Export progress bar (hidden until export starts)
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        self.export_progress.setFixedHeight(20)
        self.export_progress.setVisible(False)
        self.export_progress.setStyleSheet(
            "QProgressBar { border: 1px solid #444; border-radius: 3px; background: #2d2d2d; text-align: center; color: white; }"
            "QProgressBar::chunk { background-color: #ff3366; border-radius: 3px; }"
        )
        layout.addWidget(self.export_progress)

        # Export row: checkbox + button
        export_row = QHBoxLayout()

        self.burn_notes_cb = QCheckBox("Burn notes into export")
        self.burn_notes_cb.setChecked(True)
        self.burn_notes_cb.setToolTip(
            "When checked, panel notes appear as subtitles in the exported video. "
            "Uncheck for a clean version without text."
        )
        export_row.addWidget(self.burn_notes_cb)

        export_row.addStretch()

        self.export_btn = QPushButton("Export Video")
        self.export_btn.setObjectName("ActionBtn")
        self.export_btn.clicked.connect(self._export_video)
        export_row.addWidget(self.export_btn)

        layout.addLayout(export_row)

    def _setup_player(self) -> None:
        """Initialize the preview player and connect signals."""
        self.player = PreviewPlayer(self)
        self.player.panel_changed.connect(self._on_preview_panel_changed)
        self.player.position_updated.connect(self._on_preview_position)
        self.player.playback_finished.connect(self._on_preview_finished)
        self._scrubbing = False
        self._was_playing = False

    def resizeEvent(self, event) -> None:
        """Re-display current panel at new size on window resize."""
        super().resizeEvent(event)
        current = self.panel_strip.currentItem()
        if current:
            panel_id = current.data(Qt.ItemDataRole.UserRole)
            panel = self._find_panel(panel_id)
            if panel:
                self._show_panel_image(panel)

    # -- Drag and Drop --

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drag events that contain file URLs."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle dropped files — images become panels, audio sets the track."""
        if self.player.is_playing():
            self.player.stop()
            self.play_btn.setText("Play")
        self._undo_stack.push(self.project)
        urls = event.mimeData().urls()
        for url in urls:
            file_path = url.toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".animatic":
                self._load_project(file_path)
                return
            elif ext in (".png", ".jpg", ".jpeg", ".gif"):
                panel = self.project.add_panel(file_path)
                self._add_panel_to_strip(panel)
            elif ext in (".mp3", ".wav", ".m4a"):
                self._set_audio(file_path)

        self._update_status()
        self._update_button_states()
        self._set_default_output_path()

    # -- Panel Strip --

    def _add_panel_to_strip(self, panel: Panel) -> None:
        """Add a panel thumbnail to the strip widget.

        Args:
            panel: The Panel to add.
        """
        pixmap = QPixmap(panel.image_path)
        if pixmap.isNull():
            pixmap = QPixmap(120, 80)
            pixmap.fill(Qt.GlobalColor.darkGray)

        thumb = pixmap.scaled(
            120,
            80,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        item = QListWidgetItem()
        item.setIcon(thumb)
        item.setText(f"{panel.duration}s")
        item.setData(Qt.ItemDataRole.UserRole, panel.panel_id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        self.panel_strip.addItem(item)

        # Cache full-size pixmap for preview
        self._cache_panel_pixmap(panel, pixmap)

        # Select the newly added panel
        self.panel_strip.setCurrentItem(item)

    def _cache_panel_pixmap(self, panel: Panel, pixmap: Optional[QPixmap] = None) -> None:
        """Cache the original full-size pixmap for a panel.

        The pixmap is scaled to fit the display each time it's shown,
        so it always looks correct at any window size.

        Args:
            panel: The panel to cache.
            pixmap: Optional pre-loaded pixmap; loads from disk if not provided.
        """
        if pixmap is None:
            pixmap = QPixmap(panel.image_path)
        # Store the original — we scale to display size on every show
        self._pixmap_cache[panel.panel_id] = pixmap

    def _on_panel_selected(
        self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]
    ) -> None:
        """Update the main display, slider, and status bar when a panel is selected."""
        if current is None:
            return
        panel_id = current.data(Qt.ItemDataRole.UserRole)
        panel = self._find_panel(panel_id)
        if panel:
            # Calculate elapsed time at start of this panel
            idx = self.panel_strip.row(current)
            elapsed = sum(p.duration for p in self.project.panels[:idx])

            self._show_panel_image(panel, elapsed)
            self.duration_spin.blockSignals(True)
            self.duration_spin.setValue(panel.duration)
            self.duration_spin.blockSignals(False)

            # Update slider position
            total = self.project.total_duration()
            if total > 0:
                self.scrub_slider.blockSignals(True)
                self.scrub_slider.setValue(int((elapsed / total) * 1000))
                self.scrub_slider.blockSignals(False)

            self.timecode_label.setText(self._format_time(elapsed))
            self._update_status_bar(elapsed, playing=False)

            # Populate notes field
            self.notes_input.blockSignals(True)
            self.notes_input.setText(panel.notes)
            self.notes_input.blockSignals(False)

            if panel.audio_path:
                self.panel_audio_label.setText(f"Panel Audio: {os.path.basename(panel.audio_path)}")
            else:
                self.panel_audio_label.setText("Panel Audio: None")

            self._update_button_states()

    def _on_panels_reordered(self) -> None:
        """Sync the Project panel order with the strip's visual order."""
        # Defer to after the event loop processes the move
        QTimer.singleShot(0, self._sync_panel_order)

    def _sync_panel_order(self) -> None:
        """Read strip order and update the project to match."""
        if self.player.is_playing():
            self.player.stop()
            self.play_btn.setText("Play")
        panel_map = {p.panel_id: p for p in self.project.panels}
        new_panels: list[Panel] = []
        for i in range(self.panel_strip.count()):
            item = self.panel_strip.item(i)
            pid = item.data(Qt.ItemDataRole.UserRole)
            if pid in panel_map:
                new_panels.append(panel_map[pid])
        self._undo_stack.push(self.project)
        self.project.panels = new_panels

    def _on_duration_changed(self, value: float) -> None:
        """Update the selected panel's duration when the spinbox changes."""
        current = self.panel_strip.currentItem()
        if current is None:
            return
        self._undo_stack.push(self.project)
        panel_id = current.data(Qt.ItemDataRole.UserRole)
        panel = self._find_panel(panel_id)
        if panel:
            panel.duration = value
            current.setText(f"{value}s")
            self._update_status()

    def _remove_selected_panel(self) -> None:
        """Remove the currently selected panel from the project and strip."""
        current = self.panel_strip.currentItem()
        if current is None:
            return
        if self.player.is_playing():
            self.player.stop()
            self.play_btn.setText("Play")
        self._undo_stack.push(self.project)
        panel_id = current.data(Qt.ItemDataRole.UserRole)
        self.project.remove_panel(panel_id)
        self._pixmap_cache.pop(panel_id, None)
        row = self.panel_strip.row(current)
        self.panel_strip.takeItem(row)
        self._update_status()
        self._update_button_states()

        if self.panel_strip.count() == 0:
            self.main_display.clear()
            self.main_display.setText("Drop images here or click Add Images")

    def _find_panel(self, panel_id: str) -> Optional[Panel]:
        """Find a panel in the project by its ID.

        Args:
            panel_id: The unique panel identifier.

        Returns:
            The Panel if found, None otherwise.
        """
        for p in self.project.panels:
            if p.panel_id == panel_id:
                return p
        return None

    # -- Preview Display --

    def _show_panel_image(self, panel: Panel, elapsed: float = 0.0) -> None:
        """Display a panel's image scaled to fit the display.

        Args:
            panel: The panel to display.
            elapsed: Total elapsed time (used by status bar, not drawn on image).
        """
        original = self._pixmap_cache.get(panel.panel_id)
        if original is None:
            self._cache_panel_pixmap(panel)
            original = self._pixmap_cache.get(panel.panel_id)
        if original is None:
            return

        # Scale to fit current display size
        display_w = self.main_display.width() - 4
        display_h = self.main_display.height() - 4
        if display_w < 100:
            display_w = 640
        if display_h < 100:
            display_h = 400
        display = original.scaled(
            display_w,
            display_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.main_display.setPixmap(display)
        self.dialogue_label.setText(panel.notes if panel.notes else "")

    # -- Preview Playback --

    def _toggle_playback(self) -> None:
        """Play or pause the preview."""
        if self.player.is_playing():
            self.player.pause()
            self.play_btn.setText("Play")
            self._update_status_bar(self.player.total_elapsed(), playing=False)
        else:
            if not self.project.panels:
                return
            if self.player.current_index() == 0 and self.player.total_elapsed() == 0.0:
                self.player.load(self.project.panels, self.project.audio_path)
                self._on_preview_panel_changed(0)
            self.player.play()
            self.play_btn.setText("Pause")

    def _stop_playback(self) -> None:
        """Stop the preview and reset."""
        self.player.stop()
        self.play_btn.setText("Play")
        self.scrub_slider.blockSignals(True)
        self.scrub_slider.setValue(0)
        self.scrub_slider.blockSignals(False)
        self.timecode_label.setText(self._format_time(0.0))
        self._update_status_bar(0.0, playing=False)
        if self.project.panels:
            self._show_panel_image(self.project.panels[0], 0.0)

    def _on_preview_panel_changed(self, index: int) -> None:
        """Update display when preview advances to a new panel."""
        if 0 <= index < len(self.project.panels):
            panel = self.project.panels[index]
            self._show_panel_image(panel, self.player.total_elapsed())
            self.panel_strip.setCurrentRow(index)
            self.notes_input.blockSignals(True)
            self.notes_input.setText(panel.notes)
            self.notes_input.blockSignals(False)

    def _on_preview_position(self, elapsed: float) -> None:
        """Update status bar and scrub slider during preview playback."""
        self.timecode_label.setText(self._format_time(elapsed))

        # Update timecode overlay on current image
        idx = self.player.current_index()
        if 0 <= idx < len(self.project.panels):
            self._show_panel_image(self.project.panels[idx], elapsed)

        self._update_status_bar(elapsed, playing=True)

        # Update scrub slider position (block signals to prevent feedback loop)
        if not self._scrubbing:
            total = self.project.total_duration()
            if total > 0:
                position = int((elapsed / total) * 1000)
                self.scrub_slider.blockSignals(True)
                self.scrub_slider.setValue(min(position, 1000))
                self.scrub_slider.blockSignals(False)

    def _on_preview_finished(self) -> None:
        """Handle preview reaching the end."""
        self.play_btn.setText("Play")
        self.scrub_slider.setValue(1000)

    # -- Scrub Bar --

    def _on_scrub_pressed(self) -> None:
        """Pause playback while scrubbing."""
        self._scrubbing = True
        self._was_playing = self.player.is_playing()
        if self._was_playing:
            self.player.pause()

    def _on_scrub_released(self) -> None:
        """Jump to the scrubbed position and resume if was playing.

        Keeps _scrubbing True during seek so that position_updated
        signals don't snap the slider back.
        """
        self._seek_to_slider_position()
        self._scrubbing = False
        if self._was_playing:
            self.player.play()
            self.play_btn.setText("Pause")

    def _on_scrub_value_changed(self, value: int) -> None:
        """Handle clicking on the scrub bar (not dragging).

        Only updates the visual display — does NOT call player.load/seek,
        which would emit position_updated and snap the slider back to 0.
        """
        if not self._scrubbing and not self.player.is_playing() and self.project.panels:
            total = self.project.total_duration()
            target_time = (value / 1000.0) * total
            cumulative = 0.0
            for i, panel in enumerate(self.project.panels):
                if cumulative + panel.duration > target_time or i == len(self.project.panels) - 1:
                    self._show_panel_image(panel, target_time)
                    self.timecode_label.setText(self._format_time(target_time))
                    self._update_status_bar(target_time, playing=False)
                    break
                cumulative += panel.duration

    def _on_scrub_moved(self, value: int) -> None:
        """Update display while dragging the scrub bar."""
        if not self._scrubbing or not self.project.panels:
            return
        total = self.project.total_duration()
        target_time = (value / 1000.0) * total

        # Find which panel this time falls in
        cumulative = 0.0
        for i, panel in enumerate(self.project.panels):
            if cumulative + panel.duration > target_time or i == len(self.project.panels) - 1:
                self._show_panel_image(panel, target_time)
                self.timecode_label.setText(self._format_time(target_time))
                self._update_status_bar(target_time, playing=False)
                break
            cumulative += panel.duration

    def _seek_to_slider_position(self) -> None:
        """Seek the player to the exact time matching the slider position.

        Uses seek_to_time instead of seek_to_panel so scrubbing
        within a single panel works correctly.
        """
        if not self.project.panels:
            return
        total = self.project.total_duration()
        target_time = (self.scrub_slider.value() / 1000.0) * total

        # Load the player if it hasn't been loaded yet
        if not self.player._panels:
            self.player.load(self.project.panels, self.project.audio_path)

        self.player.seek_to_time(target_time)

    # -- Keyboard Shortcuts --

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Catch keyboard shortcuts globally, even when child widgets have focus.

        Space: play/pause
        Left arrow: previous panel
        Right arrow: next panel

        Args:
            obj: The object the event was sent to.
            event: The event.

        Returns:
            True if the event was handled, False to pass it through.
        """
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            focused = QApplication.focusWidget()
            in_text = isinstance(focused, (QLineEdit, QDoubleSpinBox)) or isinstance(
                obj, (QLineEdit, QDoubleSpinBox)
            )

            # Ctrl+Z: undo, Ctrl+Shift+Z: redo
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            if ctrl and key == Qt.Key.Key_Z and not shift:
                self._undo()
                return True
            if ctrl and key == Qt.Key.Key_Z and shift:
                self._redo()
                return True
            # Ctrl+S: save project (works even in text inputs)
            if ctrl and key == Qt.Key.Key_S:
                self._save_project()
                return True
            # Ctrl+D: duplicate panel
            if ctrl and key == Qt.Key.Key_D and not in_text:
                self._duplicate_selected_panel()
                return True
            # Ctrl+Left/Right: reorder panels
            if ctrl and key == Qt.Key.Key_Left and not in_text:
                self._move_panel_left()
                return True
            if ctrl and key == Qt.Key.Key_Right and not in_text:
                self._move_panel_right()
                return True
            # Delete: remove selected panel
            if key == Qt.Key.Key_Delete and not in_text:
                self._remove_selected_panel()
                return True
            # Space: play/pause
            if key == Qt.Key.Key_Space and not in_text:
                self._toggle_playback()
                return True
            # Left/Right: navigate panels
            if key == Qt.Key.Key_Left and not in_text:
                row = self.panel_strip.currentRow()
                if row > 0:
                    self.panel_strip.setCurrentRow(row - 1)
                return True
            if key == Qt.Key.Key_Right and not in_text:
                row = self.panel_strip.currentRow()
                if row < self.panel_strip.count() - 1:
                    self.panel_strip.setCurrentRow(row + 1)
                return True
        return super().eventFilter(obj, event)

    # -- New Feature Handlers --

    def _on_notes_changed(self, text: str) -> None:
        """Update the selected panel's notes when the text field changes."""
        current = self.panel_strip.currentItem()
        if current is None:
            return
        panel_id = current.data(Qt.ItemDataRole.UserRole)
        panel = self._find_panel(panel_id)
        if panel:
            panel.notes = text
            self.dialogue_label.setText(text)
            self._notes_undo_timer.start()

    def _push_notes_undo(self) -> None:
        """Push an undo snapshot after notes editing pauses."""
        self._undo_stack.push(self.project)

    def _undo(self) -> None:
        """Undo the last panel operation."""
        restored = self._undo_stack.undo(self.project)
        if restored:
            self.project = restored
            self._rebuild_strip()

    def _redo(self) -> None:
        """Redo the last undone operation."""
        restored = self._undo_stack.redo(self.project)
        if restored:
            self.project = restored
            self._rebuild_strip()

    def _rebuild_strip(self) -> None:
        """Rebuild the panel strip and UI from the current project state."""
        self.player.stop()
        self._pixmap_cache.clear()
        self.panel_strip.clear()
        for panel in self.project.panels:
            self._add_panel_to_strip(panel)
        self._update_status()
        self._update_button_states()

    def _remove_panel_audio(self) -> None:
        """Remove audio from the currently selected panel."""
        self._undo_stack.push(self.project)
        current = self.panel_strip.currentItem()
        if current is None:
            return
        panel_id = current.data(Qt.ItemDataRole.UserRole)
        panel = self._find_panel(panel_id)
        if panel:
            panel.audio_path = None
            self.panel_audio_label.setText("Panel Audio: None")
            self._update_button_states()

    def _toggle_recording(self) -> None:
        """Start or stop audio recording for the selected panel.

        If the panel already has audio, it will be replaced.
        """
        if self._recorder is not None:
            self._stop_recording()
            return

        current = self.panel_strip.currentItem()
        if current is None:
            QMessageBox.warning(self, "Error", "Select a panel first!")
            return

        # Clear existing audio so re-recording just works
        panel_id = current.data(Qt.ItemDataRole.UserRole)
        panel = self._find_panel(panel_id)
        if panel and panel.audio_path:
            panel.audio_path = None

        try:
            from PySide6.QtMultimedia import (
                QAudioInput,
                QMediaCaptureSession,
                QMediaRecorder,
            )
        except ImportError:
            QMessageBox.warning(
                self,
                "Error",
                "Audio recording requires PySide6 multimedia support.",
            )
            return

        self._recording_path = os.path.join(
            tempfile.gettempdir(), f"animatic_rec_{current.data(Qt.ItemDataRole.UserRole)}.wav"
        )

        self._audio_input = QAudioInput(self)
        self._capture_session = QMediaCaptureSession(self)
        self._capture_session.setAudioInput(self._audio_input)
        self._recorder = QMediaRecorder(self)
        self._capture_session.setRecorder(self._recorder)

        from PySide6.QtCore import QUrl

        self._recorder.setOutputLocation(QUrl.fromLocalFile(self._recording_path))
        self._recorder.record()

        self.record_btn.setText("\u23f9 Stop Recording")
        self.record_btn.setStyleSheet(
            "background-color: #cc3333; color: white; border: 2px solid #ff6666;"
            "border-radius: 5px; padding: 8px 16px; font-size: 14px; font-weight: bold;"
        )

    def _stop_recording(self) -> None:
        """Stop recording and assign the audio to the selected panel."""
        if self._recorder is None:
            return

        self._recorder.stop()
        self._recorder.deleteLater()
        self._recorder = None
        if self._capture_session:
            self._capture_session.deleteLater()
            self._capture_session = None
        if self._audio_input:
            self._audio_input.deleteLater()
            self._audio_input = None

        self.record_btn.setText("\U0001f534 Record")
        self.record_btn.setStyleSheet("")

        if self._recording_path and os.path.exists(self._recording_path):
            self._set_audio(self._recording_path)
        self._recording_path = None

    def _duplicate_selected_panel(self) -> None:
        """Duplicate the selected panel and insert the copy after it."""
        current = self.panel_strip.currentItem()
        if current is None:
            return
        self._undo_stack.push(self.project)
        panel_id = current.data(Qt.ItemDataRole.UserRole)
        new_panel = self.project.duplicate_panel(panel_id)
        if new_panel:
            # Insert into strip right after the current item
            row = self.panel_strip.row(current)
            pixmap = QPixmap(new_panel.image_path)
            if pixmap.isNull():
                pixmap = QPixmap(120, 80)
                pixmap.fill(Qt.GlobalColor.darkGray)

            thumb = pixmap.scaled(
                120,
                80,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            item = QListWidgetItem()
            item.setIcon(thumb)
            item.setText(f"{new_panel.duration}s")
            item.setData(Qt.ItemDataRole.UserRole, new_panel.panel_id)
            self.panel_strip.insertItem(row + 1, item)
            self._cache_panel_pixmap(new_panel, pixmap)
            self.panel_strip.setCurrentItem(item)
            self._update_status()
            self._update_button_states()

    def _save_project(self) -> None:
        """Save the project to a .animatic JSON file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "Animatic Project (*.animatic)"
        )
        if path:
            if not path.endswith(".animatic"):
                path += ".animatic"
            self.project.save(path)

    def _browse_load_project(self) -> None:
        """Open a file dialog to load a .animatic project file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "", "Animatic Project (*.animatic)"
        )
        if path:
            self._load_project(path)

    def _load_project(self, path: str) -> None:
        """Load a project from a .animatic file and rebuild the UI.

        Args:
            path: Path to the .animatic file.
        """
        try:
            loaded = Project.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load project:\n{e}")
            return
        self.project = loaded
        self.player.stop()
        self._pixmap_cache.clear()
        self.panel_strip.clear()

        for panel in self.project.panels:
            self._add_panel_to_strip(panel)

        self._update_status()
        self._update_button_states()

        if self.project.output_path:
            self.output_path_input.setText(self.project.output_path)

    def _move_panel_left(self) -> None:
        """Move the selected panel one position to the left."""
        row = self.panel_strip.currentRow()
        if row <= 0:
            return
        self._undo_stack.push(self.project)
        self.project.reorder(row, row - 1)
        item = self.panel_strip.takeItem(row)
        self.panel_strip.insertItem(row - 1, item)
        self.panel_strip.setCurrentItem(item)

    def _move_panel_right(self) -> None:
        """Move the selected panel one position to the right."""
        row = self.panel_strip.currentRow()
        if row < 0 or row >= self.panel_strip.count() - 1:
            return
        self._undo_stack.push(self.project)
        self.project.reorder(row, row + 1)
        item = self.panel_strip.takeItem(row)
        self.panel_strip.insertItem(row + 1, item)
        self.panel_strip.setCurrentItem(item)

    # -- Export --

    def _export_video(self) -> None:
        """Export the animatic as an MP4 video in a background thread.

        Prevents the UI from freezing during FFmpeg rendering.
        """
        if not self.project.panels:
            QMessageBox.warning(self, "Error", "Add some panels first!")
            return

        if self._export_thread is not None and self._export_thread.isRunning():
            return

        output_path = self.output_path_input.text().strip()
        if not output_path:
            output_path = self._generate_output_path()
        if not output_path.lower().endswith(".mp4"):
            output_path += ".mp4"
        self.output_path_input.setText(output_path)

        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self,
                "File Exists",
                f"Overwrite existing file?\n{output_path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self.export_btn.setEnabled(False)
        self.export_btn.setText("Exporting...")
        self.export_progress.setValue(0)
        self.export_progress.setVisible(True)
        self._update_status_bar(0.0, playing=False)

        self._export_thread = ExportThread(
            self.engine,
            copy.deepcopy(self.project.panels),
            output_path,
            self.project.audio_path,
            total_duration=self.project.total_duration(),
            burn_notes=self.burn_notes_cb.isChecked(),
        )
        self._export_thread.progress.connect(self._on_export_progress)
        self._export_thread.succeeded.connect(self._on_export_success)
        self._export_thread.failed.connect(self._on_export_error)
        self._export_thread.start()

    def _on_export_progress(self, pct: int) -> None:
        """Update the progress bar during export."""
        self.export_progress.setValue(pct)

    def _on_export_success(self, path: str) -> None:
        """Handle successful export."""
        self.export_progress.setValue(100)
        self.export_progress.setVisible(False)
        self.export_btn.setEnabled(True)
        self.export_btn.setText("Export Video")
        QMessageBox.information(self, "Success", f"Video exported!\n{path}")
        self._restore_display()

    def _on_export_error(self, error: str) -> None:
        """Handle export failure."""
        self.export_progress.setVisible(False)
        self.export_btn.setEnabled(True)
        self.export_btn.setText("Export Video")
        QMessageBox.critical(self, "Error", f"Export failed:\n{error}")
        self._restore_display()

    def _restore_display(self) -> None:
        """Restore the panel image after export."""
        if self.project.panels:
            current = self.panel_strip.currentItem()
            if current:
                panel_id = current.data(Qt.ItemDataRole.UserRole)
                panel = self._find_panel(panel_id)
                if panel:
                    self._show_panel_image(panel)

    def _browse_images(self) -> None:
        """Open a file dialog to select storyboard images."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Storyboard Images", "", "Images (*.png *.jpg *.jpeg)"
        )
        if paths:
            self._undo_stack.push(self.project)
        for path in paths:
            panel = self.project.add_panel(path)
            self._add_panel_to_strip(panel)
        if paths:
            self._update_status()
            self._update_button_states()
            self._set_default_output_path()

    def _browse_audio(self) -> None:
        """Open a file dialog to select an audio file for the selected panel."""
        path, _ = QFileDialog.getOpenFileName(self, "Select Audio", "", "Audio (*.mp3 *.wav)")
        if path:
            self._set_audio(path)

    def _set_audio(self, path: str) -> None:
        """Assign audio to the selected panel and auto-set its duration.

        Args:
            path: Path to the audio file.
        """
        current = self.panel_strip.currentItem()
        if current is None:
            # No panel selected — store as global audio
            self.project.audio_path = path
            self.panel_audio_label.setText(f"Audio: {os.path.basename(path)}")
            return

        panel_id = current.data(Qt.ItemDataRole.UserRole)
        panel = self._find_panel(panel_id)
        if not panel:
            return

        panel.audio_path = path
        if self.project.audio_path:
            QMessageBox.information(
                self,
                "Audio Note",
                "Per-panel audio will be used instead of the global audio track during export.",
            )
        name = os.path.basename(path)
        duration = self.engine.get_audio_duration(path)

        if duration is not None:
            panel.duration = round(duration, 1)
            self.duration_spin.blockSignals(True)
            self.duration_spin.setValue(panel.duration)
            self.duration_spin.blockSignals(False)
            current.setText(f"{panel.duration}s")
            self.panel_audio_label.setText(f"Panel Audio: {name} ({duration:.1f}s)")
        else:
            self.panel_audio_label.setText(f"Panel Audio: {name}")

        self._update_status()

    def browse_output_path(self) -> None:
        """Open a save dialog for the user to choose the output path."""
        path, _ = QFileDialog.getSaveFileName(self, "Save Video As", "", "MP4 Files (*.mp4)")
        if path:
            self.project.output_path = path
            self.output_path_input.setText(path)

    # -- Helpers --

    def _update_status(self) -> None:
        """Update the total duration label and status bar."""
        total = self.project.total_duration()
        count = len(self.project.panels)
        self.total_label.setText(f"Total: {total:.1f}s ({count} panels)")
        self._update_status_bar(0.0, playing=False)

    def _format_time(self, seconds: float) -> str:
        """Format seconds as M:SS.s timecode.

        Args:
            seconds: Time in seconds.

        Returns:
            Formatted string like '0:25.3' or '1:05.2'.
        """
        m = int(seconds) // 60
        s = seconds % 60
        return f"{m}:{s:04.1f}"

    def _update_status_bar(self, elapsed: float = 0.0, playing: bool = False) -> None:
        """Update the green status bar at the bottom.

        Args:
            elapsed: Current elapsed time in seconds.
            playing: Whether playback is active.
        """
        count = len(self.project.panels)
        total = self.project.total_duration()
        if count == 0:
            idx = 0
        elif playing or self._scrubbing:
            idx = self.player.current_index() + 1
        else:
            strip_row = self.panel_strip.currentRow()
            idx = (strip_row + 1) if strip_row >= 0 else self.player.current_index() + 1

        current_time = self._format_time(elapsed)
        total_time = self._format_time(total)

        if playing:
            state = "\u25b6 Playing"
        elif self._scrubbing:
            state = "\u25cf Scrubbing"
        elif count == 0:
            state = "Stopped"
        else:
            state = "\u25a0 Stopped"

        self.status_bar.setText(
            f"Panel {idx}/{count}  |  {current_time} / {total_time}  |  {state}"
        )

    def _update_button_states(self) -> None:
        """Enable/disable buttons based on project state."""
        has_panels = len(self.project.panels) > 0
        self.play_btn.setEnabled(has_panels)
        self.stop_btn.setEnabled(has_panels)
        self.export_btn.setEnabled(has_panels)
        self.remove_btn.setEnabled(has_panels)
        self.duplicate_btn.setEnabled(has_panels)

        # Remove audio button only enabled if selected panel has audio
        has_audio = False
        current = self.panel_strip.currentItem()
        if current:
            panel_id = current.data(Qt.ItemDataRole.UserRole)
            panel = self._find_panel(panel_id)
            if panel and panel.audio_path:
                has_audio = True
        self.remove_audio_btn.setEnabled(has_audio)
        self.remove_audio_btn.setVisible(has_audio)

    def _set_default_output_path(self) -> None:
        """Set a default output path if none is set."""
        if self.output_path_input.text().strip():
            return
        if not self.project.panels:
            return
        output_path = self._generate_output_path()
        self.output_path_input.setText(output_path)

    def _generate_output_path(self) -> str:
        """Generate a timestamped output path in the first panel's directory.

        Returns:
            A path like '/path/to/images/animatic_20260402_143022.mp4'.
        """
        folder = os.path.dirname(self.project.panels[0].image_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(folder, f"animatic_{timestamp}.mp4")

    def _apply_styles(self) -> None:
        """Apply the dark theme stylesheet."""
        dark_bg = "#1e1e1e"
        text_color = "#ffffff"
        accent_pink = "#ff3366"
        style_sheet = f"""
            QMainWindow {{ background-color: {dark_bg}; }}
            QWidget {{ color: {text_color}; font-family: 'Segoe UI', 'Roboto', sans-serif; font-size: 14px; }}
            QLabel#TitleLabel {{ font-size: 28px; font-weight: bold; color: {accent_pink}; }}
            QLabel#MainDisplay {{ border: 2px dashed {accent_pink}; border-radius: 10px; background-color: #2d2d2d; font-size: 18px; color: #aaa; }}
            QLabel#AudioLabel {{ color: #33ccff; font-size: 13px; }}
            QLabel#StatusBar {{ color: #00ff00; font-family: 'Courier New', monospace; font-size: 13px; font-weight: bold; background-color: #111; border: 1px solid #333; border-radius: 3px; padding: 2px 8px; }}
            QLineEdit#InputBox {{ padding: 8px; border: 2px solid #444; border-radius: 5px; background-color: #2d2d2d; font-size: 14px; color: white; }}
            QDoubleSpinBox#InputBox {{ padding: 6px; border: 2px solid #444; border-radius: 5px; background-color: #2d2d2d; font-size: 14px; color: white; }}
            QPushButton#ActionBtn {{ background-color: {accent_pink}; color: white; border: none; padding: 12px; border-radius: 5px; font-weight: bold; font-size: 14px; }}
            QPushButton#ActionBtn:hover {{ background-color: #ff6688; }}
            QPushButton#ActionBtn:disabled {{ background-color: #555; color: #888; }}
            QPushButton#BrowseBtn {{ background-color: #2d2d2d; border: 2px solid #444; border-radius: 5px; padding: 8px 12px; font-size: 14px; }}
            QPushButton#RemoveBtn {{ background-color: #2d2d2d; border: 2px solid #884444; border-radius: 5px; padding: 8px 12px; color: #ff6666; font-size: 13px; }}
            QPushButton#RemoveBtn:hover {{ background-color: #442222; }}
            QPushButton#ImportBtn {{ background-color: #2d2d2d; border: 2px solid #448844; border-radius: 5px; padding: 8px 16px; color: #66ff66; font-size: 14px; font-weight: bold; }}
            QPushButton#ImportBtn:hover {{ background-color: #224422; }}
            QPushButton#RecordBtn {{ background-color: #2d2d2d; border: 2px solid #cc3333; border-radius: 5px; padding: 8px 16px; color: #ff6666; font-size: 14px; font-weight: bold; }}
            QPushButton#RecordBtn:hover {{ background-color: #442222; }}
            QPushButton#ProjectBtn {{ background-color: #2d2d2d; border: 2px solid {accent_pink}; border-radius: 5px; padding: 8px 16px; color: {accent_pink}; font-size: 14px; font-weight: bold; }}
            QPushButton#ProjectBtn:hover {{ background-color: #4a1a2a; }}
            QListWidget {{ background-color: #2d2d2d; border: 2px solid #444; border-radius: 5px; }}
            QListWidget::item {{ padding: 4px; color: #aaa; font-size: 11px; }}
            QListWidget::item:selected {{ background-color: {accent_pink}; color: white; border-radius: 3px; }}
            QSlider::groove:horizontal {{ background: #444; height: 6px; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {accent_pink}; width: 20px; margin: -7px 0; border-radius: 10px; }}
            QSlider::sub-page:horizontal {{ background: {accent_pink}; border-radius: 3px; }}
            QMessageBox {{ background-color: #2d2d2d; }}
            QMessageBox QLabel {{ color: white; }}
            QMessageBox QPushButton {{ background-color: {accent_pink}; color: white; border-radius: 3px; padding: 5px 15px; }}
        """
        self.setStyleSheet(style_sheet)


def main() -> None:
    """Launch the animatic application."""
    app = QApplication(sys.argv)
    window = AnimaticCreator()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
