"""PS4 NID helper: NID(name) = base64(reverse(sha1(name + suffix)[:8])), '/' -> '-'."""
import base64
import hashlib

SUFFIX = bytes.fromhex("518D64A635DED8C1E6B039B1C3E55230")


def nid(name: str) -> str:
    h = hashlib.sha1(name.encode() + SUFFIX).digest()[:8][::-1]
    return base64.b64encode(h).decode().rstrip("=").replace("/", "-")
