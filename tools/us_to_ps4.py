"""Convert an UltraStar song folder (txt + mp3 + video + cover) into a SingStar PS4 DLC pack folder.

  python us_to_ps4.py SONG_DIR OUT_ROOT [--id N] [--copy-video|--reencode] [--track-name HD720VideoDL]
                      [--adrs HZ [--adrs-low HZ] [--adrs-width W]] [--test-tag TAG --id N]

Result: OUT_ROOT/Prod_Sku_130XXX/ (label derived from the song id, see songid.py) plus
OUT_ROOT/sce_sys/icon0.png. Build the installable package with:  build_dlc.py OUT_ROOT auto "TITLE" OUT_DIR

Mapping (verified against the SingStar Toolbox output of the same songs):
  SingStar Tempo = UltraStar BPM / 2 at Resolution Demisemiquaver -> 1 UltraStar beat = 1 tick
  MidiNote = 60 + pitch; ':' normal, '*' Bonus, 'F' FreeStyle, 'R' Rap, 'G' Rap+Bonus
  '-' line break -> new SENTENCE; #GAP (ms) -> leading rest (rounded to whole ticks)
  word-internal syllables get " -" (SingStar hyphenation), '~' -> "-" (held note)
Song ids: songs already in the PS3 library keep their PS4 id (songid.ps4_id), others get a stable id
from song_ids.json (new ids from 45300 upwards).
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, str(Path(__file__).parent))
import songid  # noqa: E402
from ps3_to_ps4 import add_duet_parts, convert_song, probe, write_pack_files  # noqa: E402

REGISTRY = Path(__file__).parent.parent / "song_ids.json"
RAP_SONGS = Path(__file__).parent.parent / "rap_songs.json"  # {"Artist - Title": true} = detect rap lines
import local_config  # noqa: E402
PS3_EXPORT = local_config.path("ps3_export_dir", None)  # None = no PS3 library (release copy)
FIRST_NEW_ID = 45300
PREVIEW_LEN = 30.0
AUTO_HIGH = 3125.0  # ADRS band top for --adrs auto (tested: Matilda, Valerie, Kaleo)
LANG = {"german": "DE", "deutsch": "DE", "english": "EN", "englisch": "EN", "french": "FR", "spanish": "ES",
        "italian": "IT", "dutch": "NL", "polish": "PL", "portuguese": "PT", "swedish": "SV", "norwegian": "NO",
        "danish": "DA", "finnish": "FI", "russian": "RU", "turkish": "TR", "korean": "KO", "japanese": "JA"}


# ---------------------------------------------------------------- UltraStar parsing

TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "´": "'", "`": "'", "“": '"', "”": '"',
                            "„": '"', "–": "-", "—": "-", "…": "...", " ": " "})


def read_txt(path: Path) -> str:
    """Decode (UTF-8, else cp1252) and map typographic quotes/dashes to ASCII the game font surely has."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return raw.decode(enc).translate(TYPOGRAPHY)
        except UnicodeDecodeError:
            pass


def parse(path: Path):
    head, lines, cur, duet = {}, [], [], False
    for row in read_txt(path).splitlines():
        if row.startswith("#"):
            k, _, v = row[1:].partition(":")
            head[k.strip().upper()] = v.strip()
        elif row[:2] in ("P1", "P2", "P3") or row.strip() in ("P1", "P2", "P3"):
            duet = True
        elif row[:1] in ":*FRG" and len(row) > 2:
            m = re.match(r"([:*FRG]) +(-?\d+) +(\d+) +(-?\d+) ?(.*)$", row)
            if m:
                kind, start, length, pitch, text = m.groups()
                cur.append({"kind": kind, "start": int(start), "len": int(length),
                            "pitch": int(pitch), "text": text})
        elif row.startswith("-"):
            if cur:
                lines.append(cur)
            cur = []
        elif row.startswith("E"):
            break
    if cur:
        lines.append(cur)
    if head.get("RELATIVE", "").lower() == "yes":
        sys.exit("#RELATIVE songs are not supported")
    return head, lines, duet


# ---------------------------------------------------------------- melody

def lyric(note, nxt) -> str:
    t = note["text"]
    word_end = t.endswith(" ") or nxt is None or nxt["text"].startswith(" ")
    t = t.strip()
    if t in ("~", ""):
        t = "-" if t == "~" else ""
    elif t.startswith("~"):  # held vowel ending in a consonant ("~r"): show the consonant only
        t = t.lstrip("~")
        if not any(c.isalnum() for c in t):  # "~," / "~!": still just a held note
            t = "-"
    elif not word_end and not t.endswith("-"):
        t += " -"
    return t


RAP_PITCH = 45  # Sony writes every rap note at this pitch (PS4 demo "What's My Name?", most PS3 rap)


def rap_point(word: str, dur_s: float) -> str:
    """Sony's rap checkpoint for a word-initial rap syllable, chosen by its first sound (statistics of
    8472 official rap notes: Fric s/f/z/v/sch, Short Fric t/k/c/q, Voice Begin p/b/d/g, else Voice Inside).
    Without these POINTs the game shows no timing feedback for rap (blue bar)."""
    w = re.sub(r"[^a-zäöüß]", "", word.lower())
    if not w:
        return ""
    if w.startswith(("sch", "sh", "ph")) or w[0] in "sfzvß" or (w[0] == "c" and w[1:2] in ("e", "i", "y")):
        kind, length, stop = "Fric", 0.035, dur_s
    elif w[0] in "tkcq":
        kind, length, stop = "Short Fric", 0.060, dur_s
    elif w[0] in "pbdg":
        kind, length, stop = "Voice Begin", 0.058, dur_s * 0.86
    else:
        return f'<POINT Type="Voice Inside" Start="0.000" Stop="{dur_s:.3f}" />'
    return f'<POINT Type="{kind}" Start="0.000" Stop="{stop:.3f}" Length="{length:.3f}" />'


def note_xml(midi: int, dur: int, text: str, attrs: str = "", children: str = "") -> str:
    a = f'<NOTE MidiNote="{midi}" Duration="{dur}" Lyric={quoteattr(text)}{attrs}'
    return f"{a}>{children}</NOTE>" if children else f"{a} />"


def build_melody(head, lines, artist, tempo, gap_ticks, medley, end_ticks=0):
    """Return melody xml. medley = (normal_begin_line, normal_end_line, micro_begin_line, micro_end_line).
    end_ticks: song length in ticks. Like the official melodies, a final rest runs to the end of the song:
    the game stops the performance where the melody ends, not where the video ends."""
    out = [f'<?xml version="1.0" encoding="UTF-8"?>',
           f'<MELODY Version="1" Tempo="{tempo:g}" FixedTempo="Yes" Resolution="Demisemiquaver" m2xVersion="0" '
           f'audioVersion="1" shouldHaveAdrs="No" xmlns="http://www.singstargame.com">',
           f'  <TRACK Name="Player1" Artist={quoteattr(artist)} />']
    cursor = -gap_ticks  # beat position (relative to GAP) reached so far
    for li, ln in enumerate(lines):
        tag = '<SENTENCE Singer="Solo 1" Part="Verse">' if li == 0 else "<SENTENCE>"
        out.append(f"  {tag}")
        if li == 0:
            out.append('    <LABEL Name="Bar Marker" Delay="0" />')
        if li and li % 4 == 0:
            out.append('    <MARKER_S Type="PTM" />')
        begin = []
        if medley[0] == li:
            begin.append('<MARKER_N Type="MedleyNormalBegin" Delay="10" />')
        if medley[2] == li:
            begin.append('<MARKER_N Type="MedleyMicroBegin" Delay="5" />')
        notes = []
        rap_line = any(n["kind"] in ("R", "G") for n in ln)  # like Sony: rests in rap lines are rap too
        for k, n in enumerate(ln):
            nxt = ln[k + 1] if k + 1 < len(ln) else None  # line end always ends a word
            start, length = n["start"], max(1, n["len"])
            if start < cursor:  # overlap with the previous note: shorten it
                if notes and notes[-1][1] - (cursor - start) >= 1:
                    notes[-1][1] -= cursor - start
                    cursor = start
                else:
                    start = cursor
            if start > cursor:
                notes.append([0, start - cursor, "", ' Rap="Yes"' if rap_line else "", ""])
            # Sony marks every rap note FreeStyle + Rap (without FreeStyle the game shows pitch bars)
            attrs = {":": "", "*": ' Bonus="Yes"', "F": ' FreeStyle="Yes"', "R": ' FreeStyle="Yes" Rap="Yes"',
                     "G": ' Bonus="Yes" FreeStyle="Yes" Rap="Yes"'}[n["kind"]]
            midi = min(127, max(1, 60 + n["pitch"]))
            point = ""
            if n["kind"] in ("R", "G"):
                midi = RAP_PITCH
                if k == 0 or n["text"].startswith(" ") or ln[k - 1]["text"].endswith(" "):
                    point = rap_point(n["text"], length * 60.0 / (tempo * 8))
            notes.append([midi, length, lyric(n, nxt), attrs, point])
            cursor = start + length
        end = []
        if medley[1] == li:
            end.append('<MARKER_N Type="MedleyNormalEnd" Delay="10" />')
        if medley[3] == li:
            end.append('<MARKER_N Type="MedleyMicroEnd" Delay="5" />')
        for i, (midi, dur, text, attrs, point) in enumerate(notes):
            kids = point + ("".join(begin) if i == 0 else "")
            if li == 0 and i == 0:  # official melodies always carry the tempo map; ADRS timing depends on it
                kids += f'<TEMPO Tempo="{tempo:g}" Resolution="Demisemiquaver" Offset="0" />'
            kids += "".join(end) if i == len(notes) - 1 else ""
            out.append("    " + note_xml(midi, dur, text, attrs, kids))
        out.append("  </SENTENCE>")
    rest = end_ticks - (cursor + gap_ticks)
    if rest > 0:
        out.insert(len(out) - 1, "    " + note_xml(0, rest, ""))
    out.append("</MELODY>")
    return "\n".join(out) + "\n"


def adrs_xml(width: float, low: float, high: float, time: float, azimuth: float = 0.0, soft: int = 0) -> str:
    return (f'<ADRS Id="0" Time="{time:.3f}" Azimuth="{azimuth:.7f}" Width="{width:.7f}" Transient="0" '
            f'LowShelf="{low:.2f}" HighShelf="{high:.2f}" Mode="0" Bypass="0" SoftSupression="{soft}" />')


def add_adrs(melody: str, low: float, high: float, width: float, soft: int = 0, join_gap: float = 3.0,
             lead: float = 0.3, tail: float = 0.5, shape=None, max_seg: float = 20.0) -> tuple[str, list]:
    """Vocal reduction (ADRS) from the melody timing: neutral set at 0 s, the vocal set from shortly before
    each sung passage (lines closer than join_gap s are one passage) to shortly after it, neutral in between.
    With shape(start, end) -> (azimuth, width) the setting is chosen per segment (passages split into pieces
    of about max_seg s at gaps between sung notes; width 0 = no reduction there).
    Like Sony, each ADRS hangs in the NOTE that contains its time (Time = offset in that note, seconds).
    Returns (melody, [(time, azimuth, width), ...])."""
    head = re.search(r"<MELODY[^>]*>", melody).group()
    tick = 60.0 / (float(re.search(r'Tempo="([\d.]+)"', head).group(1)) * 8)
    notes, pos = [], 0
    for m in re.finditer(r'<NOTE MidiNote="(\d+)" Duration="(\d+)"[^>]*?(/>|>.*?</NOTE>)', melody, re.S):
        dur = int(m.group(2))
        notes.append((m, pos * tick, (pos + dur) * tick, int(m.group(1)) > 0))
        pos += dur
    passages = []  # each: list of (start, end) of its sung notes
    for _, a, b, sung in notes:
        if not sung:
            continue
        if passages and a - passages[-1][-1][1] < join_gap:
            passages[-1].append((a, b))
        else:
            passages.append([(a, b)])
    segs = []  # (start, end, event time)
    for p in passages:
        if shape is None:
            segs.append((p[0][0], p[-1][1], max(0.0, p[0][0] - lead)))
            continue
        start, t0 = p[0][0], max(0.0, p[0][0] - lead)
        for (a1, b1), (a2, _b2) in zip(p, p[1:]):
            if b1 - start >= max_seg and a2 - b1 >= 0.2 and p[-1][1] - a2 >= max_seg / 2:
                segs.append((start, b1, t0))
                start, t0 = a2, (b1 + a2) / 2
        segs.append((start, p[-1][1], t0))
    events = [(0.0, 0.0, 0.0)]
    for i, (a, b, t) in enumerate(segs):
        az, w = shape(a, b) if shape else (0.0, width)
        events.append((t, az, w))
        if i + 1 == len(segs) or segs[i + 1][2] - b > tail + 0.01:  # passage ends
            events.append((b + tail, az, 0.0))
    # same time: the later event wins (a song that starts singing at once must not lose its first "on");
    # the final reset after the song is moot; repeated identical settings are dropped
    events = [e for i, e in enumerate(events)
              if (i + 1 == len(events) or events[i + 1][0] > e[0]) and e[0] < notes[-1][2]]
    events = [e for i, e in enumerate(events) if i == 0 or e[1:] != events[i - 1][1:]]
    kids = {}
    for t, az, w in events:
        k = next((i for i, n in enumerate(notes) if n[1] <= t < n[2]), len(notes) - 1)
        kids.setdefault(k, []).append(adrs_xml(w, low, high, max(0.0, t - notes[k][1]), az, soft))
    out, last = [], 0
    for k, (m, *_rest) in enumerate(notes):
        if k not in kids:
            continue
        s = m.group(0)
        ins = "".join(kids[k])
        s = s[:-2].rstrip() + f">{ins}</NOTE>" if s.endswith("/>") else s.replace(">", f">{ins}", 1)
        out += [melody[last:m.start()], s]
        last = m.end()
    out.append(melody[last:])
    return "".join(out).replace('shouldHaveAdrs="No"', 'shouldHaveAdrs="Yes"'), events


# ---------------------------------------------------------------- helpers

def key_text(s: str) -> str:
    # like Sony's keys: "Köller Grüß" -> "KOELLER GRUESS" (umlauts spelled out, other accents dropped)
    s = s.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", "", s)).strip().upper()


def find_file(folder: Path, name: str | None, exts) -> Path | None:
    if name and (folder / name).exists():
        return folder / name
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() in exts:
            return p
    return None


def ps3_id_for(artist: str, title: str) -> int | None:
    if PS3_EXPORT is None:
        return None
    songs = PS3_EXPORT / "songs_4_0.xml"
    if not songs.exists():
        return None
    xml = songs.read_text("utf-8")
    want = (key_text(artist), key_text(title))
    for m in re.finditer(r'<SONG ID="(\d+)".*?</SONG>', xml, re.S):
        t = re.search(r"<TITLE>(.*?)</TITLE>", m.group(0))
        a = re.search(r"<PERFORMANCE_NAME>(.*?)</PERFORMANCE_NAME>", m.group(0))
        if t and a and (key_text(a.group(1).replace("&amp;", "&")), key_text(t.group(1).replace("&amp;", "&"))) == want:
            return int(m.group(1))
    return None


def ps3_chorus_time(ps3_id: int | None) -> float | None:
    """Chorus start the SingStar Toolbox stored for this song in the PS3 library (seconds)."""
    if not ps3_id or PS3_EXPORT is None:
        return None
    songs = PS3_EXPORT / "songs_4_0.xml"
    if not songs.exists():
        return None
    m = re.search(r'<SONG ID="%d".*?</SONG>' % ps3_id, songs.read_text("utf-8"), re.S)
    c = m and re.search(r'<CHORUS TIME="([\d.]+)"', m.group(0))
    return float(c.group(1)) if c else None


def song_id_for(artist: str, title: str, forced: int | None) -> int:
    reg = json.loads(REGISTRY.read_text("utf-8")) if REGISTRY.exists() else {}
    key = f"{artist} - {title}"
    if forced:
        sid = forced
    elif key in reg:
        sid = reg[key]
    else:
        ps3 = ps3_id_for(artist, title)
        sid = songid.ps4_id(ps3) if ps3 else max([FIRST_NEW_ID - 1, *[v for v in reg.values() if v >= FIRST_NEW_ID]]) + 1
    clash = [k for k, v in reg.items() if v == sid and k != key]
    if clash:
        sys.exit(f"song id {sid} already used by {clash[0]}")
    if reg.get(key) != sid:  # write only on change (batch_us.py runs several conversions in parallel)
        reg[key] = sid
        REGISTRY.write_text(json.dumps(dict(sorted(reg.items())), ensure_ascii=False, indent=1), "utf-8")
    return sid


def ffprobe_json(path: Path) -> dict:
    return json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                                      str(path)], capture_output=True, check=True).stdout.decode("utf-8", "replace"))


def loudness_filter(audio: Path, target: float, peak: float = -1.5) -> tuple[str, float]:
    """Two-pass EBU R128 normalisation: measure, then a linear gain (loudnorm falls back to gentle limiting only
    if the gain would push true peaks above `peak`). Returns (filter, measured integrated loudness)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio), "-vn",
                        "-af", f"loudnorm=I={target}:TP={peak}:LRA=20:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    f = (f"loudnorm=I={target}:TP={peak}:LRA=20:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
         f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
         "linear=true,aresample=48000")
    return f, float(m["input_i"])


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def find_chorus(lines) -> int | None:
    """Index of the line where the chorus first starts: the first occurrence of the most repeated run of
    consecutive lines (normalised lyrics). None if nothing repeats."""
    txt = [re.sub(r"[^a-z0-9äöüß]", "", "".join(n["text"] for n in ln).lower()) for ln in lines]
    best, best_score = None, 0
    for i in range(len(txt)):
        for j in range(i + 1, len(txt)):
            k = 0
            while j + k < len(txt) and i + k < j and txt[i + k] and txt[i + k] == txt[j + k]:
                k += 1
            if k >= 1:
                reps = sum(1 for p in range(len(txt) - k + 1) if txt[p:p + k] == txt[i:i + k])
                score = k * reps
                if score > best_score or (score == best_score and best is not None and i < best):
                    best, best_score = i, score
    return best


def detect_crop(video: Path, around: float) -> str:
    """'crop=w:h:x:y,' for black borders baked into the video (sampled over 20 s), '' if there are none."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{max(0.0, around):.1f}", "-i", str(video), "-t", "20",
                        "-vf", "fps=2,cropdetect=24:2:0", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    boxes = [tuple(map(int, m)) for m in re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)]
    if not boxes:
        return ""
    w, h = max(b[0] for b in boxes), max(b[1] for b in boxes)  # largest content box seen
    x, y = min(b[2] for b in boxes), min(b[3] for b in boxes)
    info = next(s for s in ffprobe_json(video)["streams"] if s["codec_type"] == "video")
    if w >= int(info["width"]) - 16 and h >= int(info["height"]) - 16:
        return ""
    return f"crop={w}:{h}:{x}:{y},"


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song_dir", type=Path)
    ap.add_argument("out_root", type=Path)
    ap.add_argument("--id", type=int)
    ap.add_argument("--reencode", action="store_true", help="always re-encode the video (H.264 High, 25 fps)")
    ap.add_argument("--max-height", type=int, default=1080)
    ap.add_argument("--track-name", default="HD720VideoDL")
    ap.add_argument("--performance-type", default="MALE_SOLO")
    ap.add_argument("--no-crop-preview", action="store_true", help="keep black borders/aspect in the preview")
    ap.add_argument("--loudness", type=float, default=-12.0, help="target integrated loudness in LUFS")
    ap.add_argument("--no-normalize", action="store_true", help="keep the original audio level")
    ap.add_argument("--adrs", default="0", metavar="HZ|auto",
                    help="vocal reduction (ADRS): upper band edge in Hz with one fixed window, or 'auto' = "
                         "window per segment from the Demucs stems (see adrs_auto.py); 0 = none")
    ap.add_argument("--adrs-low", type=float, default=312.5, metavar="HZ")
    ap.add_argument("--adrs-width", type=float, default=0.25)
    ap.add_argument("--adrs-soft", type=int, choices=(0, 1), default=0,
                    help="SoftSupression flag (1 = only gentle reduction, barely audible on the PS4)")
    ap.add_argument("--rap", choices=("auto", "off"), default="auto",
                    help="auto: in songs listed in rap_songs.json, mark unmarked rap lines (one pitch, dense "
                         "syllables, see rap_detect.py) as Rap")
    ap.add_argument("--test-tag", help="test variant: appended to the title, needs --id, song_ids.json untouched")
    a = ap.parse_args()
    # Song-Manager setting "Gesangstrennung": full = Demucs for ADRS (default), nodemucs/off = no vocal separation,
    # UltraStar songs have no separate vocal track -> no ADRS then
    if a.adrs == "auto" and os.environ.get("SINGSTAR_ADRS", "full") in ("nodemucs", "off"):
        a.adrs = "0"
        print("  ADRS: aus (Gesangstrennung abgeschaltet)")

    txt = next(p for p in a.song_dir.glob("*.txt"))
    head, lines, duet = parse(txt)
    if duet:
        sys.exit("duet (P1/P2) songs are not supported yet")
    artist, title = head["ARTIST"], head["TITLE"]
    if a.rap == "auto":
        from rap_detect import rap_lines
        overrides = json.loads(RAP_SONGS.read_text("utf-8")) if RAP_SONGS.exists() else {}
        rap = rap_lines(lines, 60.0 / (float(head["BPM"].replace(",", ".")) * 4)) if overrides.get(f"{artist} - {title}") else set()
        for i in rap:
            for n in lines[i]:
                n["kind"] = {":": "R", "*": "G"}.get(n["kind"], n["kind"])
        if rap:
            print(f"  rap: {len(rap)} of {len(lines)} lines marked as rap")
    if a.test_tag and not a.id:
        sys.exit("--test-tag needs --id")
    bpm = float(head["BPM"].replace(",", "."))
    gap_ms = float(head.get("GAP", "0").replace(",", "."))
    tempo = bpm / 2
    tick = 60.0 / (bpm * 4)
    gap_ticks = round(gap_ms / 1000 / tick)
    sid = a.id if a.test_tag else song_id_for(artist, title, a.id)
    if a.test_tag:
        title = f"{title} [{a.test_tag}]"
    sku = songid.sku_for(sid)
    pack = f"Prod_Sku_{sku}"
    dst = a.out_root / pack
    if a.out_root.exists():
        shutil.rmtree(a.out_root)
    (dst / str(sid)).mkdir(parents=True)
    (dst / "textures").mkdir()
    print(f"{artist} - {title}: id {sid}, label {songid.label_for(sid)}, tempo {tempo:g}, gap {gap_ticks} ticks "
          f"(error {gap_ticks * tick * 1000 - gap_ms:+.0f} ms)")

    # ---- media
    audio = find_file(a.song_dir, head.get("MP3") or head.get("AUDIO"), (".mp3", ".ogg", ".m4a", ".wav", ".flac"))
    video = find_file(a.song_dir, head.get("VIDEO"), (".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v"))
    cover = find_file(a.song_dir, head.get("COVER"), (".jpg", ".jpeg", ".png"))
    alen = float(ffprobe_json(audio)["format"]["duration"])
    vgap = float(head.get("VIDEOGAP", "0").replace(",", "."))
    out_video = dst / str(sid) / "video.mp4"
    vinfo = next(s for s in ffprobe_json(video)["streams"] if s["codec_type"] == "video") if video else None
    copy_ok = (vinfo and not a.reencode and vgap == 0 and vinfo["codec_name"] == "h264"
               and vinfo.get("pix_fmt") == "yuv420p" and int(vinfo["height"]) <= a.max_height
               and vinfo.get("profile") in ("Main", "High", "Constrained Baseline"))
    aopts = ["-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2"]
    if not a.no_normalize:
        afilter, measured = loudness_filter(audio, a.loudness)
        aopts = ["-af", afilter, *aopts]
        print(f"  audio: {measured:.1f} LUFS -> {a.loudness:g} LUFS ({a.loudness - measured:+.1f} dB)")
    if video is None:  # no video: cover as still image
        ff("-loop", "1", "-framerate", "25", "-i", str(cover), "-i", str(audio), "-map", "0:v", "-map", "1:a",
           "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
           "-c:v", "libx264", "-profile:v", "high", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "25",
           *aopts, "-t", f"{alen:.3f}", "-movflags", "+faststart", str(out_video))
    elif copy_ok:
        ff("-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", *aopts,
           "-t", f"{alen:.3f}", "-movflags", "+faststart", str(out_video))
    else:
        vin = (["-ss", f"{vgap:.3f}"] if vgap > 0 else ["-itsoffset", f"{-vgap:.3f}"] if vgap < 0 else []) + ["-i", str(video)]
        h = min(a.max_height, int(vinfo["height"]))
        ff(*vin, "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
           "-vf", f"scale=-2:{h}", "-r", "25", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-crf", "20", "-preset", "medium", *aopts, "-t", f"{alen:.3f}", "-movflags", "+faststart", str(out_video))
    print(f"  video: {'copied' if copy_ok else 'encoded'} from {video.name if video else cover.name}")

    # ---- preview / medley positions (seconds -> line indices)
    starts = [(ln[0]["start"] + gap_ticks) * tick for ln in lines]
    ends = [(ln[-1]["start"] + ln[-1]["len"] + gap_ticks) * tick for ln in lines]
    chorus = find_chorus(lines)
    ps3_chorus = ps3_chorus_time(ps3_id_for(artist, head["TITLE"]))
    if "MEDLEYSTARTBEAT" in head:
        p0, how = (int(head["MEDLEYSTARTBEAT"]) + gap_ticks) * tick, "#MEDLEYSTARTBEAT"
    elif ps3_chorus is not None:
        p0, how = ps3_chorus, "chorus from the PS3 library (Toolbox)"
    elif chorus is not None:
        p0, how = starts[chorus], "first chorus"
    else:
        p0, how = alen / 3, "1/3 of the song"
    b = min(range(len(lines)), key=lambda i: abs(starts[i] - p0))
    print(f"  preview/medley at {starts[b]:.1f} s ({how})")
    ne = max((i for i in range(b, len(lines)) if ends[i] - starts[b] <= PREVIEW_LEN), default=b)
    me = max((i for i in range(b, len(lines)) if ends[i] - starts[b] <= 12), default=b)
    preview_start = max(0.0, starts[b] - 0.5)
    # The main video keeps its original format (the game pillarboxes non-16:9 itself). The preview drops black
    # borders baked into the video but keeps the content's own aspect (max 368x208), so it fills the square cover
    # tile while the game letterboxes it in 16:9 views. --no-crop-preview keeps a plain 368x208.
    # Sizes must be multiples of 16: the PS4 preview player ignores H.264 frame cropping and shows the encoder's
    # macroblock padding as a green bar (e.g. 368x154 -> coded 368x160; 32 songs, 28.09.).
    if not a.no_crop_preview:
        vf = (f"{detect_crop(out_video, preview_start)}scale=trunc(iw*sar/2)*2:ih,setsar=1,"  # anamorphic sources
              "scale=368:208:force_original_aspect_ratio=decrease:force_divisible_by=16")
    else:
        vf = "scale=368:208:force_original_aspect_ratio=decrease,pad=368:208:(ow-iw)/2:(oh-ih)/2"
    ff("-ss", f"{preview_start:.3f}", "-i", str(out_video), "-t", f"{PREVIEW_LEN:.0f}",
       "-vf", f"{vf},setsar=1",
       "-c:v", "libx264", "-profile:v", "high", "-level", "3.1", "-pix_fmt", "yuv420p", "-crf", "22",
       "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(dst / str(sid) / "preview.mp4"))
    shutil.copy2(dst / str(sid) / "preview.mp4", dst / str(sid) / "audiopreview.mp4")

    # ---- melody
    melody = build_melody(head, lines, artist, tempo, gap_ticks, (b, ne, b, me), math.ceil(alen / tick) + 1)
    melody = add_duet_parts(melody)
    if a.adrs == "auto":
        import adrs_auto
        sd = adrs_auto.stem_dir(audio)
        if not adrs_auto.suitable(a.song_dir.name):
            print("  ADRS: song not rated suitable (adrs_us_scan.json), no vocal reduction")
        elif sd is None:
            print("  ADRS: no stems found, song gets no vocal reduction")
        else:
            shaper = adrs_auto.StemShaper(sd, a.adrs_low, AUTO_HIGH)
            melody, ev = add_adrs(melody, a.adrs_low, AUTO_HIGH, 0, a.adrs_soft, shape=shaper)
            on = [s for s in shaper.log if not s["off"]]
            print(f"  ADRS auto: {len(on)}/{len(shaper.log)} segments reduced, {len(ev)} entries")
            for s in shaper.log:
                print(f"    {s['start']:6.1f}-{s['end']:6.1f}  vocal centre {s['azimuth']:+.3f} spread {s['width']:.3f}  "
                      f"music {s['music']:.0%}  vocal/music {s['level_db']:+.1f} dB  {s['off'] or 'on'}")
    elif float(a.adrs):
        melody, ev = add_adrs(melody, a.adrs_low, float(a.adrs), a.adrs_width, a.adrs_soft)
        print(f"  ADRS: {len(ev)} entries, band {a.adrs_low:g}-{a.adrs} Hz, width {a.adrs_width:g}, soft {a.adrs_soft}")
    (dst / str(sid) / "melody_1.xml").write_text(melody, "utf-8", newline="\n")

    # ---- cover
    tex = f"page_{sid}"
    ff("-i", str(cover), "-vf", "scale=256:256:force_original_aspect_ratio=increase,crop=256:256",
       "-q:v", "2", str(dst / "textures" / f"{tex}.jpg"))
    (a.out_root / "sce_sys").mkdir(parents=True, exist_ok=True)
    ff("-i", str(cover), "-vf", "scale=512:512:force_original_aspect_ratio=increase,crop=512:512",
       "-pix_fmt", "rgb24", str(a.out_root / "sce_sys" / "icon0.png"))

    # ---- songs / acts / covers / config
    lang = LANG.get(head.get("LANGUAGE", "").split(",")[0].strip().lower(), "EN")
    genre = head.get("GENRE", "Pop")
    year = re.sub(r"\D", "", head.get("YEAR", ""))[:4] or "2000"
    # rap songs: Sony lists the gameplay and switches rap scoring on per player; without this block the game
    # shows no timing feedback for rap notes (Holland test 28.09.)
    has_rap = any(n["kind"] in ("R", "G") for ln in lines for n in ln)
    gameplay = "      <GAMEPLAY>Singing</GAMEPLAY>\n" + ("      <GAMEPLAY>Rap</GAMEPLAY>\n" if has_rap else "")
    use = '<USE VERSION="Short">Yes</USE>\n        <USE VERSION="Normal">Yes</USE>'
    rap_block = (f'    <RAP>\n      <PLAYER ID="1">\n        {use}\n      </PLAYER>\n'
                 f'      <PLAYER ID="2">\n        {use}\n      </PLAYER>\n    </RAP>\n') if has_rap else ""
    song = (f'<SONG ID="{sid}" PERFORMANCE_TYPE="{a.performance_type}">\n'
            f"    <TITLE>{escape(title)}</TITLE>\n    <TITLE_KEY>{key_text(title)}</TITLE_KEY>\n"
            f"    <ALBUM />\n    <SHORT_VER>false</SHORT_VER>\n"
            f'    <SOLO PLAYER1={quoteattr(artist)} SHORT_VER="0" />\n'
            f'    <TEMPO BPM="{tempo:g}" RESOLUTION="Demisemiquaver" />\n'
            f'    <CHORUS TIME="{starts[b]:.3f}" />\n'
            f"    <INFO>\n      <GENRE>{escape(genre)}</GENRE>\n{gameplay}      <RELEASE_DATE>{year}-01-01</RELEASE_DATE>\n"
            f"      <VOXLANGUAGE>{lang}</VOXLANGUAGE>\n    </INFO>\n{rap_block}"
            f"    <MEDLEYS>\n      <TYPE Start=\"{starts[b]:.3f}\" End=\"{ends[ne]:.3f}\">Normal</TYPE>\n"
            f"      <TYPE Start=\"{starts[b]:.3f}\" End=\"{ends[me]:.3f}\">Micro</TYPE>\n    </MEDLEYS>\n"
            f'    <PERFORMED_BY ID="{sid}">\n      <ACT ID="{sid}" />\n    </PERFORMED_BY>\n'
            f"    <PERFORMANCE_NAME>{escape(artist)}</PERFORMANCE_NAME>\n"
            f"    <PERFORMANCE_NAME_KEY>{key_text(artist)}</PERFORMANCE_NAME_KEY>\n  </SONG>")
    v = probe(out_video)
    song = convert_song(song, v, preview_start).replace('NAME="HD720VideoDL"', f'NAME="{a.track_name}"')
    act = f'<ACT ID="{sid}">\n    <NAME>{escape(artist)}</NAME>\n    <NAME_KEY>{key_text(artist)}</NAME_KEY>\n  </ACT>'
    cov = f'<TPAGE_BIT NAME="cover_{sid}" TEXTURE="{tex}" U="0" V="0" WIDTH="256" HEIGHT="256" />'
    cache = [f"{sid}/audiopreview.mp4", f"{sid}/melody_1.xml", f"textures/{tex}.jpg"]
    write_pack_files(dst, pack, [song], [act], [cov], cache, [(sid, melody.encode("utf-8"))],
                     f"{artist} - {title}", sid)
    print(f"  video {v['w']}x{v['h']} @ {v['fps']:g} fps, {v['len']:.1f} s; preview from {preview_start:.1f} s")
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
