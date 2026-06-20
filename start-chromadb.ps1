#Requires -Version 5.1
<#
  Starts the standalone ChromaDB server WaveTouchOS's RAG tool-selection
  relies on (src/chroma_client.py connects to localhost:8100).

  Runs from its own isolated venv (.chromadb_venv) so it never touches the
  main app's global-Python site-packages. Forces the legacy pre-Rust
  SegmentAPI (see scripts/run_chromadb_server_legacy.py) because the
  chromadb_rust_bindings wheel chromadb 1.5.9 wants by default isn't
  published for this platform.

  Re-run this after every reboot — it does not currently auto-start.
#>
Set-Location -Path $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot ".chromadb_venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "ERROR: .chromadb_venv not found. Run:" -ForegroundColor Red
    Write-Host "  python -m venv .chromadb_venv"
    Write-Host "  .\.chromadb_venv\Scripts\python.exe -m pip install chromadb==1.5.9"
    exit 1
}

$existing = Get-NetTCPConnection -LocalPort 8100 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "ChromaDB already listening on port 8100 (PID $($existing[0].OwningProcess)) - nothing to do."
    exit 0
}

Write-Host "Starting ChromaDB server on http://localhost:8100 ..."
Start-Process -FilePath $venvPy -ArgumentList "scripts\run_chromadb_server_legacy.py" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden

Start-Sleep -Seconds 4
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:8100/api/v1/heartbeat" -UseBasicParsing -TimeoutSec 5
    Write-Host "ChromaDB is up (HTTP $($resp.StatusCode))." -ForegroundColor Green
} catch {
    Write-Host "ChromaDB did not respond - check for errors above." -ForegroundColor Yellow
}
