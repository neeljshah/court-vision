"""
video_fetcher.py — Download NBA highlight clips and calibrate court for new videos.

Uses yt-dlp to pull clips from YouTube/NBA.com, then auto-generates the panorama
and homography that the tracker needs for any new camera angle.

Public API
----------
    download_clip(url, label=None)           -> str  (local video path)
    list_downloaded()                        -> List[dict]
    calibrate_from_video(video_path,
                         resources_dir=None) -> dict  (M, M1, pano paths)
    CURATED_CLIPS                            — dict of labelled YouTube URLs
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import List, Optional

import cv2
import numpy as np

PROJECT_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_VIDEOS_DIR  = os.path.join(PROJECT_DIR, "data", "videos")
_DEFAULT_RES = os.path.join(PROJECT_DIR, "resources")

# ── Curated search queries ────────────────────────────────────────────────────
# Search-based: always finds available content. yt-dlp picks the top result.
# Use broadcast/arena-cam angle queries — side-court is best for our tracker.
CURATED_CLIPS: dict[str, str] = {
    # Label                   Search query (prefixed with ytsearch:)
    # NOTE: "full game replay" targets 2-3 hour videos, not highlight reels.
    # These channels reliably post full game replays: NBA (official), House of Highlights,
    # and various fan channels. All need --max-filesize raised to 3000m.
    "nba_gsw_full_2024":    "ytsearch:Golden State Warriors full game replay 2024-25 NBA",
    "nba_bos_full_2024":    "ytsearch:Boston Celtics full game replay 2024-25 NBA",
    "nba_lakers_full_2024": "ytsearch:Los Angeles Lakers full game replay 2024-25 NBA",
    "nba_okc_full_2024":    "ytsearch:Oklahoma City Thunder full game replay 2024-25 NBA",
    "nba_den_full_2024":    "ytsearch:Denver Nuggets full game replay 2024-25 NBA",
    "nba_mia_full_2024":    "ytsearch:Miami Heat full game replay 2024-25 NBA",
    "nba_mil_full_2024":    "ytsearch:Milwaukee Bucks full game replay 2024-25 NBA",
    "nba_phx_full_2024":    "ytsearch:Phoenix Suns full game replay 2024-25 NBA",
    # Condensed replays (~45 min, no timeouts/dead balls) — more practical for tracker
    "nba_gsw_condensed_2024":    "ytsearch:Golden State Warriors condensed game replay 2024-25",
    "nba_bos_condensed_2024":    "ytsearch:Boston Celtics condensed game replay 2024-25",
    "nba_lakers_condensed_2024": "ytsearch:Los Angeles Lakers condensed game replay 2024-25",
}

# ─────────────────────────────────────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────────────────────────────────────

def download_clip(
    url: str,
    label: Optional[str] = None,
    max_height: int = 720,
    max_duration_secs: int = 300,
) -> str:
    """
    Download a video using yt-dlp.

    Supports:
      - YouTube URLs:          https://www.youtube.com/watch?v=...
      - yt-dlp search syntax: ytsearch:NBA highlights broadcast 2024

    Args:
        url:               URL or ytsearch: query.
        label:             Output filename stem. Auto-derived if None.
        max_height:        Cap resolution (720p is enough for tracking).
        max_duration_secs: Skip videos longer than this (seconds).

    Returns:
        Absolute path to the downloaded .mp4 file.
    """
    _require_ytdlp()
    os.makedirs(_VIDEOS_DIR, exist_ok=True)

    stem     = label or _url_to_stem(url)
    out_tmpl = os.path.join(_VIDEOS_DIR, f"{stem}.%(ext)s")

    # Check for any already-downloaded file with this stem
    existing = _find_video(stem)
    if existing:
        print(f"Already downloaded: {existing}")
        return existing

    # No ffmpeg = can't merge streams; use single-stream format only
    has_ffmpeg = _check_ffmpeg()
    if has_ffmpeg:
        fmt = (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/best[height<={max_height}][ext=mp4]/best[height<={max_height}]/best"
        )
    else:
        # mp4 with audio already muxed in (progressive stream)
        fmt = (
            f"best[height<={max_height}][ext=mp4]"
            f"/worst[height>={max_height//2}][ext=mp4]"
            f"/best[ext=mp4]/best"
        )

    # --match-filter silently drops videos that don't match — omit it;
    # use --max-filesize as the only hard limit instead.
    cmd = [
        "yt-dlp",
        "--format", fmt,
        "--max-filesize", "4000m",   # full game replay ~2-4 GB at 720p
        "--output", out_tmpl,
        "--print", "after_move:filepath",
        "--no-playlist",
        "--no-warnings",
    ]

    # Check for manually-exported cookie file first (most reliable)
    cookie_file = os.path.join(_VIDEOS_DIR, "youtube_cookies.txt")
    if os.path.exists(cookie_file):
        cmd += ["--cookies", cookie_file]
        cmd.append(url)
        result = subprocess.run(cmd, capture_output=True, text=True)
        out_path = (result.stdout.strip().splitlines() or [""])[-1]
        if os.path.exists(out_path):
            size_mb = os.path.getsize(out_path) / 1e6
            print(f"  Done ({size_mb:.1f} MB) -> {out_path}")
            _update_manifest(stem, url, out_path)
            return out_path

    # Try browser cookies — each installed browser until one works
    browsers = _detect_browsers()
    cmd.append(url)
    for browser in browsers:
        full_cmd = cmd[:-1] + ["--cookies-from-browser", browser, cmd[-1]]
        result = subprocess.run(full_cmd, capture_output=True, text=True)
        out_path = (result.stdout.strip().splitlines() or [""])[-1]
        if os.path.exists(out_path):
            size_mb = os.path.getsize(out_path) / 1e6
            print(f"  Done ({size_mb:.1f} MB) -> {out_path}")
            _update_manifest(stem, url, out_path)
            return out_path
        found = _find_video(stem)
        if found:
            _update_manifest(stem, url, found)
            return found
        if "Could not copy" not in (result.stderr or ""):
            break  # real error, not a locked DB — don't retry other browsers

    # All browsers failed — give actionable instructions
    err = (result.stderr or result.stdout or "").strip()[:300]
    cookie_file = os.path.join(_VIDEOS_DIR, "youtube_cookies.txt")
    raise RuntimeError(
        f"YouTube download failed (bot detection).\n"
        f"Error: {err}\n\n"
        "Fix — choose one:\n"
        "  A) Close Chrome AND Edge completely, then retry.\n"
        "  B) Export cookies to a file (works even with browser open):\n"
        "       1. Install 'Get cookies.txt LOCALLY' Chrome extension\n"
        "       2. Visit youtube.com while logged in to Google\n"
        f"      3. Export cookies -> save to:  {cookie_file}\n"
        "       4. Retry — fetcher auto-detects the file.\n"
        "  C) Use a local video instead:\n"
        "       python benchmark.py --local resources/Short4Mosaicing.mp4"
    )

    is_search = url.startswith("ytsearch")
    print(f"{'Searching + downloading' if is_search else 'Downloading'}: {url[:80]}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    # --print after_move:filepath writes the final path to stdout
    out_path = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else None
    if out_path and os.path.exists(out_path):
        size_mb = os.path.getsize(out_path) / 1e6
        print(f"  Done ({size_mb:.1f} MB) -> {out_path}")
        _update_manifest(stem, url, out_path)
        return out_path

    # Fallback: scan directory for any new video file with this stem
    found = _find_video(stem)
    if found:
        _update_manifest(stem, url, found)
        return found

    err = (result.stderr or result.stdout or "unknown error").strip()[:400]
    raise RuntimeError(f"yt-dlp failed (code {result.returncode}):\n{err}")


def list_downloaded() -> list:
    """Return list of {label, url, path, size_mb} for all downloaded clips."""
    manifest = _load_manifest()
    result = []
    for label, info in manifest.items():
        path = info.get("path", "")
        result.append({
            "label":   label,
            "url":     info.get("url", ""),
            "path":    path,
            "size_mb": round(os.path.getsize(path) / 1e6, 1) if os.path.exists(path) else 0,
        })
    return result


def download_batch(
    clips: Optional[dict] = None,
    max_clips: int = 5,
    max_height: int = 720,
) -> List[str]:
    """
    Download multiple clips from CURATED_CLIPS (or a provided dict).

    Skips clips already present in data/videos/ (uses existing download_clip
    skip logic). Stops after max_clips successful downloads.

    Args:
        clips:     dict of {label: url/query}. Defaults to CURATED_CLIPS.
        max_clips: Maximum number of clips to download in one batch.
        max_height: Max video height in pixels.

    Returns:
        List of local video paths for all downloaded clips.
    """
    if clips is None:
        clips = CURATED_CLIPS
    paths: List[str] = []
    for label, url in clips.items():
        if len(paths) >= max_clips:
            break
        try:
            path = download_clip(url, label=label, max_height=max_height)
            if path:
                paths.append(path)
                print(f"[download_batch] {label} -> {path}")
        except RuntimeError as exc:
            msg = str(exc)
            if "bot detection" in msg.lower() or "403" in msg or "sign in" in msg.lower():
                print(
                    f"[download_batch] Bot detection on {label}. "
                    "Export cookies via 'Get cookies.txt LOCALLY' Chrome extension -> cookies.txt"
                )
            else:
                print(f"[download_batch] SKIP {label}: {exc}")
    return paths


def download_curated(keys: Optional[list] = None) -> list:
    """
    Download a subset (or all) of CURATED_CLIPS.

    Args:
        keys: List of labels from CURATED_CLIPS, or None for all.

    Returns:
        List of local video paths successfully downloaded.
    """
    targets = {k: v for k, v in CURATED_CLIPS.items()
               if keys is None or k in keys}
    paths = []
    for label, url in targets.items():
        try:
            paths.append(download_clip(url, label=label))
        except RuntimeError as e:
            print(f"  ⚠  Skipped {label}: {e}")
    return paths


# ─────────────────────────────────────────────────────────────────────────────
# Court calibration for new videos
# ─────────────────────────────────────────────────────────────────────────────

def calibrate_from_video(
    video_path: str,
    resources_dir: Optional[str] = None,
    sample_frames: int = 8,
    topcut: int = 320,
) -> dict:
    """
    Auto-generate panorama + court homography from a new video.

    Samples `sample_frames` evenly-spaced frames, stitches a panorama, then
    runs rectangularize + rectify to produce M1 (panorama → 2D court map).
    Saves outputs to `resources_dir` so the pipeline can load them.

    Args:
        video_path:    Path to .mp4 clip.
        resources_dir: Where to save pano_enhanced.png + Rectify1.npy.
                       Defaults to a per-video subfolder under data/videos/.
        sample_frames: Number of frames to sample for panorama stitching.
        topcut:        Rows to crop from top of each frame (scoreboard).

    Returns:
        {
          "pano_path":   str,
          "rectify_path": str,
          "map_2d_path": str,
          "success":     bool,
          "error":       str or None,
        }
    """
    sys.path.insert(0, PROJECT_DIR)
    from src.tracking.rectify_court import collage, binarize_erode_dilate, rectangularize_court, rectify

    if resources_dir is None:
        stem = os.path.splitext(os.path.basename(video_path))[0]
        resources_dir = os.path.join(_VIDEOS_DIR, f"{stem}_resources")

    os.makedirs(resources_dir, exist_ok=True)
    pano_path    = os.path.join(resources_dir, "pano_enhanced.png")
    rectify_path = os.path.join(resources_dir, "Rectify1.npy")

    # Use default 2d_map.png (court outline is fixed)
    map_2d_src  = os.path.join(_DEFAULT_RES, "2d_map.png")
    map_2d_path = map_2d_src  # reuse shared court diagram

    result = {"pano_path": pano_path, "rectify_path": rectify_path,
               "map_2d_path": map_2d_path, "success": False, "error": None}

    # If already calibrated, skip
    if os.path.exists(pano_path) and os.path.exists(rectify_path):
        result["success"] = True
        return result

    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    indices = [int(total * i / (sample_frames - 1)) for i in range(sample_frames)]
    frames = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, f = cap.read()
        if ok and f is not None:
            frames.append(f[topcut:])
    cap.release()

    if len(frames) < 2:
        result["error"] = "Not enough readable frames for panorama stitching."
        return result

    try:
        pano = collage(frames, direction=1, plot=False)
        if pano is None or pano.size == 0:
            result["error"] = "collage() returned empty panorama."
            return result

        # Pad + save panorama
        pano_padded = np.vstack((
            pano,
            np.zeros((100, pano.shape[1], pano.shape[2]), dtype=pano.dtype)
        ))
        cv2.imwrite(pano_path, pano_padded)

        # Compute homography
        binary  = binarize_erode_dilate(pano_padded, plot=False)
        _, corners = rectangularize_court(binary, plot=False)
        rectify(pano_padded, corners, plot=False)

        # rectify() saves to _DEFAULT_RES — copy to our resources_dir
        default_r1 = os.path.join(_DEFAULT_RES, "Rectify1.npy")
        if os.path.exists(default_r1):
            import shutil
            shutil.copy(default_r1, rectify_path)

        result["success"] = True
        print(f"  Calibration saved: {resources_dir}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  ⚠  Calibration failed: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detect_browsers() -> list:
    """Return list of installed browsers yt-dlp can pull cookies from."""
    import winreg
    candidates = [
        ("firefox", r"SOFTWARE\Mozilla\Mozilla Firefox"),
        ("edge",    r"SOFTWARE\Microsoft\Edge\BLBeacon"),
        ("brave",   r"SOFTWARE\BraveSoftware\Brave-Browser\BLBeacon"),
        ("chrome",  r"SOFTWARE\Google\Chrome\BLBeacon"),
    ]
    found = []
    for browser, reg_key in candidates:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                winreg.OpenKey(hive, reg_key)
                found.append(browser)
                break
            except OSError:
                continue
    return found


def _find_video(stem: str) -> Optional[str]:
    """Return the first existing video file matching stem in _VIDEOS_DIR."""
    if not os.path.isdir(_VIDEOS_DIR):
        return None
    for ext in (".mp4", ".webm", ".mkv", ".mov"):
        p = os.path.join(_VIDEOS_DIR, f"{stem}{ext}")
        if os.path.exists(p):
            return p
    return None


def _check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _require_ytdlp():
    result = subprocess.run(["yt-dlp", "--version"], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            "yt-dlp not found. Install with: pip install yt-dlp"
        )


def _url_to_stem(url: str) -> str:
    """Derive a safe filename stem from a URL."""
    import re
    # Extract YouTube video ID if present
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    return re.sub(r"[^A-Za-z0-9_-]", "_", url)[-40:]


def _manifest_path() -> str:
    return os.path.join(_VIDEOS_DIR, "manifest.json")


def _load_manifest() -> dict:
    p = _manifest_path()
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}


def _update_manifest(label: str, url: str, path: str):
    manifest = _load_manifest()
    manifest[label] = {"url": url, "path": path}
    os.makedirs(_VIDEOS_DIR, exist_ok=True)
    with open(_manifest_path(), "w") as f:
        json.dump(manifest, f, indent=2)
