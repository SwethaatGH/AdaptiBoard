"""
icons.py - AAC pictograms from ARASAAC (https://arasaac.org), cached on disk.

ARASAAC symbols are made for AAC and are free to use under CC BY-NC-SA 4.0
(author: Sergio Palao, owner: Government of Aragon). Non-commercial use only; keep the
attribution shown in the app footer.

The first time a word is needed we ask the ARASAAC API for the best pictogram, download
the 300 px PNG and remember the answer in data/icons/index.json. After that it works
offline. Words with no good pictogram fall back to the tile's emoji in the browser.
"""
import asyncio
import json
import re
from pathlib import Path

import httpx

DIR = Path(__file__).resolve().parent / "data" / "icons"
INDEX = DIR / "index.json"
API = "https://api.arasaac.org/v1/pictograms/en"
IMG = "https://static.arasaac.org/pictograms/{id}/{id}_300.png"

# Hand-picked search terms where the plain word gives a poor pictogram.
ALIASES = {
    "i": "I", "me": "me", "my": "my", "tv": "television", "in pain": "pain",
    "call nurse": "nurse", "call family": "family", "move me": "move", "too loud": "noise",
    "i'm hungry": "hungry", "i'm cold": "cold", "i'm hot": "hot", "all done": "finish",
    "can i": "can", "can you": "can", "are you": "question", "do you": "question",
    "is it": "question", "how much": "how much", "what time is it": "what time is it",
    "what's that": "what", "how are you": "how are you", "i'm fine": "fine",
    "i don't know": "I don't know", "i love you": "I love you", "turn on": "turn on",
    "turn off": "turn off", "remote": "remote control", "okay": "OK",
}

# Pictograms checked by eye. An id pins the exact symbol; None = no good symbol (word only).
OVERRIDES: dict[str, int | None] = {
    "stop": 8289, "water": 2248, "who": 9853, "sit": 25081, "light": 8619, "watch": 2782,
    "park": 26296, "cold": 35583, "i'm cold": 35583, "what time is it": 13026,
    "garden": 2434, "can": 35949, "can i": 9843, "can you": 9843, "how are you": 6009,
    "you're welcome": 8128, "me too": 11591, "is": 36480,
    # Needs page
    "chest pain": 28781, "can't breathe": 11167, "seizure": 31432, "dizzy": 5442,
    "move me": 32270, "too loud": 7157,
    "excuse me": 9034, "maybe": 11696, "frustrated": 21820, "partner": 10344, "coming": 11708,
}

_index: dict[str, int | None] = {}
_lock = asyncio.Lock()
_client: httpx.AsyncClient | None = None


def _load():
    global _index
    if INDEX.exists():
        try:
            _index = json.loads(INDEX.read_text())
        except Exception:
            _index = {}


_load()


def _key(word: str) -> str:
    return re.sub(r"\s+", " ", word.lower().strip(" ?.!"))


async def _find_id(client, word):
    term = ALIASES.get(word, word)
    for kind in ("bestsearch", "search"):
        try:
            r = await client.get(f"{API}/{kind}/{term}")
            if r.status_code == 200:
                items = r.json()
                if items:
                    # prefer colour pictograms that aren't schematic diagrams
                    items.sort(key=lambda x: (x.get("schematic", False), not x.get("aac", True)))
                    return int(items[0]["_id"])
        except Exception:
            return -1  # network problem: don't remember a "no icon" answer
    return None


async def icon_path(word: str) -> Path | None:
    global _client
    key = _key(word)
    if not key:
        return None
    if key in OVERRIDES:
        _index[key] = OVERRIDES[key]
    if key in _index:
        pid = _index[key]
        if pid is None:
            return None
        p = DIR / f"{pid}.png"
        if p.exists():
            return p
    _client = _client or httpx.AsyncClient(timeout=6, follow_redirects=True)
    pid = _index.get(key)
    if pid is None:
        pid = await _find_id(_client, key)
        if pid == -1:
            return None
    async with _lock:
        _index[key] = pid
        DIR.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(json.dumps(_index))
    if pid is None:
        return None
    p = DIR / f"{pid}.png"
    if not p.exists():
        try:
            r = await _client.get(IMG.format(id=pid))
            r.raise_for_status()
            p.write_bytes(r.content)
        except Exception:
            return None
    return p


async def prefetch(words):
    """Download pictograms for the whole vocabulary in the background."""
    sem = asyncio.Semaphore(6)

    async def one(w):
        async with sem:
            await icon_path(w)

    await asyncio.gather(*(one(w) for w in words), return_exceptions=True)
