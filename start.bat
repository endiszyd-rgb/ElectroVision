@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title ElectroVision — uruchamianie...

echo.
echo  ╔══════════════════════════════════════╗
echo  ║       ElectroVision — Start          ║
echo  ╚══════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM ── 1. Znajdź Python ─────────────────────────────────────────────────────────

set PYTHON=
if exist "C:\ev\Scripts\python.exe" (
    set PYTHON=C:\ev\Scripts\python.exe
    echo [OK] Srodowisko wirtualne: C:\ev
    goto :check_deps
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [BLAD] Nie znaleziono Pythona.
    echo        Zainstaluj Python 3.11+ z https://python.org
    pause
    exit /b 1
)

set PYTHON=python
echo [INFO] Tworzenie srodowiska wirtualnego C:\ev ...
python -m venv C:\ev
if %errorlevel% neq 0 (
    echo [BLAD] Nie udalo sie utworzyc venv.
    echo        Sprawdz czy Python jest poprawnie zainstalowany.
    pause
    exit /b 1
)
set PYTHON=C:\ev\Scripts\python.exe
echo [OK] Srodowisko wirtualne utworzone.


REM ── 2. Zainstaluj zależności jeśli brak ──────────────────────────────────────

:check_deps
C:\ev\Scripts\python.exe -c "import PySide6" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Instalowanie zaleznosci (moze potrwac kilka minut)...
    C:\ev\Scripts\pip install --upgrade pip >nul 2>&1
    C:\ev\Scripts\pip install -r "%~dp0requirements.txt"
    if !errorlevel! neq 0 (
        echo.
        echo [BLAD] Instalacja zaleznosci nie powiodla sie.
        echo        Sprawdz bledy powyzej i sprobuj recznie:
        echo          C:\ev\Scripts\pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo [OK] Zaleznosci zainstalowane.
) else (
    echo [OK] Zaleznosci sa juz zainstalowane.
)


REM ── 3. Sprawdź i uruchom Ollama ──────────────────────────────────────────────

set OLLAMA=
set OLLAMA_STARTED=0

where ollama >nul 2>&1
if %errorlevel%==0 ( set OLLAMA=ollama & goto :try_start_ollama )

for %%P in (
    "%LOCALAPPDATA%\Ollama\ollama.exe"
    "%PROGRAMFILES%\Ollama\ollama.exe"
    "%PROGRAMFILES(X86)%\Ollama\ollama.exe"
    "%USERPROFILE%\AppData\Local\Ollama\ollama.exe"
    "C:\Ollama\ollama.exe"
) do (
    if exist %%P ( set OLLAMA=%%~P & goto :try_start_ollama )
)

echo [INFO] Ollama nie znaleziona — AI lokalny bedzie niedostepne.
echo        Pobierz: https://ollama.ai  |  Model: ollama pull llama3
echo.
goto :start_app


:try_start_ollama
powershell -NoProfile -Command "try{(New-Object Net.WebClient).DownloadString('http://localhost:11434')|Out-Null;exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Ollama juz dziala.
    goto :start_app
)

echo [INFO] Uruchamianie Ollama server...
start "Ollama Server" /min cmd /c ""%OLLAMA%" serve"
set OLLAMA_STARTED=1

for /l %%i in (1,1,6) do (
    timeout /t 2 /nobreak >nul
    powershell -NoProfile -Command "try{(New-Object Net.WebClient).DownloadString('http://localhost:11434')|Out-Null;exit 0}catch{exit 1}" >nul 2>&1
    if !errorlevel!==0 (
        echo [OK] Ollama gotowa.
        goto :start_app
    )
)
echo [WARN] Ollama nie odpowiada — aplikacja uruchomi sie bez AI.


REM ── 4. Uruchom ElectroVision ──────────────────────────────────────────────────

:start_app
echo.
echo [START] Uruchamiam ElectroVision...
echo.

"%PYTHON%" main.py
set APP_EXIT=%errorlevel%

if %APP_EXIT% neq 0 (
    echo.
    echo [BLAD] Aplikacja zamknela sie z bledem (kod %APP_EXIT%).
    pause
)

if %OLLAMA_STARTED%==1 (
    echo [INFO] Zatrzymuje Ollama server...
    taskkill /f /im ollama.exe >nul 2>&1
)
