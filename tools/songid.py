"""SingStar PS4 ties a DLC pack to its song: label[3:6] read as base 36 must equal the song id.

Official examples: 130U9X0000000000 -> "U9X" -> 39237 (Let It Go), 100SW40000000000 -> "SW4" -> 37444.
The game (eboot 0x7d3e70) derives the id from the label; packs whose id has no song in the db are
re-enumerated at every start, and download songs whose id matches no pack are purged from the song list.
"""

MAX_ID = 36 ** 3 - 1  # 46655
CUSTOM_BASE = 45000   # PS3 custom songs 600xx -> 45xxx (official ids in the PS3 library go up to 39263)
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def b36(n: int) -> str:
    if not 0 < n <= MAX_ID:
        raise ValueError(f"song id {n} does not fit into 3 base-36 digits (max {MAX_ID})")
    return DIGITS[n // 1296] + DIGITS[n // 36 % 36] + DIGITS[n % 36]


def sku_for(song_id: int, prefix: str = "130") -> str:
    """Prod_Sku suffix, e.g. 39237 -> '130U9X'."""
    return prefix + b36(song_id)


def label_for(song_id: int) -> str:
    """16-char entitlement label, e.g. 39237 -> '130U9X0000000000'."""
    return sku_for(song_id) + "0" * 10


def id_from_label(label: str) -> int:
    return int(label[3:6], 36)


def ps4_id(ps3_id: int) -> int:
    """In-game id for a PS3 library song: official ids stay, custom 600xx move below MAX_ID."""
    return CUSTOM_BASE + (ps3_id - 60000) if ps3_id >= 60000 else ps3_id
