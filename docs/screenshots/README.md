# Screenshots for README

Save your screenshots into this folder with these exact filenames so the main README renders them correctly:

| Filename | What it should show |
|---|---|
| `01-empty.png` | Fresh app open — empty preview with "Drop images here..." placeholder |
| `02-panels-added.png` | Three panels in the strip, one selected, no audio yet |
| `03-recording.png` | Recording in progress — red "Stop Recording" button visible |
| `04-with-audio.png` | A panel with audio attached, duration auto-set to the audio length |
| `05-burn-notes-preview.png` | Notes typed in the field, yellow text overlaid on preview |
| `06-exporting.png` | Export running — progress bar visible (e.g. 58%) |
| `07-export-complete.png` | The "Open it now?" dialog after export finishes |
| `08-buttons-closeup.png` | Close-up of the button row (Add Images, Add Audio, Record, Save Project, Load Project) |
| `09-controls-closeup.png` | Close-up of the controls row (Duration, Duplicate, Remove Panel, Audio info, Notes, Play/Stop, scrub bar) |

After saving, run:
```
git add docs/screenshots/
git commit -m "Add README screenshots"
git push
```
