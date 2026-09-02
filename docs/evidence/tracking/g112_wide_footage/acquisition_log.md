# G112 acquisition log

All actions below were local-only. No queue, bridge configuration, cookie file,
credential, pod file, pod process, or downloader source code was changed.

| Candidate | URL | Anonymous bridge-compatible bounded acquisition | Result | Consequence |
|---|---|---|---|---|
| S1 | `https://www.youtube.com/watch?v=nLRe7AlSM7g` | Existing bridge `download_local()` with its cookie path set to a nonexistent local file; 16-minute section policy | Initial high-resolution attempt exceeded the bounded window and left only zero-byte partial artifacts. A separate no-cookie 2-second section attempt received HTTP 403 when yt-dlp handed the media URL to ffmpeg. | Not obtained; no census claimed. |
| F1 | `https://www.youtube.com/watch?v=UNyLHlZr-bI` | yt-dlp/ffmpeg section mechanism used by the existing bridge, no cookies | HTTP 403 from the anonymous media URL. | Not obtained; no census claimed. |
| B1 | `https://www.youtube.com/watch?v=ZtsLAC-DiBo` | yt-dlp/ffmpeg section mechanism used by the existing bridge, no cookies | A 00:00:10-00:00:12 section produced a valid 601,767-byte MP4. | Obtained; proceed to the fixed 20-frame census. |

The public player page alone is not treated as bridge-acquirable. The decision
is based on an actual bounded local acquisition attempt. No cookie retry is
permitted by G112.
