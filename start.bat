@echo off
title WealthFlow - FastAPI Server

cd /d "%~dp0"

echo.
echo ==========================================
echo          WealthFlow is starting...
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment was not found.
    echo.
    echo Make sure this file is inside your WealthFlow project folder.
    echo.
    pause
    exit /b 1
)

echo Starting FastAPI server with local HTTPS...
echo.
echo Open your browser at:
echo https://localhost:8443
echo.
echo The local self-signed certificate may trigger a browser warning.
echo Keep this window open while using WealthFlow.
echo Press Ctrl+C to stop the server.
echo.

".venv\Scripts\python.exe" dev_https.py

echo.
echo WealthFlow server stopped.
pause
