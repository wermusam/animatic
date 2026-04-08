"""Data models for the animatic project.

Provides Panel and Project classes to represent a multi-panel
storyboard animatic with optional audio and notes.
"""

import json
import uuid
from typing import Optional


class Panel:
    """A single storyboard panel with an image, duration, and optional audio/notes.

    Attributes:
        image_path: Absolute path to the panel's image file.
        duration: How long this panel is shown in seconds.
        panel_id: Unique identifier for this panel.
        audio_path: Optional path to per-panel audio.
        notes: Dialogue or direction notes for this panel.
    """

    def __init__(self, image_path: str, duration: float = 3.0) -> None:
        self.image_path: str = image_path
        self.duration: float = duration
        self.panel_id: str = uuid.uuid4().hex[:8]
        self.audio_path: Optional[str] = None
        self.dialogue: str = ""
        self.notes: str = ""

    def __repr__(self) -> str:
        return f"Panel(image_path='{self.image_path}', duration={self.duration})"

    def to_dict(self) -> dict:
        """Serialize this panel to a dictionary.

        Returns:
            Dictionary with all panel fields.
        """
        return {
            "image_path": self.image_path,
            "duration": self.duration,
            "panel_id": self.panel_id,
            "audio_path": self.audio_path,
            "dialogue": self.dialogue,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Panel":
        """Reconstruct a Panel from a dictionary.

        Args:
            data: Dictionary with panel fields.

        Returns:
            A Panel with the saved state restored.
        """
        panel = cls(image_path=data["image_path"], duration=data.get("duration", 3.0))
        panel.panel_id = data.get("panel_id", panel.panel_id)
        panel.audio_path = data.get("audio_path")
        panel.dialogue = data.get("dialogue", "")
        panel.notes = data.get("notes", "")
        return panel


class Project:
    """The complete animatic project state.

    Holds an ordered list of panels and an optional audio track.

    Attributes:
        panels: Ordered list of Panel objects.
        audio_path: Optional path to the audio file.
        output_path: Optional path for the exported video.
    """

    def __init__(self) -> None:
        self.panels: list[Panel] = []
        self.audio_path: Optional[str] = None
        self.output_path: Optional[str] = None

    def add_panel(self, image_path: str, duration: float = 3.0) -> Panel:
        """Create a new panel and append it to the project.

        Args:
            image_path: Absolute path to the image file.
            duration: How long this panel is shown in seconds.

        Returns:
            The newly created Panel.
        """
        panel = Panel(image_path=image_path, duration=duration)
        self.panels.append(panel)
        return panel

    def remove_panel(self, panel_id: str) -> None:
        """Remove a panel by its unique ID.

        Args:
            panel_id: The ID of the panel to remove.
        """
        self.panels = [p for p in self.panels if p.panel_id != panel_id]

    def duplicate_panel(self, panel_id: str) -> Optional[Panel]:
        """Duplicate a panel and insert the copy right after the original.

        Args:
            panel_id: The ID of the panel to duplicate.

        Returns:
            The new Panel, or None if the original wasn't found.
        """
        for i, p in enumerate(self.panels):
            if p.panel_id == panel_id:
                new_panel = Panel(image_path=p.image_path, duration=p.duration)
                new_panel.audio_path = p.audio_path
                new_panel.dialogue = p.dialogue
                new_panel.notes = p.notes
                self.panels.insert(i + 1, new_panel)
                return new_panel
        return None

    def reorder(self, old_index: int, new_index: int) -> None:
        """Move a panel from one position to another.

        Args:
            old_index: Current position of the panel.
            new_index: Desired new position.
        """
        if 0 <= old_index < len(self.panels) and 0 <= new_index < len(self.panels):
            panel = self.panels.pop(old_index)
            self.panels.insert(new_index, panel)

    def total_duration(self) -> float:
        """Sum of all panel durations in seconds.

        Returns:
            Total duration across all panels.
        """
        return sum(p.duration for p in self.panels)

    def to_dict(self) -> dict:
        """Serialize the project to a dictionary.

        Returns:
            Dictionary with all project state.
        """
        return {
            "panels": [p.to_dict() for p in self.panels],
            "audio_path": self.audio_path,
            "output_path": self.output_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        """Reconstruct a Project from a dictionary.

        Args:
            data: Dictionary with project fields.

        Returns:
            A Project with the saved state restored.
        """
        project = cls()
        project.panels = [Panel.from_dict(pd) for pd in data.get("panels", [])]
        project.audio_path = data.get("audio_path")
        project.output_path = data.get("output_path")
        return project

    def save(self, path: str) -> None:
        """Save the project to a JSON file.

        Args:
            path: File path to write to.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Project":
        """Load a project from a JSON file.

        Args:
            path: File path to read from.

        Returns:
            The loaded Project.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
