"""Preview player for animatic playback.

Plays through a sequence of storyboard panels on a timer,
optionally with audio, without requiring FFmpeg rendering.
"""

from typing import Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from animatic.models import Panel


class PreviewPlayer(QObject):
    """Plays through panels by emitting signals on timer ticks.

    Flips through panels based on their durations and optionally
    plays an audio file in sync. No rendering needed — the GUI
    just swaps images in response to signals.

    Signals:
        panel_changed: Emitted with the panel index when switching panels.
        playback_finished: Emitted when all panels have been shown.
        position_updated: Emitted with elapsed seconds (~30 times/sec).
    """

    panel_changed = Signal(int)
    playback_finished = Signal()
    position_updated = Signal(float)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._panels: list[Panel] = []
        self._current_index: int = 0
        self._elapsed_in_panel: float = 0.0
        self._total_elapsed: float = 0.0
        self._playing: bool = False

        # Timer fires every 33ms (~30fps) for smooth progress updates
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

        # Audio playback
        self._audio_output = QAudioOutput(self)
        self._audio_player = QMediaPlayer(self)
        self._audio_player.setAudioOutput(self._audio_output)
        self._audio_player.mediaStatusChanged.connect(self._on_media_status)
        self._has_audio: bool = False
        self._per_panel_audio: bool = False
        self._pending_play: bool = False

    def load(self, panels: list[Panel], audio_path: Optional[str] = None) -> None:
        """Load panels and optional audio for playback.

        Supports two audio modes:
        - Per-panel: each panel has its own audio_path, played when that panel is active
        - Global: one audio track laid over the whole sequence

        Args:
            panels: Ordered list of panels to play through.
            audio_path: Optional global audio path to play in sync.
        """
        self.stop()
        self._panels = list(panels)
        self._has_audio = False
        self._per_panel_audio = any(p.audio_path for p in panels)

        if self._per_panel_audio:
            self._has_audio = True
        elif audio_path:
            self._audio_player.setSource(QUrl.fromLocalFile(audio_path))
            self._has_audio = True

    def play(self) -> None:
        """Start or resume playback.

        If per-panel audio is active and the correct source is already
        loaded (e.g. after seek_to_time), resumes from current position
        instead of restarting from 0.
        """
        if not self._panels:
            return
        self._playing = True
        self._timer.start()
        if self._per_panel_audio:
            panel = self._panels[self._current_index]
            if panel.audio_path:
                expected = QUrl.fromLocalFile(panel.audio_path)
                if self._audio_player.source() == expected:
                    self._audio_player.play()
                else:
                    self._play_panel_audio(self._current_index)
        elif self._has_audio:
            self._audio_player.play()

    def pause(self) -> None:
        """Pause playback."""
        self._playing = False
        self._timer.stop()
        self._pending_play = False
        if self._has_audio:
            self._audio_player.pause()

    def stop(self) -> None:
        """Stop playback and reset to the beginning."""
        self._playing = False
        self._timer.stop()
        self._pending_play = False
        self._current_index = 0
        self._elapsed_in_panel = 0.0
        self._total_elapsed = 0.0
        if self._has_audio:
            self._audio_player.stop()

    def seek_to_panel(self, index: int) -> None:
        """Jump to the start of a specific panel.

        Args:
            index: The panel index to jump to.
        """
        if not self._panels or index < 0 or index >= len(self._panels):
            return
        self._current_index = index
        self._elapsed_in_panel = 0.0
        self._total_elapsed = sum(p.duration for p in self._panels[:index])
        self.panel_changed.emit(self._current_index)
        self.position_updated.emit(self._total_elapsed)
        if self._per_panel_audio:
            self._play_panel_audio(index)
        elif self._has_audio:
            offset_ms = int(self._total_elapsed * 1000)
            self._audio_player.setPosition(offset_ms)

    def seek_to_time(self, target_time: float) -> None:
        """Jump to a specific time in the sequence.

        Finds which panel the time falls in and sets elapsed
        to the exact position within that panel.

        Args:
            target_time: Time in seconds to seek to.
        """
        if not self._panels:
            return
        cumulative = 0.0
        for i, panel in enumerate(self._panels):
            if cumulative + panel.duration > target_time or i == len(self._panels) - 1:
                self._current_index = i
                self._elapsed_in_panel = max(0.0, target_time - cumulative)
                self._total_elapsed = target_time
                self.panel_changed.emit(self._current_index)
                if self._per_panel_audio and panel.audio_path:
                    new_source = QUrl.fromLocalFile(panel.audio_path)
                    if self._audio_player.source() == new_source:
                        self._audio_player.setPosition(
                            int(self._elapsed_in_panel * 1000)
                        )
                    else:
                        self._audio_player.stop()
                        self._pending_play = False
                        self._audio_player.setSource(new_source)
                elif self._has_audio:
                    self._audio_player.setPosition(int(target_time * 1000))
                return
            cumulative += panel.duration

    def _play_panel_audio(self, index: int) -> None:
        """Start playing the audio for a specific panel.

        If the same file is already loaded, restarts it directly.
        Otherwise sets the source and waits for _on_media_status
        to call play() once loaded.

        Args:
            index: The panel index whose audio to play.
        """
        if index < 0 or index >= len(self._panels):
            return
        panel = self._panels[index]
        if panel.audio_path:
            new_source = QUrl.fromLocalFile(panel.audio_path)
            if self._audio_player.source() == new_source:
                # Same file already loaded — just restart
                self._pending_play = False
                self._audio_player.setPosition(0)
                self._audio_player.play()
            else:
                # Different file — load and wait for ready
                self._audio_player.stop()
                self._pending_play = True
                self._audio_player.setSource(new_source)
        else:
            self._pending_play = False
            self._audio_player.stop()

    def _on_media_status(self, status) -> None:
        """Auto-play audio once the source is loaded.

        QMediaPlayer needs time to load after setSource(). This
        callback fires play() as soon as the media is ready.
        Accepts both LoadedMedia and BufferedMedia since Qt may
        skip directly to BufferedMedia for cached files.
        """
        if self._pending_play and status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self._pending_play = False
            self._audio_player.play()

    def next_panel(self) -> None:
        """Jump to the next panel, or stop if at the end."""
        if self._current_index < len(self._panels) - 1:
            self.seek_to_panel(self._current_index + 1)

    def prev_panel(self) -> None:
        """Jump to the previous panel, or stay at the first."""
        if self._current_index > 0:
            self.seek_to_panel(self._current_index - 1)

    def is_playing(self) -> bool:
        """Return whether playback is active.

        Returns:
            True if currently playing, False otherwise.
        """
        return self._playing

    def current_index(self) -> int:
        """Return the index of the currently displayed panel.

        Returns:
            The current panel index.
        """
        return self._current_index

    def total_elapsed(self) -> float:
        """Return total elapsed time in seconds.

        Returns:
            Elapsed seconds since playback started.
        """
        return self._total_elapsed

    def _tick(self) -> None:
        """Advance elapsed time and switch panels when due.

        Called every 33ms by the timer. Increments the elapsed time,
        emits position_updated, and switches to the next panel when
        the current panel's duration has elapsed.
        """
        if not self._playing or not self._panels:
            return

        dt = self._timer.interval() / 1000.0
        self._elapsed_in_panel += dt
        self._total_elapsed += dt
        self.position_updated.emit(self._total_elapsed)

        current_panel = self._panels[self._current_index]
        if self._elapsed_in_panel >= current_panel.duration:
            self._current_index += 1
            self._elapsed_in_panel = 0.0
            if self._current_index >= len(self._panels):
                self.stop()
                self.playback_finished.emit()
            else:
                if self._per_panel_audio:
                    self._play_panel_audio(self._current_index)
                self.panel_changed.emit(self._current_index)
