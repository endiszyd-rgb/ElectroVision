@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title ElectroVision — uruchamianie...

echo.
echo  ╔══════════════════════════════════════╗
echo  ║       ElectroVision — Start          ║
echo  ╚══════════════════════════════════════╝
echo.

REM ── 1. Sprawdź środowisko wirtualne ─────────────────────────────────────────

set PYTHON=
if exist "C:\ev\Scripts\python.exe" (
    set PYTHON=C:\ev\Scripts\python.exe
    echo [OK] Srodowisko wirtualne: C:\ev
    goto :check_ollama
)

REM Fallback: systemowy Python
where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
    echo [OK] Python systemowy (bez venv)
    goto :check_ollama
)

echo [BLAD] Nie znaleziono Pythona.
echo.
echo  Zainstaluj Python z https://python.org
echo  Lub utwórz venv: python -m venv C:\ev
echo              potem: C:\ev\Scripts\pip install -r requirements.txt
echo.
pause
exit /b 1


REM ── 2. Sprawdź i uruchom Ollama ──────────────────────────────────────────────

:check_ollama

set OLLAMA=
set OLLAMA_STARTED=0

REM Szukaj ollama.exe w PATH
where ollama >nul 2>&1
if %errorlevel%==0 (
    set OLLAMA=ollama
    goto :try_start_ollama
)

REM Typowe ścieżki instalacji Ollama na Windows
for %%P in (
    "%LOCALAPPDATA%\Ollama\ollama.exe"
    "%PROGRAMFILES%\Ollama\ollama.exe"
    "%PROGRAMFILES(X86)%\Ollama\ollama.exe"
    "%USERPROFILE%\AppData\Local\Ollama\ollama.exe"
    "C:\Ollama\ollama.exe"
) do (
    if exist %%P (
        set OLLAMA=%%~P
        goto :try_start_ollama
    )
)

echo [INFO] Ollama nie znaleziona — aplikacja uruchomi sie bez AI lokalnego.
echo        Pobierz Ollama: https://ollama.ai
echo        Zainstaluj model: ollama pull llama3
echo.
goto :start_app


:try_start_ollama
REM Sprawdź czy ollama serve już działa (port 11434)
powershell -NoProfile -Command "try { $r=(New-Object Net.WebClient).DownloadString('http://localhost:11434'); exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Ollama juz dziala na porcie 11434.
    goto :start_app
)

echo [INFO] Uruchamianie Ollama server...
start "Ollama Server" /min cmd /c ""%OLLAMA%" serve"
set OLLAMA_STARTED=1

REM Czekaj aż Ollama się podniesie (max 12 sekund)
echo [....] Czekam na Ollama
for /l %%i in (1,1,6) do (
    timeout /t 2 /nobreak >nul
    powershell -NoProfile -Command "try { (New-Object Net.WebClient).DownloadString('http://localhost:11434') | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
    if !errorlevel!==0 (
        echo [OK] Ollama gotowa.
        goto :start_app
    )
    echo [....] Czekam... %%i/6
)
echo [WARN] Ollama nie odpowiada — aplikacja uruchomi sie bez AI.


REM ── 3. Uruchom ElectroVision ──────────────────────────────────────────────────

:start_app
echo.
echo [START] Uruchamiam ElectroVision...
echo.

REM Zmień katalog roboczy na folder skryptu
cd /d "%~dp0"

"%PYTHON%" main.py
if %errorlevel% neq 0 (
    echo.
    echo [BLAD] Aplikacja zamknela sie z bledem (kod %errorlevel%).
    echo        Sprawdz logi powyzej.
    echo.
    pause
)

REM Jeśli Ollama była przez nas uruchomiona — zatrzymaj ją po wyjściu
if %OLLAMA_STARTED%==1 (
    echo.
    echo [INFO] Zatrzymuję Ollama server...
    taskkill /f /im ollama.exe >nul 2>&1
)
