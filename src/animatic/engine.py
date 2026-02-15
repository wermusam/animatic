import os
import subprocess
from typing import Optional, List
from imageio_ffmpeg import get_ffmpeg_exe


class AnimaticEngine:
    """
    A logic handler for building and executing FFMPEG commands to
    generate animatics from images and audio."
    """

    def __init__(self) -> None:
        """initializes the engine and locates the ffmpeg binary."""
        self.ffmpeg_exe: str = get_ffmpeg_exe()

    def generate_video(
        self,
        image_path: str,
        output_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
    ) -> str:
        """
        Stitches an image and optioanl audio into an mp4 file.

        Args:
            image_path: Absolute Path to the input image.
            output_path: Absolute path for the output video.
            audio_path: Optional path to an audio file to include.
            duration: Duration of the video in seconds (used if no audio is provided)

        Returns:
            The path to the generated video file.

        Raises:
            subprocess.CalledProcessError: If FFMPEG fails to execute.
        """
        cmd: List[str] = [self.ffmpeg_exe, "-y"]
        cmd.extend(["-loop", "1", "-i", image_path])

        if audio_path:
            cmd.extend(["-i", audio_path, "-shortest"])
        else:
            cmd.extend(["-t", str(duration)])

        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-tune",
                "stillimage",
                "-c:a",
                "copy",
                "-pix_fmt",
                "yuv420p",
            ]
        )

        cmd.append(output_path)
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        subprocess.run(
            cmd, check=True, startupinfo=startupinfo, stdin=subprocess.DEVNULL
        )

        return output_path
