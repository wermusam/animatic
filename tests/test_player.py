"""Tests for the PreviewPlayer playback logic."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from animatic.models import Panel
from animatic.player import PreviewPlayer


@pytest.fixture
def app(qtbot):
    """Ensure a QApplication exists for audio/timer components."""
    test_app = QApplication.instance()
    if test_app is None:
        test_app = QApplication(sys.argv)
    return test_app


@pytest.fixture
def player(qtbot, app) -> PreviewPlayer:
    """Create a fresh PreviewPlayer for each test."""
    # PreviewPlayer is a QObject, not a QWidget, so we manage cleanup manually
    p = PreviewPlayer()
    yield p
    p.stop()


@pytest.fixture
def sample_panels() -> list[Panel]:
    """Three panels with short durations for fast tests."""
    return [
        Panel(image_path="/tmp/a.png", duration=0.1),
        Panel(image_path="/tmp/b.png", duration=0.1),
        Panel(image_path="/tmp/c.png", duration=0.1),
    ]


class TestPlayerLoad:
    """Tests for loading panels into the player."""

    def test_load_sets_panels(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """Loading panels should store them and reset state."""
        player.load(sample_panels)
        assert player.current_index() == 0
        assert player.total_elapsed() == 0.0
        assert not player.is_playing()

    def test_load_without_audio(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """Loading without audio should not error."""
        player.load(sample_panels, audio_path=None)
        assert not player._has_audio

    def test_load_resets_previous_state(
        self, player: PreviewPlayer, sample_panels: list[Panel]
    ) -> None:
        """Loading new panels should reset any previous playback state."""
        player.load(sample_panels)
        player.play()
        player.load(sample_panels)
        assert not player.is_playing()
        assert player.current_index() == 0


class TestPlayerPlayback:
    """Tests for play, pause, and stop."""

    def test_play_starts(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """Play should set playing state to True."""
        player.load(sample_panels)
        player.play()
        assert player.is_playing()

    def test_play_empty_does_nothing(self, player: PreviewPlayer) -> None:
        """Play with no panels loaded should not crash or start."""
        player.play()
        assert not player.is_playing()

    def test_pause(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """Pause should set playing state to False."""
        player.load(sample_panels)
        player.play()
        player.pause()
        assert not player.is_playing()

    def test_stop_resets(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """Stop should reset index and elapsed time."""
        player.load(sample_panels)
        player.play()
        player.stop()
        assert not player.is_playing()
        assert player.current_index() == 0
        assert player.total_elapsed() == 0.0

    def test_panel_changed_signal(
        self, player: PreviewPlayer, sample_panels: list[Panel], qtbot
    ) -> None:
        """panel_changed signal should fire when advancing to next panel."""
        player.load(sample_panels)
        player.play()
        with qtbot.waitSignal(player.panel_changed, timeout=3000):
            pass  # Wait for the signal to fire

    def test_playback_finished_signal(
        self, player: PreviewPlayer, sample_panels: list[Panel], qtbot
    ) -> None:
        """playback_finished should fire after all panels are shown."""
        player.load(sample_panels)
        player.play()
        with qtbot.waitSignal(player.playback_finished, timeout=2000):
            pass

    def test_position_updated_signal(
        self, player: PreviewPlayer, sample_panels: list[Panel], qtbot
    ) -> None:
        """position_updated should emit elapsed time during playback."""
        player.load(sample_panels)
        player.play()
        with qtbot.waitSignal(player.position_updated, timeout=1000):
            pass


class TestPlayerNavigation:
    """Tests for seek, next, and prev."""

    def test_seek_to_panel(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """seek_to_panel should jump to the specified panel index."""
        player.load(sample_panels)
        player.seek_to_panel(2)
        assert player.current_index() == 2

    def test_seek_computes_elapsed(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """Seeking should compute total elapsed from preceding panel durations."""
        player.load(sample_panels)
        player.seek_to_panel(2)
        expected = sample_panels[0].duration + sample_panels[1].duration
        assert abs(player.total_elapsed() - expected) < 0.01

    def test_seek_out_of_bounds(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """Seeking to invalid index should be a no-op."""
        player.load(sample_panels)
        player.seek_to_panel(10)
        assert player.current_index() == 0

    def test_seek_negative(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """Seeking to negative index should be a no-op."""
        player.load(sample_panels)
        player.seek_to_panel(-1)
        assert player.current_index() == 0

    def test_next_panel(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """next_panel should advance by one."""
        player.load(sample_panels)
        player.next_panel()
        assert player.current_index() == 1

    def test_next_panel_at_end(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """next_panel at the last panel should stay put."""
        player.load(sample_panels)
        player.seek_to_panel(2)
        player.next_panel()
        assert player.current_index() == 2

    def test_prev_panel(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """prev_panel should go back by one."""
        player.load(sample_panels)
        player.seek_to_panel(2)
        player.prev_panel()
        assert player.current_index() == 1

    def test_prev_panel_at_start(self, player: PreviewPlayer, sample_panels: list[Panel]) -> None:
        """prev_panel at the first panel should stay put."""
        player.load(sample_panels)
        player.prev_panel()
        assert player.current_index() == 0


class TestSeekToTime:
    """Tests for seek_to_time time-to-panel mapping."""

    def test_seek_to_start(self, player: PreviewPlayer) -> None:
        """Seeking to 0.0 should land on the first panel."""
        panels = [
            Panel(image_path="/tmp/a.png", duration=3.0),
            Panel(image_path="/tmp/b.png", duration=4.0),
        ]
        player.load(panels)
        player.seek_to_time(0.0)
        assert player.current_index() == 0
        assert abs(player.total_elapsed()) < 0.01

    def test_seek_to_second_panel(self, player: PreviewPlayer) -> None:
        """Seeking past first panel's duration should land on second panel."""
        panels = [
            Panel(image_path="/tmp/a.png", duration=3.0),
            Panel(image_path="/tmp/b.png", duration=4.0),
            Panel(image_path="/tmp/c.png", duration=2.0),
        ]
        player.load(panels)
        player.seek_to_time(4.0)
        assert player.current_index() == 1
        assert abs(player.total_elapsed() - 4.0) < 0.01

    def test_seek_to_last_panel(self, player: PreviewPlayer) -> None:
        """Seeking near the end should land on the last panel."""
        panels = [
            Panel(image_path="/tmp/a.png", duration=2.0),
            Panel(image_path="/tmp/b.png", duration=2.0),
            Panel(image_path="/tmp/c.png", duration=2.0),
        ]
        player.load(panels)
        player.seek_to_time(5.5)
        assert player.current_index() == 2

    def test_seek_beyond_total_lands_on_last(self, player: PreviewPlayer) -> None:
        """Seeking past the total duration should land on the last panel."""
        panels = [
            Panel(image_path="/tmp/a.png", duration=2.0),
            Panel(image_path="/tmp/b.png", duration=3.0),
        ]
        player.load(panels)
        player.seek_to_time(100.0)
        assert player.current_index() == len(panels) - 1

    def test_seek_emits_panel_changed(self, player: PreviewPlayer, qtbot) -> None:
        """seek_to_time should emit panel_changed signal."""
        panels = [
            Panel(image_path="/tmp/a.png", duration=3.0),
            Panel(image_path="/tmp/b.png", duration=3.0),
        ]
        player.load(panels)
        with qtbot.waitSignal(player.panel_changed, timeout=1000):
            player.seek_to_time(4.0)

    def test_seek_on_empty_is_noop(self, player: PreviewPlayer) -> None:
        """Seeking with no panels loaded should not crash."""
        player.seek_to_time(5.0)
        assert player.current_index() == 0
