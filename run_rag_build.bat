@echo off
REM Buduje lokalny indeks RAG (wiedza AI)
REM Uruchom po dodaniu nowych plikow do training_data/

echo Budowanie bazy wiedzy AI (RAG)...
if exist C:\ev\Scripts\python.exe (
    C:\ev\Scripts\python.exe training_data\build_rag.py
) else (
    python training_data\build_rag.py
)
pause
