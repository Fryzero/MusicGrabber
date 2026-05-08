# Media Processor

A single Python script that downloads music from YouTube/Deezer, grabs the best available quality, tags everything properly, and runs a set of file‑cleanup steps.

## What it does

1. **Download** – reads `links.txt` (one URL per line), extracts metadata with `yt-dlp`, tries to get a FLAC from Deezer, otherwise falls back to the best audio from the link.
2. **Genre from Spotify** – looks up the track on Spotify and embeds the genre automatically.
3. **Cover art** – downloads cover art (preferably from Deezer, otherwise from YouTube) and embeds it.
4. **Crop images** – makes all JPEG/PNG covers square (centered crop).
5. **Convert OPUS → M4A** – uses ffmpeg to convert any `.opus` files and deletes the originals.
6. **Rename files** – strips trailing parentheses like `Song (lyrics)` → `Song`.
7. **Embed covers** – matches image files with audio files and writes the cover into the metadata.
8. **Delete leftover images** – removes `.jpg` files after embedding.
9. **Fix artist tags** – removes the `- Topic` suffix often left by YouTube auto‑generated channels.

## Requirements

- Python 3.7+
- Pip packages listed in `requirements.txt`
- `ffmpeg` installed and available in PATH
- `yt-dlp` (will be installed via pip, but you can also use your system package)

### Install Python dependencies

```bash
pip install -r requirements.txt
