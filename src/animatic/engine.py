"""FFmpeg engine for generating animatic videos.

Builds and executes FFmpeg commands to stitch storyboard images
and audio into MP4 video files.
"""

import os
import platform
import subprocess
import time
from typing import Optional

from imageio_ffmpeg import get_ffmpeg_exe

from animatic.models import Panel


def _get_subtitle_font_path() -> Optional[str]:
    """Return a path to a clean system font for subtitle rendering, or None."""
    system = platform.system()
    if system == "Windows":
        for candidate in (
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
        ):
            if os.path.exists(candidate):
                return candidate
    elif system == "Darwin":
        for candidate in (
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ):
            if os.path.exists(candidate):
                return candidate
    else:
        for candidate in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ):
            if os.path.exists(candidate):
                return candidate
    return None


class AnimaticEngine:
    """Builds and executes FFmpeg commands to generate animatic videos.

    Supports both single-image and multi-panel video generation.
    Uses imageio-ffmpeg to locate the FFmpeg binary cross-platform.
    """

    def __init__(self) -> None:
        """Initialize the engine and locate the FFmpeg binary."""
        self.ffmpeg_exe: str = get_ffmpeg_exe()

    def get_audio_duration(self, audio_path: str) -> Optional[float]:
        """Get the duration of an audio file in seconds.

        Uses ffmpeg (not ffprobe) since imageio-ffmpeg doesn't ship ffprobe.
        Parses the Duration line from ffmpeg's stderr output.

        Args:
            audio_path: Path to the audio file.

        Returns:
            Duration in seconds, or None if it can't be determined.
        """
        cmd = [self.ffmpeg_exe, "-i", audio_path, "-f", "null", "-"]
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                stdin=subprocess.DEVNULL,
            )
            # ffmpeg prints duration info to stderr
            output = result.stderr
            for line in output.split("\n"):
                if "Duration:" in line:
                    # Format: "  Duration: 00:01:23.45, ..."
                    time_str = line.split("Duration:")[1].split(",")[0].strip()
                    parts = time_str.split(":")
                    hours = float(parts[0])
                    minutes = float(parts[1])
                    seconds = float(parts[2])
                    return hours * 3600 + minutes * 60 + seconds
        except (IndexError, ValueError, subprocess.SubprocessError, FileNotFoundError):
            pass
        return None

    def generate_video(
        self,
        image_path: str,
        output_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
    ) -> str:
        """Stitch a single image and optional audio into an MP4 file.

        Convenience wrapper around generate_multi_panel_video for
        single-image use.

        Args:
            image_path: Absolute path to the input image.
            output_path: Absolute path for the output video.
            audio_path: Optional path to an audio file to include.
            duration: Duration of the video in seconds (used if no audio).

        Returns:
            The path to the generated video file.

        Raises:
            subprocess.CalledProcessError: If FFmpeg fails to execute.
        """
        panels = [Panel(image_path=image_path, duration=duration)]
        return self.generate_multi_panel_video(panels, output_path, audio_path)

    def generate_multi_panel_video(
        self,
        panels: list[Panel],
        output_path: str,
        audio_path: Optional[str] = None,
    ) -> str:
        """Concatenate multiple image panels into one MP4, optionally with audio.

        Uses FFmpeg's concat filter to join per-panel streams. Each panel
        is an image looped for its specified duration.

        Args:
            panels: Ordered list of Panel objects with image_path and duration.
            output_path: Where to write the final MP4.
            audio_path: Optional single audio track laid over the whole video.

        Returns:
            The output_path on success.

        Raises:
            subprocess.CalledProcessError: If FFmpeg fails.
            ValueError: If panels list is empty.
        """
        if not panels:
            raise ValueError("At least one panel is required.")

        start = time.time()
        cmd = self._build_multi_panel_cmd(panels, output_path, audio_path)

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        subprocess.run(cmd, check=True, startupinfo=startupinfo, stdin=subprocess.DEVNULL)
        elapsed = time.time() - start
        print(f"Render time: {elapsed:.2f} seconds")

        return output_path

    def _build_multi_panel_cmd(
        self,
        panels: list[Panel],
        output_path: str,
        audio_path: Optional[str],
        burn_notes: bool = False,
    ) -> list[str]:
        """Build the FFmpeg command for multi-panel concat.

        Supports three audio modes:
        - Per-panel audio: each panel has its own audio_path, concatenated
        - Global audio: one audio track laid over the whole video
        - No audio: video only

        Args:
            panels: Ordered list of Panel objects.
            output_path: Where to write the final MP4.
            audio_path: Optional global audio track path.

        Returns:
            The complete FFmpeg command as a list of strings.
        """
        cmd: list[str] = [self.ffmpeg_exe, "-y"]

        # Check if any panels have per-panel audio
        has_per_panel_audio = any(p.audio_path for p in panels)

        # Add inputs: image for each panel, then per-panel audio files
        input_idx = 0
        panel_video_inputs: list[int] = []
        panel_audio_inputs: dict[int, int] = {}

        for i, panel in enumerate(panels):
            cmd.extend(["-loop", "1", "-t", str(panel.duration), "-i", panel.image_path])
            panel_video_inputs.append(input_idx)
            input_idx += 1

        if has_per_panel_audio:
            for i, panel in enumerate(panels):
                if panel.audio_path:
                    cmd.extend(["-i", panel.audio_path])
                    panel_audio_inputs[i] = input_idx
                    input_idx += 1

        # Global audio (used when no per-panel audio)
        global_audio_idx: Optional[int] = None
        if audio_path and not has_per_panel_audio:
            global_audio_idx = input_idx
            cmd.extend(["-i", audio_path])

        # Build filter_complex
        scale_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
        )
        filter_parts: list[str] = []
        concat_inputs: list[str] = []
        font_path = _get_subtitle_font_path()

        for i, vid_idx in enumerate(panel_video_inputs):
            vlabel = f"v{i}"
            vfilter = scale_filter
            if burn_notes and panels[i].notes:
                escaped = self._escape_drawtext(panels[i].notes)
                font_clause = ""
                if font_path:
                    # Escape ':' in Windows paths so FFmpeg doesn't treat it as a separator
                    safe_font = font_path.replace("\\", "/").replace(":", "\\:")
                    font_clause = f"fontfile={safe_font}:"
                vfilter += (
                    f",drawtext={font_clause}text='{escaped}'"
                    ":fontsize=48:fontcolor=white"
                    ":borderw=3:bordercolor=black"
                    ":box=1:boxcolor=black@0.75:boxborderw=24"
                    ":x=(w-text_w)/2:y=h-th-80"
                )
            filter_parts.append(f"[{vid_idx}:v]{vfilter}[{vlabel}]")

            if has_per_panel_audio:
                alabel = f"a{i}"
                if i in panel_audio_inputs:
                    # Trim audio to panel duration
                    aidx = panel_audio_inputs[i]
                    filter_parts.append(
                        f"[{aidx}:a]atrim=0:{panel.duration},asetpts=PTS-STARTPTS[{alabel}]"
                    )
                else:
                    # Generate silence for panels without audio
                    dur = panels[i].duration
                    filter_parts.append(
                        f"anullsrc=r=44100:cl=stereo[{alabel}_raw];"
                        f"[{alabel}_raw]atrim=0:{dur},asetpts=PTS-STARTPTS[{alabel}]"
                    )
                concat_inputs.append(f"[{vlabel}][{alabel}]")
            else:
                concat_inputs.append(f"[{vlabel}]")

        if has_per_panel_audio:
            concat_str = "".join(concat_inputs) + f"concat=n={len(panels)}:v=1:a=1[outv][outa]"
            filter_parts.append(concat_str)
        else:
            concat_str = "".join(concat_inputs) + f"concat=n={len(panels)}:v=1:a=0[outv]"
            filter_parts.append(concat_str)

        cmd.extend(["-filter_complex", ";".join(filter_parts)])

        # Map outputs
        cmd.extend(["-map", "[outv]"])
        if has_per_panel_audio:
            cmd.extend(["-map", "[outa]", "-c:a", "aac"])
        elif global_audio_idx is not None:
            cmd.extend(["-map", f"{global_audio_idx}:a", "-c:a", "copy", "-shortest"])

        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                output_path,
            ]
        )
        return cmd

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        """Escape special characters for FFmpeg's drawtext filter."""
        text = text.replace("\\", "\\\\\\\\")
        text = text.replace("'", "'\\\\\\''")
        text = text.replace(":", "\\\\:")
        text = text.replace("%", "%%")
        return text
