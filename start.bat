@echo off
setlocal enabledelayedexpansion
title ElectroVision

cd /d "%~dp0"

echo.
echo  === ElectroVision - Start ===
echo.

REM ── 1. Python / venv ─────────────────────────────────────────────────────────

if exist "C:\ev\Scripts\python.exe" (
    echo [OK] Venv C:\ev znaleziony.
    goto :check_deps
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [BLAD] Python nie znaleziony.
    echo        Zainstaluj Python 3.11+ z https://python.org
    pause
    exit /b 1
)

echo [INFO] Tworzenie C:\ev ...
python -m venv C:\ev
if %errorlevel% neq 0 (
    echo [BLAD] Nie mozna utworzyc venv.
    pause
    exit /b 1
)
echo [OK] Venv utworzony.

REM ── 2. Zaleznosci ────────────────────────────────────────────────────────────

:check_deps
C:\ev\Scripts\python.exe -c "import PySide6" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Zaleznosci zainstalowane.
    goto :check_ollama
)

echo [INFO] Instalowanie zaleznosci (kilka minut)...
C:\ev\Scripts\pip.exe install --upgrade pip --quiet
C:\ev\Scripts\pip.exe install -r "%~dp0requirements.txt"
if !errorlevel! neq 0 (
    echo [BLAD] Instalacja nie powiodla sie.
    pause
    exit /b 1
)
echo [OK] Zaleznosci zainstalowane.

REM ── 3. Ollama ─────────────────────────────────────────────────────────────────

:check_ollama
set OLLAMA=
set OLLAMA_STARTED=0

where ollama >nul 2>&1
if %errorlevel%==0 (
    set OLLAMA=ollama
    goto :try_start_ollama
)

if exist "%LOCALAPPDATA%\Ollama\ollama.exe" (
    set OLLAMA=%LOCALAPPDATA%\Ollama\ollama.exe
    goto :try_start_ollama
)

if exist "%PROGRAMFILES%\Ollama\ollama.exe" (
    set OLLAMA=%PROGRAMFILES%\Ollama\ollama.exe
    goto :try_start_ollama
)

echo [INFO] Ollama nie znaleziona - AI niedostepne.
echo        Pobierz: https://ollama.ai
goto :start_app

:try_start_ollama
powershell -NoProfile -Command "try{(New-Object Net.WebClient).DownloadString('http://localhost:11434')|Out-Null;exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Ollama juz dziala.
    goto :start_app
)

echo [INFO] Uruchamiam Ollama...
start "Ollama" /min cmd /c ""%OLLAMA%" serve"
set OLLAMA_STARTED=1

for /l %%i in (1,1,6) do (
    timeout /t 2 /nobreak >nul
    powershell -NoProfile -Command "try{(New-Object Net.WebClient).DownloadString('http://localhost:11434')|Out-Null;exit 0}catch{exit 1}" >nul 2>&1
    if !errorlevel!==0 (
        echo [OK] Ollama gotowa.
        goto :start_app
    )
)
echo [WARN] Ollama nie odpowiada - uruchomiono bez AI.

REM ── 4. Aplikacja ─────────────────────────────────────────────────────────────

:start_app
echo.
echo [START] Uruchamiam ElectroVision...
echo.

C:\ev\Scripts\python.exe main.py
set APP_EXIT=%errorlevel%

if %APP_EXIT% neq 0 (
    echo.
    echo [BLAD] Aplikacja zamknela sie z bledem (kod %APP_EXIT%).
    pause
)

if %OLLAMA_STARTED%==1 (
    taskkill /f /im ollama.exe >nul 2>&1
)
