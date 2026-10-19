"""PS4-Fernsteuerung für SingStar-Tests (ohne Handgriffe an der Konsole).

Zwei Protokolle:
  * Second Screen (PS-App, TCP 997, pyps4-2ndscreen): App per Title-ID starten,
    Menütasten, Ruhemodus.
  * Remote Play (pyremoteplay): Bild holen (Screenshot) und volle Controller-Tasten.

Status (läuft die Konsole, welche App?) kommt ohne Anmeldung per DDP (UDP 987).

Einmalige Einrichtung:
  ps4ctl account <Konto-ID>      PSN-Konto-ID des PS4-Benutzers (dezimal, 0x-hex oder base64)
  ps4ctl pair-app <PIN>          PS4: Einstellungen > Einstellungen für Verbindung mit mobiler App > Gerät hinzufügen
  ps4ctl pair-rp <PIN>           PS4: Einstellungen > Remote Play-Verbindungseinstellungen > Gerät hinzufügen

Benutzung:
  ps4ctl status
  ps4ctl start [CUSA00033]       startet SingStar (wartet, bis DDP die App meldet)
  ps4ctl close                   schließt die laufende App (Tastenfolge, siehe CONFIG close_keys)
  ps4ctl restart                 close + start
  ps4ctl shot [datei.png]        Bild über Remote Play
  ps4ctl keys PS OPTIONS CROSS [--shot datei.png] [--wait 1.0]
                                 Tasten über Remote Play (UP DOWN LEFT RIGHT CROSS CIRCLE SQUARE
                                 TRIANGLE OPTIONS SHARE PS L1 R1 L2 R2 L3 R3 TOUCHPAD)
  ps4ctl app-keys ps option enter
                                 Tasten über Second Screen (up down left right enter back option ps ps_hold)
  ps4ctl wake | standby
"""
import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "ps4ctl.json"
PROFILES = HERE / "rp_profiles.json"
SHOTS = HERE.parents[2] / "build" / "shots"

DEFAULTS = {
    "host": "",  # PS4-IP, steht in ps4ctl.json
    "title_id": "CUSA00033",
    "user": "singstar",
    "account_b64": "",
    # Tastenfolge zum Schließen der laufenden App (Remote Play; Second-Screen-Tasten waren im
    # Menü unzuverlässig): Home, Options-Menü der Kachel, „Anwendung schließen“, Bestätigung
    # (OK vorausgewählt). "{goldhen}" wird bei aktivem GoldHEN durch "DOWN" ersetzt – GoldHEN
    # setzt „GoldHEN Cheat Menu“ an die erste Stelle.
    "close_keys": ["PS", 2.5, "OPTIONS", 2.5, "{goldhen}", 1.0, "CROSS", 2.0, "CROSS", 1.0],
}

log = logging.getLogger("ps4ctl")


def load_cfg():
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def save_cfg(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- Konto-ID

def parse_account(text):
    """Konto-ID (dezimal, 0x-hex, 16 hex-Zeichen oder base64) -> int."""
    t = text.strip()
    if t.lower().startswith("0x"):
        return int(t, 16)
    if t.isdigit():
        return int(t)
    if len(t) == 16 and all(c in "0123456789abcdefABCDEF" for c in t):
        return int(t, 16)
    raw = base64.b64decode(t)
    if len(raw) != 8:
        raise ValueError("base64-Konto-ID muss 8 Bytes ergeben")
    return int.from_bytes(raw, "little")


def account_int(cfg):
    if not cfg["account_b64"]:
        sys.exit("Keine Konto-ID eingerichtet: ps4ctl account <ID>")
    return int.from_bytes(base64.b64decode(cfg["account_b64"]), "little")


def app_credential(cfg):
    """Second-Screen-Credential = SHA256 der dezimalen Konto-ID (wie die PS-App)."""
    return hashlib.sha256(str(account_int(cfg)).encode()).hexdigest()


# ---------------------------------------------------------------- DDP-Status

def ddp_status(host, timeout=2.0):
    """Antwort der PS4 auf SRCH als dict, None wenn keine Antwort."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.bind(("", 0))
        s.sendto(b"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:00020020\n", (host, 987))
        data, _ = s.recvfrom(2048)
    except OSError:
        return None
    finally:
        s.close()
    lines = data.decode("utf-8", "replace").splitlines()
    st = {"status_line": lines[0]}
    for ln in lines[1:]:
        if ":" in ln:
            k, v = ln.split(":", 1)
            st[k] = v.strip().strip("\x00")
    st["on"] = " 200 " in lines[0]
    return st


def running_title(cfg):
    st = ddp_status(cfg["host"])
    return st.get("running-app-titleid") if st and st["on"] else None


def goldhen_active(cfg):
    """GoldHEN geladen = sein FTP-Server (2121) antwortet."""
    try:
        socket.create_connection((cfg["host"], 2121), timeout=2).close()
        return True
    except OSError:
        return False


def wait_title(cfg, want, timeout):
    """Wartet, bis running-app-titleid == want (None = keine App)."""
    end = time.time() + timeout
    while time.time() < end:
        if running_title(cfg) == want:
            return True
        time.sleep(1)
    return False


# ---------------------------------------------------------------- Second Screen

def ps4_app(cfg):
    from pyps4_2ndscreen.ps4 import Ps4Legacy
    return Ps4Legacy(cfg["host"], app_credential(cfg), device_name="ps4ctl")


def app_keys(cfg, seq):
    """seq: Tastennamen und Wartezeiten (float) gemischt, eine Verbindung."""
    ps4 = ps4_app(cfg)
    ps4.auto_close = False
    try:
        for item in seq:
            if isinstance(item, (int, float)):
                time.sleep(item)
            else:
                ps4.remote_control(item)
                time.sleep(0.4)
    finally:
        ps4.close()


# ---------------------------------------------------------------- Remote Play

def rp_profiles():
    from pyremoteplay.profile import Profiles
    return Profiles.load(str(PROFILES))


async def rp_session(cfg, actions, shot_path=None, settle=2.5):
    """Remote-Play-Sitzung öffnen, Tasten senden, optional Bild speichern."""
    from pyremoteplay import RPDevice
    from pyremoteplay.receiver import QueueReceiver

    dev = RPDevice(cfg["host"])
    if not await dev.async_get_status():
        sys.exit("PS4 antwortet nicht")
    for attempt in range(8):
        rcv = QueueReceiver()
        sess = dev.create_session(cfg["user"], profiles=rp_profiles(), receiver=rcv,
                                  resolution="720p", fps="low")
        if sess is None:
            sys.exit("Remote Play nicht eingerichtet: ps4ctl pair-rp <PIN>")
        if await dev.connect():
            break
        # Die vorige Sitzung ist auf der PS4 noch nicht abgemeldet -> kurz warten
        if "Another Remote Play session" not in (sess.error or "") or attempt == 7:
            sys.exit(f"Remote-Play-Verbindung fehlgeschlagen: {sess.error}")
        dev.disconnect()
        await asyncio.sleep(3)
    rc = 1
    try:
        if not await dev.async_wait_for_session():
            print(f"Remote-Play-Sitzung nicht bereit: {sess.error}", flush=True)
            return
        dev.controller.start()
        await asyncio.sleep(1.0)
        for item in actions:
            if isinstance(item, (int, float)):
                await asyncio.sleep(item)
            else:
                await dev.controller.async_button(item.upper(), "tap", delay=0.15)
                await asyncio.sleep(0.5)
        if shot_path:
            await asyncio.sleep(settle)
            frame = None
            for _ in range(20):
                frame = rcv.get_latest_video_frame()
                if frame is not None:
                    break
                await asyncio.sleep(0.5)
            if frame is None:
                print("Kein Bild empfangen", flush=True)
                return
            shot_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_image().save(shot_path)
            print(f"Bild: {shot_path}", flush=True)
        rc = 0
    finally:
        # disconnect() hängt gelegentlich (auch die Ereignisschleife) -> im Hintergrund,
        # kurze Gnadenfrist, dann hart beenden; der Timer greift auch bei blockierter Schleife
        sys.stdout.flush()
        threading.Timer(2.5, os._exit, [rc]).start()
        threading.Thread(target=dev.disconnect, daemon=True).start()
        await asyncio.sleep(1.5)
        sys.stdout.flush()
        os._exit(rc)


def run_rp(cfg, actions, shot_path=None, settle=2.5, timeout=60):
    """rp_session mit Zeitlimit. pyremoteplay hinterlässt offene IOCP-Vorgänge,
    an denen asyncio beim Beenden hängen bleibt -> Prozess hart beenden."""
    rc = 0
    try:
        asyncio.run(asyncio.wait_for(rp_session(cfg, actions, shot_path, settle), timeout))
    except asyncio.TimeoutError:
        print(f"Remote Play: Zeitlimit {timeout} s überschritten", flush=True)
        rc = 1
    except SystemExit as e:
        if e.code not in (None, 0):
            print(e.code, flush=True)
            rc = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)


def shot_name(arg):
    if arg:
        return Path(arg).resolve()
    return SHOTS / time.strftime("ps4_%Y%m%d_%H%M%S.png")


def parse_seq(items, wait):
    seq = []
    for it in items:
        try:
            seq.append(float(it))
        except ValueError:
            seq.extend([it, wait] if wait else [it])
    return seq


# ---------------------------------------------------------------- Befehle

def cmd_status(cfg, a):
    st = ddp_status(cfg["host"])
    if st is None:
        print("keine Antwort (aus oder nicht im Netz)")
        return 1
    print(json.dumps(st, indent=2, ensure_ascii=False))
    return 0


def cmd_account(cfg, a):
    acc = parse_account(a.id)
    cfg["account_b64"] = base64.b64encode(acc.to_bytes(8, "little")).decode()
    save_cfg(cfg)
    print(f"Konto-ID {acc} (0x{acc:016x}) gespeichert")
    return 0


def cmd_pair_app(cfg, a):
    ps4 = ps4_app(cfg)
    ps4.login(a.pin)
    ps4.close()
    print("Second Screen gekoppelt")
    return 0


def cmd_pair_rp(cfg, a):
    from pyremoteplay import RPDevice
    from pyremoteplay.profile import UserProfile
    profiles = rp_profiles()
    if cfg["user"] not in profiles.usernames:
        profiles.update_user(UserProfile(cfg["user"], {"id": cfg["account_b64"] or
                                                       sys.exit("erst: ps4ctl account <ID>"),
                                                       "hosts": {}}))
    dev = RPDevice(cfg["host"])
    dev.get_status()
    if dev.register(cfg["user"], a.pin, profiles=profiles, save=False) is None:
        print("Remote-Play-Registrierung fehlgeschlagen")
        return 1
    profiles.save(str(PROFILES))
    print("Remote Play registriert")
    return 0


def cmd_start(cfg, a):
    title = a.title or cfg["title_id"]
    cur = running_title(cfg)
    if cur == title:
        print(f"{title} läuft bereits")
        return 0
    ps4 = ps4_app(cfg)
    ps4.start_title(title, running_id=cur)
    ok = wait_title(cfg, title, 60)
    print(f"{title} läuft" if ok else f"{title} nach 60 s nicht gemeldet (läuft: {running_title(cfg)})")
    return 0 if ok else 1


def cmd_close(cfg, a):
    cur = running_title(cfg)
    if not cur:
        print("keine App läuft")
        return 0
    # Erst die App in den Vordergrund holen (sonst trifft PS/Options z. B. den Browser),
    # dann PS -> Options -> „Anwendung schließen“ -> OK.
    gh = goldhen_active(cfg)
    seq = [("DOWN" if gh else 0) if k == "{goldhen}" else k for k in cfg["close_keys"]]
    ok = False
    for attempt in range(2):
        if attempt:
            # Zweiter Versuch: offene Menüs/Dialoge (z. B. GoldHEN Cheat Menu) verlassen
            run_rp_sub(["CIRCLE", 1.0, "CIRCLE", 1.0])
        ps4 = ps4_app(cfg)
        ps4.start_title(cur, running_id=cur)
        time.sleep(3)
        run_rp_sub(seq)
        ok = wait_title(cfg, None, 20)
        if ok:
            break
    print(f"{cur} geschlossen" if ok else f"{cur} läuft noch – Tastenfolge prüfen (ps4ctl shot)")
    return 0 if ok else 1


def run_rp_sub(seq):
    """Remote-Play-Tastenfolge in eigenem Prozess (rp_session beendet den Prozess hart)."""
    import subprocess
    keys = [str(k) for k in seq]
    subprocess.run([sys.executable, str(HERE / "ps4ctl.py"), "--timeout", "80", "keys", *keys],
                   check=False)


def cmd_restart(cfg, a):
    rc = cmd_close(cfg, a)
    if rc:
        return rc
    time.sleep(2)
    return cmd_start(cfg, a)


def cmd_shot(cfg, a):
    run_rp(cfg, [], shot_name(a.file), settle=a.settle, timeout=a.timeout - 5)


def cmd_keys(cfg, a):
    shot = shot_name(a.shot) if a.shot is not None else None
    run_rp(cfg, parse_seq(a.keys, a.wait), shot, settle=a.settle, timeout=a.timeout - 5)


def cmd_app_keys(cfg, a):
    app_keys(cfg, parse_seq(a.keys, a.wait))
    return 0


def cmd_wake(cfg, a):
    from pyps4_2ndscreen.ddp import wakeup
    wakeup(cfg["host"], app_credential(cfg))
    ok = False
    for _ in range(40):
        st = ddp_status(cfg["host"])
        if st and st["on"]:
            ok = True
            break
        time.sleep(1)
    print("PS4 an" if ok else "PS4 nicht aufgewacht")
    return 0 if ok else 1


def cmd_standby(cfg, a):
    ps4 = ps4_app(cfg)
    print("Ruhemodus" if ps4.standby() else "Ruhemodus fehlgeschlagen")
    return 0


def main():
    p = argparse.ArgumentParser(description="PS4-Fernsteuerung (SingStar-Tests)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(f=cmd_status)
    s = sub.add_parser("account"); s.add_argument("id"); s.set_defaults(f=cmd_account)
    s = sub.add_parser("pair-app"); s.add_argument("pin"); s.set_defaults(f=cmd_pair_app)
    s = sub.add_parser("pair-rp"); s.add_argument("pin"); s.set_defaults(f=cmd_pair_rp)
    s = sub.add_parser("start"); s.add_argument("title", nargs="?"); s.set_defaults(f=cmd_start)
    s = sub.add_parser("close"); s.set_defaults(f=cmd_close)
    s = sub.add_parser("restart"); s.add_argument("title", nargs="?"); s.set_defaults(f=cmd_restart)
    s = sub.add_parser("shot"); s.add_argument("file", nargs="?")
    s.add_argument("--settle", type=float, default=2.5); s.set_defaults(f=cmd_shot)
    for name, fn in (("keys", cmd_keys), ("app-keys", cmd_app_keys)):
        s = sub.add_parser(name); s.add_argument("keys", nargs="+")
        s.add_argument("--wait", type=float, default=0.0, help="Pause nach jeder Taste")
        if name == "keys":
            s.add_argument("--shot", nargs="?", const="", default=None)
            s.add_argument("--settle", type=float, default=1.5)
        s.set_defaults(f=fn)
    sub.add_parser("wake").set_defaults(f=cmd_wake)
    sub.add_parser("standby").set_defaults(f=cmd_standby)
    p.add_argument("--timeout", type=float, default=90, help="harte Obergrenze in s")
    a = p.parse_args()
    # Wachhund: pyps4/pyremoteplay können an toten Verbindungen hängen bleiben
    def _watchdog():
        print(f"Zeitlimit {a.timeout:.0f} s überschritten – abgebrochen", flush=True)
        os._exit(3)
    t = threading.Timer(a.timeout, _watchdog)
    t.daemon = True
    t.start()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.WARNING)
    if not a.verbose:
        # Tondekodierfehler, PS-Store-Abfrage (Cover) und asyncio-Aufräumen sind für uns Rauschen
        for name in ("pyremoteplay", "pyps4_2ndscreen", "asyncio"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
    sys.exit(a.f(load_cfg(), a))


if __name__ == "__main__":
    main()
