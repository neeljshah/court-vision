#!/bin/bash
# Download all full-game videos from manuelmazon channel locally.
# Run this while pod is off — builds a local library ready for batch processing.
# Usage: bash scripts/download_season_games.sh [MAX_JOBS]

MAX_JOBS=${1:-3}   # parallel downloads (adjust to your bandwidth)
OUT_DIR="data/videos/full_games"
mkdir -p "$OUT_DIR"

# Full list: YT_ID|GAME_ID|MATCHUP
# Generated from batch_from_channel.py dry-run output
GAMES=(
  "4MoMewm2j-o|0022500622|BKN_NYK_2026-01-21"
  "Nabp76SLZaM|0022500630|GSW_DAL_2026-01-22"
  "tu8IOgZoWm0|0022500629|DEN_WAS_2026-01-22"
  "-_d4k1r6x7M|0022500624|DET_NOP_2026-01-21"
  "gZde9IkIf7o|0022500621|IND_BOS_2026-01-21"
  "coYlCAzzpjI|0022500906|LAL_DEN_2026-03-05"
  "4uxDaDDzuic|0022500809|LAL_LAC_2026-02-20"
  "lYdjynqOzl4|0022500634|MIA_POR_2026-01-22"
  "mg-1tlNMQCs|0022500601|UTA_DAL_2026-01-17"
  "5-RZCY3agIE|0022500623|ATL_MEM_2026-01-21"
  "3gBeJyl7Szg|0022500585|CLE_PHI_2026-01-14"
  "kLwhJOEjoH0|0022500594|PHX_DET_2026-01-15"
  "FZAUuuuREg0|0022500593|OKC_HOU_2026-01-15"
  "6pjxpCEZq8E|0022500591|MIL_SAS_2026-01-15"
  "0nz5c3sNzKE|0022500609|MEM_ORL_2026-01-18"
  "4aAQ31ApYcY|0022500592|BOS_MIA_2026-01-15"
  "7jKNSIUQ37Q|0022500575|SAS_OKC_2026-01-13"
  "SE6dodowjdM|0022500586|NYK_SAC_2026-01-14"
  "IL-rGv_wy1I|0022500576|UTA_CHI_2026-01-13"
  "4n_xzQVZmfs|0022500577|TOR_IND_2026-01-13"
  "YUGjPLe4i7E|0022500584|MIA_PHX_2026-01-14"
  "l613C_9PB3s|0022500583|DEN_DAL_2026-01-14"
  "GA3al7Kv_nI|0022500582|WAS_LAC_2026-01-14"
  "r4MxQbHLvAw|0022500581|BKN_NOP_2026-01-14"
  "Tt8_qQDEvbk|0022500574|ATL_LAL_2026-01-13"
  "pGrVjtS7Xqg|0022500065|DET_BOS_2025-11-26"
  "nnjfhNBtxbU|0022500068|SAS_POR_2025-11-26"
  "31JcXMd1LdM|0022500067|PHX_SAC_2025-11-26"
  "mPvgwJbGuQY|0022500061|NYK_CHA_2025-11-26"
  "82fRGsTucis|0022500064|MIN_OKC_2025-11-26"
  "Uu2UnKE2YF0|0022500063|MIL_MIA_2025-11-26"
  "ggGIk3qlyDo|0022500066|MEM_NOP_2025-11-26"
  "JeLunEv3rcU|0022500062|IND_TOR_2025-11-26"
  "XCaGht2GmPg|0022500060|HOU_GSW_2025-11-26"
  "EyouzNHXJ8w|0022500055|LAL_LAC_2025-11-25"
  "-H-yCRmJFcc|0022500054|WAS_ATL_2025-11-25"
  "xi_cznnsnOY|0022500045|PHX_HOU_2025-11-24"
  "hzksYIV8rao|0022500044|TOR_CLE_2025-11-24"
  "qYkyG0fgjw0|0022500048|SAC_MIN_2025-11-24"
  "xDhMgmcUFXI|0022500043|NOP_CHI_2025-11-24"
  "KBlU_QWxrDM|0022500046|MIL_POR_2025-11-24"
  "pXpaHSmkowE|0022500047|MEM_DEN_2025-11-24"
  "QnT_XUTM_Bc|0022500053|MIA_DAL_2025-11-25"
  "s24TWnsdTcs|0022500035|ATL_CHA_2025-11-23"
  "tlB1Z1NhPgc|0022500036|BOS_ORL_2025-11-23"
  "yUlqAprr6MU|0022500038|CLE_LAC_2025-11-23"
  "B5R9jGSNWAE|0022500040|OKC_POR_2025-11-23"
  "DJFetU2X3To|0022500039|TOR_BKN_2025-11-23"
  "bMfHpHUV4d8|0022500042|PHI_MIA_2025-11-24"
  "Gg_etoYAF0A|0022500037|PHX_SAS_2025-11-23"
  "evw8n6E3m5Q|0022500034|UTA_LAL_2025-11-23"
  "GG2f11NYjKw|0022500041|BKN_NYK_2025-11-24"
  "dwvBRFudlEU|0022500049|GSW_UTA_2025-11-24"
  "sdGQNFathG4|0022500033|CHA_LAC_2025-11-23"
)

total=${#GAMES[@]}
downloaded=0
skipped=0
failed=0
active=0

download_one() {
  IFS='|' read -r YT_ID GAME_ID MATCHUP <<< "$1"
  OUT="$OUT_DIR/${GAME_ID}.mp4"
  if [ -f "$OUT" ] && [ "$(stat -c%s "$OUT" 2>/dev/null || echo 0)" -gt 100000000 ]; then
    echo "  SKIP $GAME_ID ($MATCHUP) — already downloaded"
    return 0
  fi
  echo "  DL   $GAME_ID ($MATCHUP)..."
  yt-dlp -f 'best[height<=720]/best' \
    "https://www.youtube.com/watch?v=$YT_ID" \
    -o "$OUT" --no-part -q 2>&1
  if [ -f "$OUT" ] && [ "$(stat -c%s "$OUT" 2>/dev/null || echo 0)" -gt 100000000 ]; then
    SIZE=$(du -h "$OUT" | cut -f1)
    echo "  OK   $GAME_ID — $SIZE"
  else
    echo "  FAIL $GAME_ID"
    rm -f "$OUT"
  fi
}

export -f download_one
export OUT_DIR

echo "=== Downloading $total full-game videos (${MAX_JOBS} parallel) ==="
echo "    Output: $OUT_DIR"
echo ""

printf '%s\n' "${GAMES[@]}" | xargs -P "$MAX_JOBS" -I{} bash -c 'download_one "$@"' _ {}

echo ""
echo "=== Done ==="
ls -lh "$OUT_DIR"/*.mp4 2>/dev/null | wc -l
echo "videos on disk"
