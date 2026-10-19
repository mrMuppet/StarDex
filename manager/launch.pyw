"""Start-menu launcher for the Song-Manager (no console window).

Running already -> just open the page in the browser; otherwise start app.py in the background (it opens the
browser itself). The server keeps running after the browser is closed; it stops with Windows logoff/shutdown.
"""
import subprocess
import sys
import urllib.request
import webbrowser
from pathlib import Path

URL = "http://127.0.0.1:5077"
HERE = Path(__file__).parent

try:
    urllib.request.urlopen(URL + "/api/status", timeout=2)
    webbrowser.open(URL)
except OSError:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else sys.executable), str(HERE / "app.py")], cwd=HERE,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                     close_fds=True)
