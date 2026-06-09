# ngrok_url_watcher.ps1
# Polls http://127.0.0.1:4040/api/tunnels every 60 seconds.
# If the public URL changes (or the cache file is missing), updates
# data/cache/ngrok_url.txt and appends a timestamped entry to
# data/cache/ngrok_url_history.log.
# Uses ASCII only -- no Unicode box-drawing or em-dashes.

$CacheFile   = "C:\Users\neelj\nba-ai-system\data\cache\ngrok_url.txt"
$HistoryLog  = "C:\Users\neelj\nba-ai-system\data\cache\ngrok_url_history.log"
$NgrokApi    = "http://127.0.0.1:4040/api/tunnels"
$PollSeconds = 60

Write-Host "ngrok_url_watcher started. Polling every $PollSeconds seconds."
Write-Host "Cache : $CacheFile"
Write-Host "Log   : $HistoryLog"

while ($true) {
    $newUrl = $null

    try {
        $resp   = Invoke-WebRequest -Uri $NgrokApi -UseBasicParsing -ErrorAction Stop
        $json   = $resp.Content | ConvertFrom-Json
        $tunnel = $json.tunnels | Select-Object -First 1
        if ($tunnel -and $tunnel.public_url) {
            $newUrl = $tunnel.public_url.Trim()
        } else {
            Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - No tunnels found in ngrok response."
        }
    } catch {
        Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - ngrok unreachable: $($_.Exception.Message). Retrying in $PollSeconds s."
    }

    if ($newUrl) {
        $oldUrl = $null

        if (Test-Path $CacheFile) {
            try {
                $oldUrl = (Get-Content $CacheFile -Raw).Trim()
            } catch {
                $oldUrl = $null
            }
        }

        if ($oldUrl -ne $newUrl) {
            # Write new URL to cache file WITHOUT a UTF-8 BOM so consumers
            # (Python json clients reading /api/health public_url) don't see
            # the U+FEFF prefix that Set-Content -Encoding UTF8 emits in
            # Windows PowerShell 5.1.
            try {
                [System.IO.File]::WriteAllText($CacheFile, $newUrl, (New-Object System.Text.UTF8Encoding($false)))
            } catch {
                Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - ERROR writing cache file: $($_.Exception.Message)"
            }

            # Append to history log
            $ts      = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $oldDisp = if ($oldUrl) { $oldUrl } else { "(none)" }
            $logLine = "$ts | old=$oldDisp | new=$newUrl"
            try {
                Add-Content -Path $HistoryLog -Value $logLine -Encoding UTF8
            } catch {
                Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - ERROR writing history log: $($_.Exception.Message)"
            }

            Write-Host "$ts - URL changed: $oldDisp -> $newUrl"
        } else {
            Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - URL unchanged: $newUrl"
        }
    }

    Start-Sleep -Seconds $PollSeconds
}
