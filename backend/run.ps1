# Lancement (Windows PowerShell) : cree/repare le venv, installe, demarre le serveur.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# --- 1. Trouver un interpreteur Python 3.10+ SAIN (pip + stdlib fonctionnels) ---
function Test-PyHealthy([string]$exe) {
  try {
    $probe = & $exe -c "import sys,html.entities,ssl,venv;print(sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -ne 0) { return $false }
    return ($probe -match "\((3), (1[0-9])\)")   # 3.10 .. 3.19
  } catch { return $false }
}
function Find-Python {
  $cands = @()
  foreach ($v in "3.12","3.11","3.13","3.10","3") {
    try { $p = & py "-$v" -c "import sys;print(sys.executable)" 2>$null
          if ($LASTEXITCODE -eq 0 -and $p) { $cands += $p } } catch {}
  }
  $cands += @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
              "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe")
  foreach ($c in (Get-Command python,python3 -ErrorAction SilentlyContinue)) { $cands += $c.Source }
  foreach ($c in ($cands | Select-Object -Unique)) {
    if ((Test-Path $c) -and (Test-PyHealthy $c)) { return $c }
  }
  throw "Aucun Python 3.10+ sain trouve (pip + stdlib). Installez-le depuis https://www.python.org/downloads/ puis relancez."
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

# --- 2. venv : creer, ou reparer s'il est casse ---
$venvOk = (Test-Path $venvPy)
if ($venvOk) {
  & $venvPy -c "import ssl,html.entities" 2>$null
  if ($LASTEXITCODE -ne 0) { Write-Host "venv casse -> reconstruction" -ForegroundColor Yellow; $venvOk = $false }
}
if (-not $venvOk) {
  if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
  $base = Find-Python
  Write-Host "Python de base : $base"
  & $base -m venv .venv
}

# --- 3. dependances ---
& $venvPy -m pip install -q --upgrade pip
& $venvPy -m pip install -q -r requirements.txt
& $venvPy -c "import fastapi,uvicorn,httpx,qrcode,PIL,dotenv" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Reinstallation forcee des dependances..." -ForegroundColor Yellow
  & $venvPy -m pip install --force-reinstall --no-cache-dir -r requirements.txt
}

# --- 4. .env ---
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "-> .env cree : renseignez GEMINI_API_KEY dedans." -ForegroundColor Yellow
}

# --- 5. lancement ---
$env:PYTHONUTF8 = "1"
Write-Host "Serveur : http://localhost:8000  (Ctrl+C pour arreter)" -ForegroundColor Green
& $venvPy main.py
