"""Tests for the Panel and Project data models."""

import json

from animatic.models import Panel, Project


class TestPanel:
    """Tests for the Panel class."""

    def test_panel_defaults(self) -> None:
        """Panel should have a 3-second default duration and a unique ID."""
        panel = Panel(image_path="/tmp/img.png")
        assert panel.image_path == "/tmp/img.png"
        assert panel.duration == 3.0
        assert len(panel.panel_id) == 8

    def test_panel_custom_duration(self) -> None:
        """Panel should accept a custom duration."""
        panel = Panel(image_path="/tmp/img.png", duration=5.5)
        assert panel.duration == 5.5

    def test_panel_unique_ids(self) -> None:
        """Each panel should get a unique ID."""
        p1 = Panel(image_path="/tmp/a.png")
        p2 = Panel(image_path="/tmp/b.png")
        assert p1.panel_id != p2.panel_id

    def test_panel_repr(self) -> None:
        """Panel repr should show image path and duration."""
        panel = Panel(image_path="/tmp/img.png", duration=2.0)
        assert "/tmp/img.png" in repr(panel)
        assert "2.0" in repr(panel)


class TestProject:
    """Tests for the Project class."""

    def test_empty_project(self) -> None:
        """New project should have no panels, no audio, no output."""
        project = Project()
        assert project.panels == []
        assert project.audio_path is None
        assert project.output_path is None

    def test_add_panel(self) -> None:
        """add_panel should append a panel and return it."""
        project = Project()
        panel = project.add_panel("/tmp/img.png")
        assert len(project.panels) == 1
        assert project.panels[0] is panel
        assert panel.image_path == "/tmp/img.png"

    def test_add_multiple_panels(self) -> None:
        """Adding multiple panels should preserve order."""
        project = Project()
        p1 = project.add_panel("/tmp/a.png")
        p2 = project.add_panel("/tmp/b.png")
        p3 = project.add_panel("/tmp/c.png")
        assert project.panels == [p1, p2, p3]

    def test_remove_panel(self) -> None:
        """remove_panel should remove the panel with the given ID."""
        project = Project()
        p1 = project.add_panel("/tmp/a.png")
        p2 = project.add_panel("/tmp/b.png")
        project.remove_panel(p1.panel_id)
        assert len(project.panels) == 1
        assert project.panels[0] is p2

    def test_remove_nonexistent_panel(self) -> None:
        """Removing a panel ID that doesn't exist should be a no-op."""
        project = Project()
        project.add_panel("/tmp/a.png")
        project.remove_panel("nonexistent")
        assert len(project.panels) == 1

    def test_reorder_panels(self) -> None:
        """reorder should move a panel from old_index to new_index."""
        project = Project()
        p1 = project.add_panel("/tmp/a.png")
        p2 = project.add_panel("/tmp/b.png")
        p3 = project.add_panel("/tmp/c.png")
        project.reorder(0, 2)
        assert project.panels == [p2, p3, p1]

    def test_reorder_out_of_bounds(self) -> None:
        """reorder with invalid indices should be a no-op."""
        project = Project()
        p1 = project.add_panel("/tmp/a.png")
        project.reorder(0, 5)
        assert project.panels == [p1]

    def test_total_duration(self) -> None:
        """total_duration should sum all panel durations."""
        project = Project()
        project.add_panel("/tmp/a.png", duration=2.0)
        project.add_panel("/tmp/b.png", duration=3.5)
        project.add_panel("/tmp/c.png", duration=1.0)
        assert project.total_duration() == 6.5

    def test_total_duration_empty(self) -> None:
        """total_duration on empty project should be 0."""
        project = Project()
        assert project.total_duration() == 0.0


class TestPanelSerialization:
    """Tests for Panel to_dict/from_dict."""

    def test_panel_to_dict(self) -> None:
        """to_dict should include all panel fields."""
        panel = Panel(image_path="/tmp/img.png", duration=5.0)
        panel.notes = "Hero enters"
        panel.audio_path = "/tmp/voice.mp3"
        d = panel.to_dict()
        assert d["image_path"] == "/tmp/img.png"
        assert d["duration"] == 5.0
        assert d["notes"] == "Hero enters"
        assert d["audio_path"] == "/tmp/voice.mp3"
        assert d["panel_id"] == panel.panel_id

    def test_panel_from_dict(self) -> None:
        """from_dict should restore all panel fields."""
        d = {
            "image_path": "/tmp/img.png",
            "duration": 4.0,
            "panel_id": "abc12345",
            "audio_path": "/tmp/voice.mp3",
            "notes": "Scene one",
        }
        panel = Panel.from_dict(d)
        assert panel.image_path == "/tmp/img.png"
        assert panel.duration == 4.0
        assert panel.panel_id == "abc12345"
        assert panel.audio_path == "/tmp/voice.mp3"
        assert panel.notes == "Scene one"

    def test_panel_from_dict_defaults(self) -> None:
        """from_dict with minimal data should use defaults."""
        d = {"image_path": "/tmp/img.png"}
        panel = Panel.from_dict(d)
        assert panel.duration == 3.0
        assert panel.audio_path is None
        assert panel.notes == ""


class TestDuplicatePanel:
    """Tests for Project.duplicate_panel."""

    def test_duplicate_creates_copy(self) -> None:
        """Duplicate should create a new panel with same image/duration/notes."""
        project = Project()
        p1 = project.add_panel("/tmp/a.png", duration=5.0)
        p1.notes = "Original"
        p1.audio_path = "/tmp/voice.mp3"

        dup = project.duplicate_panel(p1.panel_id)
        assert dup is not None
        assert dup.image_path == p1.image_path
        assert dup.duration == p1.duration
        assert dup.notes == p1.notes
        assert dup.audio_path == p1.audio_path
        assert dup.panel_id != p1.panel_id

    def test_duplicate_inserts_after_original(self) -> None:
        """Duplicate should be inserted right after the original."""
        project = Project()
        p1 = project.add_panel("/tmp/a.png")
        p2 = project.add_panel("/tmp/b.png")
        dup = project.duplicate_panel(p1.panel_id)
        assert project.panels == [p1, dup, p2]

    def test_duplicate_nonexistent(self) -> None:
        """Duplicating a nonexistent panel should return None."""
        project = Project()
        project.add_panel("/tmp/a.png")
        assert project.duplicate_panel("nonexistent") is None


class TestProjectSaveLoad:
    """Tests for Project save/load."""

    def test_save_and_load(self, tmp_path) -> None:
        """Save and load should round-trip all project state."""
        project = Project()
        p1 = project.add_panel("/tmp/a.png", duration=2.0)
        p1.notes = "Opening shot"
        p1.audio_path = "/tmp/narration.mp3"
        project.add_panel("/tmp/b.png", duration=4.0)
        project.audio_path = "/tmp/music.mp3"
        project.output_path = "/tmp/output.mp4"

        path = str(tmp_path / "test.animatic")
        project.save(path)

        loaded = Project.load(path)
        assert len(loaded.panels) == 2
        assert loaded.panels[0].image_path == "/tmp/a.png"
        assert loaded.panels[0].duration == 2.0
        assert loaded.panels[0].notes == "Opening shot"
        assert loaded.panels[0].audio_path == "/tmp/narration.mp3"
        assert loaded.panels[1].image_path == "/tmp/b.png"
        assert loaded.audio_path == "/tmp/music.mp3"
        assert loaded.output_path == "/tmp/output.mp4"

    def test_save_creates_valid_json(self, tmp_path) -> None:
        """Saved file should be valid JSON."""
        project = Project()
        project.add_panel("/tmp/a.png")
        path = str(tmp_path / "test.animatic")
        project.save(path)

        with open(path, "r") as f:
            data = json.load(f)
        assert "panels" in data
        assert len(data["panels"]) == 1

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict and from_dict should round-trip."""
        project = Project()
        p1 = project.add_panel("/tmp/a.png", duration=2.5)
        p1.notes = "Test"
        project.audio_path = "/tmp/bg.mp3"

        d = project.to_dict()
        restored = Project.from_dict(d)
        assert len(restored.panels) == 1
        assert restored.panels[0].notes == "Test"
        assert restored.audio_path == "/tmp/bg.mp3"
