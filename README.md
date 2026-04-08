# Storyboard Animatic

A free, fast storyboard animatic tool for game preproduction. Drag in images, add dialogue and audio, preview instantly, export video to share with your team on Discord.

## Quick Start

```
uv run python main.py
```

## What It Does

Drop storyboard images (png/jpg/gif) into the app, arrange them, add voice lines, and export an MP4 video your team can watch.

## Features

### Images & Panels
- Drag and drop images (png, jpg, gif) or click "Add Images"
- Reorder panels by dragging in the strip
- Duplicate or remove panels
- Set duration per panel (seconds)
- Keyboard shortcuts: arrow keys to navigate, Delete to remove, Space to play/pause, Ctrl+D to duplicate

### Dialogue & Notes
- **Dialogue field** — what the character says. Shows as yellow text during preview. Can be burned into the exported video as subtitles (white text, bottom of frame).
- **Notes field** — director/team feedback like "make this angrier." Can optionally be burned into the export (yellow text, top of frame). Also included in exported script.

### Audio
- **Add Audio button** — browse for mp3/wav/m4a files
- **Drag audio** onto the window — attaches to selected panel, or becomes global background audio if no panel is selected
- **Record button** — record from your microphone directly into a panel. Click Record, talk, click Stop. Re-recording replaces the old audio automatically.
- **Remove audio** — click the X button next to "Panel Audio"
- Panel duration auto-adjusts to match audio length

### Preview
- Play/Pause/Stop controls
- Scrub bar to jump to any point
- Timecode display
- Dialogue appears as yellow text during preview
- Status bar shows current panel, time, and playback state

### Export
- **Export Video** — renders MP4 with FFmpeg in a background thread
- **Burn dialogue into export** checkbox (ON by default) — dialogue appears as white subtitles at the bottom
- **Burn notes into export** checkbox (OFF by default) — notes appear as yellow text at the top
- **Export Script** — dumps all dialogue and notes to a text file for voice actors
- Asks before overwriting existing files
- Progress bar during export

### Project Management
- **Save Project** — saves as .animatic file (JSON format)
- **Load Project** — drag a .animatic file onto the window
- **Undo/Redo** — Ctrl+Z / Ctrl+Y for all operations (add, remove, reorder, duration, notes, dialogue)

## Testing

```
uv run pytest tests/
```

140 tests covering panel management, export, playback, undo/redo, and UI interactions.

## Lint & Format

```
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## TODO Before Shipping
- [ ] Manual test: drag images, add audio, preview, export on Windows
- [ ] Manual test: record audio from microphone
- [ ] Manual test: burn dialogue subtitles look good in exported MP4
- [ ] Manual test: burn notes look good in exported MP4
- [ ] Manual test: export script text file is readable
- [ ] Manual test: save/load project round-trips correctly
- [ ] Manual test: undo/redo works for all operations
- [ ] Package as .exe for Windows (PyInstaller)
- [ ] Test on Mac
- [ ] Clean up extra git branches (master, claude/*)
