#!/usr/bin/env python3
"""
Media Processing Automation
Downloads audio + cover art from links.txt, tries Deezer FLAC first,
falls back to regular yt-dlp, then runs post‑processing steps.
"""

import os
import sys
import subprocess
import re
import requests
from PIL import Image
from mutagen import File
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC, TPE1, TIT2, TDRC, TALB, TCON
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class MediaProcessor:
    SPOTIFY_CLIENT_ID = "" # Insert your Spotify Client ID here (example: "c9911aca87644ba68dab8338ccadb9cf")
    SPOTIFY_CLIENT_SECRET = "" # Insert your Spotify Client Secret here(example: "136b6806d41b4c5ead9116a698ca76e7")

    def __init__(self, folder_path=None):
        self.folder_path = folder_path or os.getcwd()
        self.stats = {
            'images_cropped': 0, 'images_skipped': 0, 'images_errors': 0,
            'opus_converted': 0, 'opus_skipped': 0, 'opus_errors': 0,
            'files_renamed': 0, 'rename_skipped': 0, 'rename_errors': 0,
            'covers_set': 0, 'covers_skipped': 0, 'covers_errors': 0,
            'covers_deleted': 0, 'delete_errors': 0,
            'artists_fixed': 0, 'artists_skipped': 0, 'artist_errors': 0,
            'deezer_downloaded': 0, 'deezer_errors': 0
        }
        self.sp = None
        try:
            self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                client_id=self.SPOTIFY_CLIENT_ID,
                client_secret=self.SPOTIFY_CLIENT_SECRET
            ))
        except Exception as e:
            print(f"⚠️ Spotify not available: {e}")

        self.cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
        self._ensure_cookies()

    # ------------------------------------------------------------------
    #  Cookies helper
    # ------------------------------------------------------------------
    def _ensure_cookies(self):
        if os.path.exists(self.cookies_file):
            return
        print("🍪 cookies.txt not found – exporting from Firefox...")
        try:
            subprocess.run([
                "yt-dlp",
                "--cookies-from-browser", "firefox",
                "--cookies", self.cookies_file,
                "--skip-download",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            ], check=True, stdout=subprocess.DEVNULL)
            print(f"✅ cookies.txt saved to {self.cookies_file}")
        except Exception as e:
            print(f"❌ Could not export cookies: {e}")
            self.cookies_file = None

    # ------------------------------------------------------------------
    #  Deezer helpers
    # ------------------------------------------------------------------
    def search_deezer(self, artist, title):
        clean_artist = re.sub(r'\s*-\s*Topic$', '', artist).strip()
        clean_title = re.sub(r'\s*\([^)]*\)$', '', title).strip()
        query = f'artist:"{clean_artist}" track:"{clean_title}"'
        try:
            r = requests.get("https://api.deezer.com/search", params={'q': query}, timeout=10)
            r.raise_for_status()
            data = r.json().get('data', [])
            if data:
                track = data[0]
                return {
                    'id': track['id'],
                    'title': track['title'],
                    'artist': track['artist']['name'],
                    'album': track['album']['title'],
                    'cover': track['album']['cover_medium']
                }
        except Exception as e:
            print(f"⚠️ Deezer search error: {e}")
        return None

    def download_deezer_flac(self, track_info, base_name):
        url = f"https://www.deezer.com/track/{track_info['id']}"
        print(f"   Attempting Deezer FLAC via yt-dlp: {url}")
        try:
            subprocess.run([
                "yt-dlp", "-x", "--audio-format", "flac",
                "--audio-quality", "0",
                "-o", f"{base_name}.%(ext)s",
                url
            ], cwd=self.folder_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return False

    # ------------------------------------------------------------------
    #  Spotify genre
    # ------------------------------------------------------------------
    def fetch_genre(self, title, artist):
        if not self.sp:
            return None
        try:
            q = f"track:{title} artist:{artist}"
            results = self.sp.search(q=q, type="track", limit=1)
            items = results['tracks']['items']
            if items:
                artist_id = items[0]['artists'][0]['id']
                artist_info = self.sp.artist(artist_id)
                genres = artist_info.get('genres', [])
                return genres[0] if genres else None
        except Exception as e:
            print(f"   ⚠️ Spotify error: {e}")
        return None

    # ------------------------------------------------------------------
    #  Metadata setter
    # ------------------------------------------------------------------
    def set_metadata(self, audio_file, artist, title, album, release_year, genre):
        try:
            if isinstance(genre, list):
                genre = genre[0] if genre else None
            ext = audio_file.lower()
            if ext.endswith('.m4a'):
                audio = MP4(audio_file)
                if artist:      audio["\xa9ART"] = [artist]
                if title:       audio["\xa9nam"] = [title]
                if album:       audio["\xa9alb"] = [album]
                if genre:       audio["\xa9gen"] = [genre]
                if release_year:
                    m = re.search(r"(19|20)\d{2}", release_year)
                    if m: audio["\xa9day"] = [m.group(0)]
                audio.save()
            elif ext.endswith('.flac'):
                audio = File(audio_file, easy=True) or File(audio_file)
                if artist: audio["artist"] = artist
                if title:  audio["title"] = title
                if album:  audio["album"] = album
                if genre:  audio["genre"] = genre
                if release_year:
                    m = re.search(r"(19|20)\d{2}", release_year)
                    if m: audio["date"] = m.group(0)
                audio.save()
            else:
                mp3 = MP3(audio_file, ID3=ID3)
                if not mp3.tags:
                    mp3.tags = ID3()
                tags = mp3.tags
                if artist: tags.add(TPE1(encoding=3, text=[artist]))
                if title:  tags.add(TIT2(encoding=3, text=[title]))
                if album:  tags.add(TALB(encoding=3, text=[album]))
                if genre:  tags.add(TCON(encoding=3, text=[genre]))
                if release_year:
                    m = re.search(r"(19|20)\d{2}", release_year)
                    if m: tags.add(TDRC(encoding=3, text=[m.group(0)]))
                mp3.save()
        except Exception as e:
            print(f"   ⚠️ Metadata error: {e}")

    # ------------------------------------------------------------------
    #  STEP 0 – download from links.txt
    # ------------------------------------------------------------------
    def step0_download_audio(self):
        print("\n" + "="*60)
        print("STEP 0: DOWNLOADING AUDIO + COVER ART")
        print("="*60)

        links_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "links.txt")
        if not os.path.exists(links_file):
            print("links.txt not found – skipping downloads.")
            return

        with open(links_file, "r", encoding="utf-8") as f:
            links = [line.strip() for line in f if line.strip()]
        if not links:
            print("No links in links.txt.")
            return
        print(f"Found {len(links)} link(s).")

        for i, link in enumerate(links, 1):
            print(f"\n[{i}/{len(links)}] {link}")
            artist = title = album = release_year = ""

            # Extract metadata from yt-dlp if possible
            try:
                fmt = r"%(artist)s|%(title)s|%(album)s|%(release_year)s"
                r = subprocess.run(
                    ["yt-dlp", "--print", fmt,
                     "--extractor-args", "youtube:player_client=android,web",
                     "--cookies", self.cookies_file,
                     link],
                    cwd=self.folder_path, capture_output=True, text=True, check=True
                )
                parts = r.stdout.strip().split("|")
                artist = parts[0] if len(parts) > 0 else ""
                title  = parts[1] if len(parts) > 1 else ""
                album  = parts[2] if len(parts) > 2 else ""
                release_year = parts[3] if len(parts) > 3 else ""
                print(f"   Metadata: {artist} - {title} ({album}) [{release_year}]")
            except Exception as e:
                print(f"   ⚠️ Metadata extraction: {e}")

            # Try Deezer first
            deezer_ok = False
            if artist and title:
                track_info = self.search_deezer(artist, title)
                if track_info:
                    safe_base = re.sub(r'[<>:"/\\|?*]', '_', f"{artist} - {title}")
                    if self.download_deezer_flac(track_info, safe_base):
                        self.stats['deezer_downloaded'] += 1
                        deezer_ok = True
                        # Download cover from Deezer
                        try:
                            if track_info.get('cover'):
                                img = requests.get(track_info['cover'], timeout=10)
                                if img.status_code == 200:
                                    with open(os.path.join(self.folder_path, f"{safe_base}.jpg"), 'wb') as f:
                                        f.write(img.content)
                                    print("   ✅ Deezer cover saved.")
                        except Exception as e:
                            print(f"   ⚠️ Deezer cover error: {e}")
                        # Find the downloaded FLAC and tag it
                        for ext in (".flac", ".m4a", ".mp3"):
                            candidate = os.path.join(self.folder_path, f"{safe_base}{ext}")
                            if os.path.exists(candidate):
                                genre = self.fetch_genre(title, artist)
                                self.set_metadata(candidate, artist, title, album,
                                                  release_year, genre)
                                print(f"   ✅ Tagged: {os.path.basename(candidate)}")
                                break
                    else:
                        self.stats['deezer_errors'] += 1
                        print("   Deezer FLAC download failed – falling back.")

            if not deezer_ok:
                # Fallback: standard yt-dlp audio + thumbnail
                if not self.cookies_file:
                    print("   ❌ Skipping: cookies.txt unavailable.")
                    continue
                try:
                    subprocess.run([
                        "yt-dlp", "-x", "--audio-format", "m4a",
                        "-f", "bestaudio/best",
                        "--extractor-args", "youtube:player_client=android,web",
                        "--cookies", self.cookies_file,
                        "-o", "%(title)s.%(ext)s", link
                    ], cwd=self.folder_path, check=True)
                    subprocess.run([
                        "yt-dlp", "--skip-download", "--write-thumbnail",
                        "--convert-thumbnails", "jpg",
                        "--extractor-args", "youtube:player_client=android,web",
                        "--cookies", self.cookies_file,
                        "-o", "%(title)s.%(ext)s", link
                    ], cwd=self.folder_path, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"   ❌ yt-dlp error: {e}")
                    continue

                # Find the downloaded file (best guess by title)
                audio_file = None
                for ext in (".m4a", ".mp3", ".flac"):
                    candidate = os.path.join(self.folder_path, f"{title}{ext}")
                    if os.path.exists(candidate):
                        audio_file = candidate
                        break
                if not audio_file:
                    # fallback: most recent audio file
                    files = sorted([os.path.join(self.folder_path, f) for f in os.listdir(self.folder_path)
                                    if f.lower().endswith(('.m4a','.mp3','.flac'))],
                                   key=os.path.getmtime, reverse=True)
                    audio_file = files[0] if files else None
                if audio_file:
                    genre = self.fetch_genre(title, artist)
                    self.set_metadata(audio_file, artist, title, album, release_year, genre)
                    print(f"   ✅ Fallback tagged: {os.path.basename(audio_file)}")
                else:
                    print("   ❌ Could not locate downloaded audio.")
            print("   Done.")

    # ------------------------------------------------------------------
    #  Image cropping, OPUS conversion, renaming, covers, etc.
    # ------------------------------------------------------------------
    def step1_crop_images(self):
        print("\n" + "="*60 + "\nSTEP 1: CROP IMAGES TO SQUARE\n" + "="*60)
        for f in os.listdir(self.folder_path):
            if f.lower().endswith(('.jpg','.jpeg','.png')):
                fp = os.path.join(self.folder_path, f)
                try:
                    with Image.open(fp) as img:
                        w, h = img.size
                        if w == h:
                            self.stats['images_skipped'] += 1
                            print(f"⏭ {f}")
                            continue
                        s = min(w, h)
                        left = (w - s) // 2
                        top = (h - s) // 2
                        cropped = img.crop((left, top, left+s, top+s))
                        cropped.save(fp)
                        self.stats['images_cropped'] += 1
                        print(f"✅ {f}")
                except Exception as e:
                    self.stats['images_errors'] += 1
                    print(f"❌ {f} - {e}")
        print(f"  Cropped: {self.stats['images_cropped']}, skipped: {self.stats['images_skipped']}, errors: {self.stats['images_errors']}")

    def step2_convert_opus(self):
        print("\n" + "="*60 + "\nSTEP 2: CONVERT OPUS TO M4A\n" + "="*60)
        try:
            subprocess.run(['ffmpeg','-version'], capture_output=True, check=True)
        except FileNotFoundError:
            print("ffmpeg not found – skipping.")
            return
        opus_files = [f for f in os.listdir(self.folder_path) if f.endswith('.opus')]
        if not opus_files:
            print("No .opus files found.")
            return
        for f in opus_files:
            src = os.path.join(self.folder_path, f)
            dst = os.path.join(self.folder_path, f.replace('.opus','.m4a'))
            if os.path.exists(dst):
                self.stats['opus_skipped'] += 1
                continue
            try:
                subprocess.run(['ffmpeg','-i',src,dst], check=True, capture_output=True)
                os.remove(src)
                self.stats['opus_converted'] += 1
                print(f"✅ {f} → {os.path.basename(dst)}")
            except Exception as e:
                self.stats['opus_errors'] += 1
                print(f"❌ {f} - {e}")
        print(f"  Converted: {self.stats['opus_converted']}, skipped: {self.stats['opus_skipped']}, errors: {self.stats['opus_errors']}")

    def step3_rename_files(self):
        print("\n" + "="*60 + "\nSTEP 3: REMOVE (text) FROM FILENAMES\n" + "="*60)
        for f in os.listdir(self.folder_path):
            fp = os.path.join(self.folder_path, f)
            if not os.path.isfile(fp) or f == os.path.basename(__file__):
                continue
            new_name = re.sub(r'\s*\([^)]*\)$', '', f).strip()
            if new_name == f:
                self.stats['rename_skipped'] += 1
                continue
            new_path = os.path.join(self.folder_path, new_name)
            if os.path.exists(new_path):
                self.stats['rename_skipped'] += 1
                continue
            try:
                os.rename(fp, new_path)
                self.stats['files_renamed'] += 1
                print(f"✅ {f} → {new_name}")
            except Exception as e:
                self.stats['rename_errors'] += 1
                print(f"❌ {f} - {e}")
        print(f"  Renamed: {self.stats['files_renamed']}, skipped: {self.stats['rename_skipped']}, errors: {self.stats['rename_errors']}")

    def step4_set_cover_art(self):
        print("\n" + "="*60 + "\nSTEP 4: EMBED COVER ART\n" + "="*60)
        music_ext = ('.mp3','.wav','.ogg','.flac','.m4a')
        img_ext = ('.png','.jpg','.jpeg')
        files = os.listdir(self.folder_path)
        music_files = [f for f in files if f.lower().endswith(music_ext)]
        image_files = [f for f in files if f.lower().endswith(img_ext)]

        def set_it(audio_path, img_path):
            if audio_path.endswith('.m4a'):
                a = MP4(audio_path)
                if 'covr' in a and a['covr']:
                    return False
                with open(img_path,'rb') as f:
                    a['covr'] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]
                a.save()
            else:
                a = MP3(audio_path, ID3=ID3)
                if a.tags and 'APIC:' in str(a.tags):
                    return False
                if not a.tags:
                    a.tags = ID3()
                with open(img_path,'rb') as f:
                    a.tags.add(APIC(mime='image/jpeg', type=3, desc='Cover', data=f.read()))
                a.save()
            return True

        for mf in music_files:
            base = os.path.splitext(mf)[0]
            match = next((im for im in image_files if os.path.splitext(im)[0] == base), None)
            if not match:
                self.stats['covers_skipped'] += 1
                continue
            try:
                if set_it(os.path.join(self.folder_path, mf), os.path.join(self.folder_path, match)):
                    self.stats['covers_set'] += 1
                    print(f"✅ {mf} ← {match}")
                else:
                    self.stats['covers_skipped'] += 1
                    print(f"⏭ {mf} (already had cover)")
            except Exception as e:
                self.stats['covers_errors'] += 1
                print(f"❌ {mf} - {e}")
        print(f"  Covers set: {self.stats['covers_set']}, skipped: {self.stats['covers_skipped']}, errors: {self.stats['covers_errors']}")

    def step5_delete_covers(self):
        print("\n" + "="*60 + "\nSTEP 5: DELETE JPG COVERS\n" + "="*60)
        jpgs = [f for f in os.listdir(self.folder_path) if f.lower().endswith('.jpg')]
        for f in jpgs:
            try:
                os.remove(os.path.join(self.folder_path, f))
                self.stats['covers_deleted'] += 1
                print(f"✅ {f}")
            except Exception as e:
                self.stats['delete_errors'] += 1
                print(f"❌ {f} - {e}")
        print(f"  Deleted: {self.stats['covers_deleted']}, errors: {self.stats['delete_errors']}")

    def step6_fix_artist_tags(self):
        print("\n" + "="*60 + "\nSTEP 6: REMOVE '- TOPIC' FROM ARTIST TAGS\n" + "="*60)
        for f in os.listdir(self.folder_path):
            if not f.lower().endswith(('.mp3','.flac','.m4a','.wav','.aac','.ogg','.wma')):
                continue
            fp = os.path.join(self.folder_path, f)
            try:
                audio = File(fp, easy=True)
                if not audio or 'artist' not in audio:
                    self.stats['artists_skipped'] += 1
                    continue
                original = audio['artist'][0]
                cleaned = original.replace(" - Topic", "").strip()
                if cleaned != original:
                    audio['artist'] = cleaned
                    audio.save()
                    self.stats['artists_fixed'] += 1
                    print(f"✅ {f}: {original} → {cleaned}")
                else:
                    self.stats['artists_skipped'] += 1
            except Exception as e:
                self.stats['artist_errors'] += 1
                print(f"❌ {f} - {e}")
        print(f"  Fixed: {self.stats['artists_fixed']}, skipped: {self.stats['artists_skipped']}, errors: {self.stats['artist_errors']}")

    # ------------------------------------------------------------------
    #  Run all
    # ------------------------------------------------------------------
    def run_all(self):
        print(f"Processing folder: {self.folder_path}")
        self.step0_download_audio()
        self.step1_crop_images()
        self.step2_convert_opus()
        self.step3_rename_files()
        self.step4_set_cover_art()
        self.step5_delete_covers()
        self.step6_fix_artist_tags()

        total_processed = (self.stats['images_cropped'] + self.stats['opus_converted'] +
                           self.stats['files_renamed'] + self.stats['covers_set'] +
                           self.stats['covers_deleted'] + self.stats['artists_fixed'] +
                           self.stats['deezer_downloaded'])
        total_errors = (self.stats['images_errors'] + self.stats['opus_errors'] +
                        self.stats['rename_errors'] + self.stats['covers_errors'] +
                        self.stats['delete_errors'] + self.stats['artist_errors'] +
                        self.stats['deezer_errors'])
        print(f"\n{'='*60}")
        print("ALL DONE")
        print(f"  Processed: {total_processed}, Errors: {total_errors}")
        print(f"{'='*60}")


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    if not os.path.isdir(folder):
        print(f"Not a directory: {folder}")
        sys.exit(1)
    MediaProcessor(folder).run_all()