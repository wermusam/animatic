"""Tests for the AnimaticEngine FFmpeg command construction.

Tests verify command structure without invoking FFmpeg.
"""

import subprocess
from unittest.mock import patch

import pytest

from animatic.engine import AnimaticEngine
from animatic.models import Panel


@pytest.fixture
def engine() -> AnimaticEngine:
    """Create an engine instance for testing."""
    return AnimaticEngine()


class TestBuildMultiPanelCmd:
    """Tests for _build_multi_panel_cmd command construction."""

    def test_single_panel_no_audio(self, engine: AnimaticEngine) -> None:
        """Single panel without audio should produce a valid concat command."""
        panels = [Panel(image_path="/tmp/img.png", duration=5.0)]
        cmd = engine._build_multi_panel_cmd(panels, "/tmp/out.mp4", audio_path=None)

        assert cmd[0] == engine.ffmpeg_exe
        assert "-y" in cmd
        assert "-loop" in cmd
        assert "5.0" in cmd
        assert "/tmp/img.png" in cmd
        assert "-filter_complex" in cmd
        assert "concat=n=1" in cmd[cmd.index("-filter_complex") + 1]
        assert cmd[-1] == "/tmp/out.mp4"
        # No audio mapping
        assert "-shortest" not in cmd

    def test_three_panels_no_audio(self, engine: AnimaticEngine) -> None:
        """Three panels should produce three inputs and concat=n=3."""
        panels = [
            Panel(image_path="/tmp/a.png", duration=2.0),
            Panel(image_path="/tmp/b.png", duration=3.0),
            Panel(image_path="/tmp/c.png", duration=4.0),
        ]
        cmd = engine._build_multi_panel_cmd(panels, "/tmp/out.mp4", audio_path=None)

        # Should have 3 -loop flags (one per panel)
        loop_count = cmd.count("-loop")
        assert loop_count == 3

        # All three images present
        assert "/tmp/a.png" in cmd
        assert "/tmp/b.png" in cmd
        assert "/tmp/c.png" in cmd

        # Concat with n=3
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "concat=n=3:v=1:a=0" in filter_str

    def test_single_panel_with_audio(self, engine: AnimaticEngine) -> None:
        """Single panel with audio should map audio and use -shortest."""
        panels = [Panel(image_path="/tmp/img.png", duration=5.0)]
        cmd = engine._build_multi_panel_cmd(panels, "/tmp/out.mp4", audio_path="/tmp/audio.mp3")

        assert "/tmp/audio.mp3" in cmd
        assert "-shortest" in cmd
        assert "-c:a" in cmd
        assert "copy" in cmd
        # Audio is the second input (index 1)
        assert "1:a" in cmd

    def test_three_panels_with_audio(self, engine: AnimaticEngine) -> None:
        """Three panels with audio should map audio at index 3."""
        panels = [
            Panel(image_path="/tmp/a.png", duration=2.0),
            Panel(image_path="/tmp/b.png", duration=3.0),
            Panel(image_path="/tmp/c.png", duration=4.0),
        ]
        cmd = engine._build_multi_panel_cmd(panels, "/tmp/out.mp4", audio_path="/tmp/audio.mp3")

        # Audio is the 4th input (index 3)
        assert "3:a" in cmd
        assert "-shortest" in cmd

    def test_scaling_in_filter(self, engine: AnimaticEngine) -> None:
        """Filter should include scaling and padding for consistent dimensions."""
        panels = [Panel(image_path="/tmp/img.png", duration=3.0)]
        cmd = engine._build_multi_panel_cmd(panels, "/tmp/out.mp4", audio_path=None)

        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "scale=1920:1080" in filter_str
        assert "pad=1920:1080" in filter_str
        assert "setsar=1" in filter_str

    def test_codec_settings(self, engine: AnimaticEngine) -> None:
        """Command should use libx264 ultrafast with yuv420p pixel format."""
        panels = [Panel(image_path="/tmp/img.png", duration=3.0)]
        cmd = engine._build_multi_panel_cmd(panels, "/tmp/out.mp4", audio_path=None)

        assert "libx264" in cmd
        assert "ultrafast" in cmd
        assert "yuv420p" in cmd

    def test_panel_durations_in_cmd(self, engine: AnimaticEngine) -> None:
        """Each panel's duration should appear as a -t argument."""
        panels = [
            Panel(image_path="/tmp/a.png", duration=1.5),
            Panel(image_path="/tmp/b.png", duration=7.0),
        ]
        cmd = engine._build_multi_panel_cmd(panels, "/tmp/out.mp4", audio_path=None)

        assert "1.5" in cmd
        assert "7.0" in cmd


class TestPerPanelAudio:
    """Tests for _build_multi_panel_cmd with per-panel audio."""

    def test_single_panel_with_panel_audio(self, engine: AnimaticEngine) -> None:
        """Panel with its own audio should use concat with audio streams."""
        panel = Panel(image_path="/tmp/img.png", duration=5.0)
        panel.audio_path = "/tmp/voice.mp3"
        cmd = engine._build_multi_panel_cmd([panel], "/tmp/out.mp4", audio_path=None)

        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "concat=n=1:v=1:a=1" in filter_str
        assert "/tmp/voice.mp3" in cmd
        assert "-c:a" in cmd
        assert "aac" in cmd
        # Should NOT have -shortest (that's for global audio)
        assert "-shortest" not in cmd

    def test_mixed_panels_some_with_audio(self, engine: AnimaticEngine) -> None:
        """Panels without audio should get silence when others have audio."""
        p1 = Panel(image_path="/tmp/a.png", duration=3.0)
        p1.audio_path = "/tmp/voice1.mp3"
        p2 = Panel(image_path="/tmp/b.png", duration=2.0)
        # p2 has no audio — should get anullsrc silence
        cmd = engine._build_multi_panel_cmd([p1, p2], "/tmp/out.mp4", audio_path=None)

        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "concat=n=2:v=1:a=1" in filter_str
        assert "anullsrc" in filter_str
        assert "/tmp/voice1.mp3" in cmd

    def test_per_panel_audio_overrides_global(self, engine: AnimaticEngine) -> None:
        """When panels have per-panel audio, global audio_path should be ignored."""
        panel = Panel(image_path="/tmp/img.png", duration=5.0)
        panel.audio_path = "/tmp/voice.mp3"
        cmd = engine._build_multi_panel_cmd([panel], "/tmp/out.mp4", audio_path="/tmp/global.mp3")

        # Global audio should NOT appear in the command
        assert "/tmp/global.mp3" not in cmd
        assert "/tmp/voice.mp3" in cmd

    def test_all_panels_with_audio(self, engine: AnimaticEngine) -> None:
        """All panels with audio should produce atrim filters for each."""
        p1 = Panel(image_path="/tmp/a.png", duration=2.0)
        p1.audio_path = "/tmp/v1.mp3"
        p2 = Panel(image_path="/tmp/b.png", duration=3.0)
        p2.audio_path = "/tmp/v2.mp3"
        cmd = engine._build_multi_panel_cmd([p1, p2], "/tmp/out.mp4", audio_path=None)

        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "atrim" in filter_str
        assert "anullsrc" not in filter_str
        assert "/tmp/v1.mp3" in cmd
        assert "/tmp/v2.mp3" in cmd


class TestGetAudioDuration:
    """Tests for get_audio_duration stderr parsing."""

    def test_parses_duration(self, engine: AnimaticEngine) -> None:
        """Should parse HH:MM:SS.ss format from ffmpeg stderr."""
        fake_stderr = "  Duration: 00:01:23.45, start: 0.000000, bitrate: 128 kb/s"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stderr = fake_stderr
            result = engine.get_audio_duration("/tmp/test.mp3")

        assert result is not None
        assert abs(result - 83.45) < 0.01

    def test_parses_short_duration(self, engine: AnimaticEngine) -> None:
        """Should handle durations under a minute."""
        fake_stderr = "  Duration: 00:00:05.20, start: 0.000000"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stderr = fake_stderr
            result = engine.get_audio_duration("/tmp/test.mp3")

        assert result is not None
        assert abs(result - 5.2) < 0.01

    def test_returns_none_on_missing_duration(self, engine: AnimaticEngine) -> None:
        """Should return None when stderr has no Duration line."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stderr = "some other output"
            result = engine.get_audio_duration("/tmp/test.mp3")

        assert result is None

    def test_returns_none_on_subprocess_error(self, engine: AnimaticEngine) -> None:
        """Should return None when subprocess raises an error."""
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("fail")):
            result = engine.get_audio_duration("/tmp/test.mp3")

        assert result is None


class TestGenerateMultiPanelVideo:
    """Tests for generate_multi_panel_video validation."""

    def test_empty_panels_raises(self, engine: AnimaticEngine) -> None:
        """Should raise ValueError when given an empty panel list."""
        with pytest.raises(ValueError, match="At least one panel"):
            engine.generate_multi_panel_video([], "/tmp/out.mp4")
