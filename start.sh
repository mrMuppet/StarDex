#!/bin/sh
# StarDex starten. Beim ersten Mal (und nach Updates von requirements.txt) wird die Python-Umgebung eingerichtet.
cd "$(dirname "$0")" || exit 1
PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  command -v python3 >/dev/null || { echo "Python 3.10 oder neuer fehlt: https://www.python.org"; exit 1; }
  echo "StarDex wird eingerichtet ..."
  python3 -m venv .venv || exit 1
fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
  echo "Python-Pakete werden installiert ..."
  "$PY" -m pip install --disable-pip-version-check -q -r requirements.txt || exit 1
  cp requirements.txt .venv/requirements.installed
fi
command -v ffmpeg >/dev/null || echo "Hinweis: ffmpeg wurde nicht gefunden - ohne ffmpeg koennen keine Songs umgewandelt werden."
exec "$PY" manager/app.py "$@"
