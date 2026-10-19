@echo off
rem StarDex starten. Beim ersten Mal (und nach Updates von requirements.txt) wird die Python-Umgebung eingerichtet.
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set VENV=.venv\Scripts\python.exe

if not exist "%VENV%" (
  where python >nul 2>nul || (
    echo Python fehlt. Bitte Python 3.10 oder neuer installieren: https://www.python.org
    echo Beim Installieren "Add python.exe to PATH" anhaken.
    pause & exit /b 1
  )
  echo StarDex wird eingerichtet ...
  python -m venv .venv || (pause & exit /b 1)
)
fc /b requirements.txt .venv\requirements.installed >nul 2>nul || (
  echo Python-Pakete werden installiert ...
  "%VENV%" -m pip install --disable-pip-version-check -q -r requirements.txt || (pause & exit /b 1)
  copy /y requirements.txt .venv\requirements.installed >nul
)

where ffmpeg >nul 2>nul || echo Hinweis: ffmpeg wurde nicht gefunden - ohne ffmpeg koennen keine Songs umgewandelt werden.
"%VENV%" manager\app.py %*
if errorlevel 1 pause
