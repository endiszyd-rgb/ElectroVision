@echo off
REM ElectroVision — uruchom aplikację
REM Używa środowiska wirtualnego C:\ev z wszystkimi wymaganymi pakietami

if exist C:\ev\Scripts\python.exe (
    C:\ev\Scripts\python.exe main.py %*
) else (
    echo Brak srodowiska wirtualnego C:\ev
    echo Uruchom: python -m venv C:\ev
    echo Nastepnie: C:\ev\Scripts\pip install -r requirements.txt
    pause
)
