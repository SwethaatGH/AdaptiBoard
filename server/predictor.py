"""
predictor.py - offline next-tile prediction + context extraction.

Always available (no internet, no API key). The LLM layer (llm.py) sits on top of
this: when an LLM answers in time its tiles go first and these fill the rest.

Inputs:
  message  - tiles chosen so far, e.g. ["I", "want"]
  context  - what was heard around the user (see extract_context)
  usage    - personal learning: what this user picked after each word before
"""
import json
import re
import threading
import time
from pathlib import Path

from vocab import CATEGORY_WORDS, EXTRA_POS, STOPWORDS, WORDS

SLOTS = 16  # 4 x 4 board (rows pages: Chat, Needs, More words, categories)

START = ["I", "you", "want", "yes", "no", "help", "what", "more",
         "please", "thank you", "hello", "stop", "it", "we", "go", "feel"]

_WANT = ["to", "water", "more", "help", "it", "that", "food", "you", "go", "eat",
         "drink", "play", "music", "TV", "bathroom", "the"]
_FEEL = ["happy", "sad", "tired", "hungry", "thirsty", "sick", "in pain", "okay",
         "good", "bad", "hot", "cold", "scared", "bored", "excited", "not"]
_CONSUME = ["water", "food", "juice", "pizza", "apple", "breakfast", "lunch", "dinner",
            "snack", "more", "it", "that", "the", "some", "please", "now"]
_NEG = ["want", "like", "know", "feel", "need", "go", "eat", "have", "think",
        "understand", "care", "drink", "sleep", "play", "talk", "worry"]
_WH = ["is", "are", "do", "you", "time", "that", "we", "it", "can", "did",
       "going", "about", "the", "I", "there", "happened"]

NEXT = {
    "i": ["want", "need", "like", "feel", "am", "don't", "can", "love", "have", "think",
          "go", "see", "know", "eat", "drink", "will"],
    "you": ["are", "want", "can", "like", "need", "look", "help", "know", "have", "go",
            "feel", "see", "do", "eat", "love", "please"],
    "we": ["can", "go", "want", "need", "are", "have", "will", "should", "eat", "play",
           "watch", "love", "like", "see", "talk", "wait"],
    "want": _WANT, "need": _WANT, "like": _WANT, "love": ["you", "it", "that", "to", *_WANT],
    "to": ["go", "eat", "drink", "play", "sleep", "see", "watch", "talk", "rest", "read",
           "listen", "home", "bathroom", "bed", "outside", "the"],
    "go": ["to", "home", "outside", "bathroom", "now", "later", "bed", "park", "please",
           "with", "out", "back", "school", "store", "there", "too"],
    "feel": _FEEL, "am": _FEEL, "is": [*_FEEL[:8], "it", "that", "here", "there", "good",
                                       "ready", "done", "time"],
    "are": ["you", "we", "they", "okay", "ready", "happy", "tired", "hungry", "here",
            "going", "good", "done", "sure", "coming", "there", "sad"],
    "don't": _NEG, "not": ["now", "yet", "really", "good", "okay", "hungry", "tired",
                           "sure", "that", "this", "today", "again", *_NEG[:4]],
    "eat": _CONSUME, "drink": ["water", "juice", "milk", "coffee", "tea", "soda", "more",
                               "it", "that", "please", "now", "some", "the", "later",
                               "with", "too"],
    "have": _CONSUME, "get": ["up", "out", "water", "food", "help", "it", "that", "the",
                              "more", "me", "dressed", "ready", "better", "home",
                              "please", "some"],
    "can": ["I", "you", "we", "go", "have", "help", "eat", "drink", "play", "watch", "see",
            "talk", "come", "get", "sleep", "please"],
    "help": ["me", "please", "you", "now", "with", "him", "her", "us", "I", "stop",
             "thank you", "bathroom", "move", "eat", "get", "up"],
    "please": ["help", "I", "you", "stop", "come", "more", "water", "thank you", "wait",
               "go", "call", "give", "turn on", "turn off", "now", "again"],
    "the": ["bathroom", "TV", "door", "light", "window", "phone", "music", "doctor",
            "nurse", "car", "food", "water", "remote", "book", "park", "game"],
    "turn on": ["the", "light", "TV", "music", "it", "please", "fan", "radio", "now"],
    "turn off": ["the", "light", "TV", "music", "it", "please", "fan", "radio", "now"],
    "call": ["mom", "dad", "family", "nurse", "doctor", "friend", "me", "please", "now",
             "my", "them", "her", "him", "later", "back", "you"],
    "watch": ["TV", "a movie", "the game", "it", "that", "with you", "now", "later",
              "news", "music", "please", "together", "more", "again", "this", "show"],
    "play": ["a game", "music", "with you", "outside", "ball", "cards", "now", "later",
             "it", "again", "please", "more", "together", "with", "the", "game"],
}
for _w in ("what", "where", "when", "who", "why", "how", "which"):
    NEXT[_w] = _WH
for _w in ("he", "she", "they"):
    NEXT[_w] = ["is", "wants", "likes", "needs", "can", "has", "said", "went", "will",
                "feels", "knows", "loves", "looks", "doesn't", "are", "was"]

POS_FALLBACK = {
    "verb": ["it", "that", "the", "to", "more", "please", "now", "you", "me", "with",
             "a", "again", "this", "them", "later", "together"],
    "noun": ["please", "now", "and", "with", "too", "later", "is", "more", "for", "I",
             "you", "thank you", "again", "the", "not", "stop"],
    "place": ["please", "now", "later", "with", "and", "today", "I", "you", "too",
              "thank you", "is", "go", "now please", "again", "not", "stop"],
    "describe": ["and", "too", "please", "now", "I", "you", "not", "very", "today",
                 "thank you", "more", "again", "because", "but", "right now", "stop"],
    "social": ["I", "you", "thank you", "please", "how are you?", "what", "yes", "no",
               "and", "we", "it", "more", "hello", "goodbye", "help", "stop"],
    "question": ["is", "are", "do", "you", "it", "that", "we", "can", "time", "I",
                 "the", "there", "going", "happened", "this", "about"],
    "yes": ["please", "thank you", "I", "you", "more", "now", "later", "and", "want",
            "it", "that", "again", "okay", "go", "stop", "too"],
    "no": ["thank you", "please", "I", "you", "stop", "more", "not", "now", "later",
           "want", "don't", "it", "that", "again", "help", "go"],
    "pronoun": ["want", "need", "like", "is", "can", "have", "go", "feel", "love",
                "help", "please", "and", "too", "know", "see", "are"],
    "little": ["the", "go", "eat", "you", "me", "it", "that", "home", "bathroom", "bed",
               "play", "see", "a", "my", "water", "food"],
}

AUX = {"will", "was", "could", "would", "should", "did", "do", "does", "be", "has",
       "had", "wants", "likes", "needs", "said", "went", "feels", "knows", "loves",
       "looks", "doesn't", "understand", "care", "worry", "rest", "happened", "going",
       "coming", "dressed"}
LITTLE = {"up", "out", "back", "some", "about", "because", "but", "very", "today",
          "yet", "really", "ready", "done", "sure", "better", "together", "right now",
          "now please"}
QUESTION_START = {"do", "does", "did", "are", "is", "would", "will", "can", "could",
                  "should", "have", "what", "where", "when", "who", "why", "how",
                  "which", "want", "wanna", "shall", "may"}


# ---------------------------------------------------------------- tiles
def guess_pos(label):
    low = label.lower()
    if low in WORDS:
        return WORDS[low]["pos"]
    if low in EXTRA_POS:
        return EXTRA_POS[low]
    if low.endswith("?"):
        return "question"
    if low in AUX:
        return "verb"
    if low in LITTLE:
        return "little" if low not in ("ready", "done", "sure", "better") else "describe"
    return "noun"


def make_tile(label, source="predict", pos=None, emoji=None, speak=None):
    low = label.lower()
    base = WORDS.get(low, {})
    pos = pos or base.get("pos") or guess_pos(label)
    return {
        "id": f"{source}:{low}",
        "label": label,
        "speak": speak or label,
        "pos": pos,
        "emoji": emoji or base.get("emoji") or "",
        "kind": "word" if " " not in label.strip() else "phrase",
        "source": source,
        "picto": pos != "little",  # little grammar words show as big text
    }


def more_tile(category, next_page):
    return {"id": f"more:{category}:{next_page}", "label": "More", "speak": "",
            "pos": "little", "emoji": "➡️", "kind": "more", "source": "nav",
            "picto": False, "page": next_page}


# ---------------------------------------------------------------- personal learning
def time_bucket(t=None):
    h = time.localtime(t or time.time()).tm_hour
    return "morning" if 5 <= h < 12 else "afternoon" if h < 17 else "evening" if h < 21 else "night"


class Usage:
    """Everything AdaptiBoard learns about this user. Saved to data/usage.json.

    bigrams   word -> next word -> count        ("I" -> "want": 14)
    trigrams  "w1 w2" -> next word -> count     ("I want" -> "water": 6)
    unigrams  word -> count
    hours     morning/afternoon/evening/night -> word -> count
    phrases   sentence the user spoke -> {n, last}   (shown on the Chat page)
    """

    KEYS = ("bigrams", "trigrams", "unigrams", "hours", "phrases")

    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()
        for k in self.KEYS:
            setattr(self, k, {})
        if path.exists():
            try:
                d = json.loads(path.read_text())
                for k in self.KEYS:
                    setattr(self, k, d.get(k, {}))
            except Exception:
                pass

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({k: getattr(self, k) for k in self.KEYS}))

    @staticmethod
    def _bump(d, key, word, n=1):
        d.setdefault(key, {})
        d[key][word] = d[key].get(word, 0) + n

    def add(self, prev, word, prev2=None):
        prev, word = (prev or "<s>").lower(), word.lower()
        with self.lock:
            self._bump(self.bigrams, prev, word)
            if prev2:
                self._bump(self.trigrams, f"{prev2.lower()} {prev}", word)
            self.unigrams[word] = self.unigrams.get(word, 0) + 1
            self._bump(self.hours, time_bucket(), word)
            self._save()

    def add_phrase(self, text):
        text = " ".join(text.split()).strip()
        if len(text.split()) < 2 or len(text) > 120:
            return
        with self.lock:
            key = next((k for k in self.phrases if k.lower() == text.lower()), text)
            p = self.phrases.get(key, {"n": 0, "last": 0})
            p["n"] += 1
            p["last"] = time.time()
            self.phrases[key] = p
            self._save()

    def remove_phrase(self, text):
        with self.lock:
            self.phrases.pop(text, None)
            self._save()

    def top_phrases(self, n=40):
        now = time.time()
        # frequency, with a gentle boost for recent use (half-life 3 days)
        score = {k: v["n"] * (1 + 0.5 ** ((now - v["last"]) / 259200)) for k, v in self.phrases.items()}
        return sorted(self.phrases, key=lambda k: -score[k])[:n]

    def after(self, prev):
        return self.bigrams.get((prev or "<s>").lower(), {})

    def after2(self, prev2, prev):
        if not prev2 or not prev:
            return {}
        return self.trigrams.get(f"{prev2.lower()} {prev.lower()}", {})

    def now_words(self):
        return self.hours.get(time_bucket(), {})

    def count(self, word):
        return self.unigrams.get(word.lower(), 0)

    def summary(self, message):
        """Short text about this user's habits, for the language model."""
        top = lambda d, n=8: ", ".join(f"{w} ({c})" for w, c in sorted(d.items(), key=lambda kv: -kv[1])[:n])
        prev = message[-1] if message else None
        prev2 = message[-2] if len(message) > 1 else None
        lines = []
        if self.unigrams:
            lines.append(f"Words they choose most: {top(self.unigrams, 15)}")
        a = self.after2(prev2, prev) or {}
        b = self.after(prev)
        if a:
            lines.append(f'After "{prev2} {prev}" they usually choose: {top(a)}')
        if b:
            lines.append(f'After "{prev or "(start of a sentence)"}" they usually choose: {top(b)}')
        if self.now_words():
            lines.append(f"In the {time_bucket()} they often choose: {top(self.now_words())}")
        if self.phrases:
            lines.append("Sentences they say often: " + "; ".join(f'"{p}"' for p in self.top_phrases(8)))
        return "\n".join(lines) or "(new user - no history yet)"


# ---------------------------------------------------------------- context
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z']*")
_MULTI = sorted((w for w in WORDS if " " in w and WORDS[w]["pos"] in
                 ("noun", "place", "verb", "describe")), key=len, reverse=True)


def extract_context(lines, now=None):
    """lines: [(timestamp, text)] heard around the user.

    Returns {keywords: {word: weight 0..1}, question: bool, options: [..], last: str}.
    Recent words weigh more (half-life 45 s); words older than 2 minutes are ignored.
    """
    now = now or time.time()
    weights = {}
    recent = [(t, s) for t, s in lines if now - t < 120]
    for t, text in recent:
        decay = 0.5 ** ((now - t) / 45.0)
        low = text.lower()
        for phrase in _MULTI:
            if phrase in low:
                weights[phrase] = weights.get(phrase, 0) + decay
        for w in _WORD_RE.findall(low):
            if w in STOPWORDS or len(w) < 3:
                continue
            weights[w] = weights.get(w, 0) + decay
    top = max(weights.values(), default=1.0)
    keywords = dict(sorted(((w, min(1.0, v / top)) for w, v in weights.items()),
                           key=lambda kv: -kv[1])[:10])

    question, options, last = False, [], ""
    if recent:
        t, last = recent[-1]
        toks = _WORD_RE.findall(last.lower())
        if now - t < 40 and toks:
            question = last.strip().endswith("?") or toks[0] in QUESTION_START or (
                len(toks) > 1 and toks[0] in ("so", "hey", "and", "um") and toks[1] in QUESTION_START)
            if " or " in f" {last.lower()} ":
                i = toks.index("or") if "or" in toks else -1
                if i > 0:
                    before = [w for w in toks[:i] if w not in STOPWORDS]
                    after = [w for w in toks[i + 1:] if w not in STOPWORDS]
                    if before and after:
                        options = [before[-1], after[0]]
    return {"keywords": keywords, "question": question, "options": options, "last": last}


# ---------------------------------------------------------------- ranking
def _candidates_after(message):
    if not message:
        return START
    last = message[-1].lower().rstrip("?.!")
    if last in NEXT:
        return NEXT[last]
    if last.split()[-1] in NEXT:
        return NEXT[last.split()[-1]]
    return POS_FALLBACK.get(guess_pos(last), POS_FALLBACK["noun"])


# ---------------------------------------------------------------- Smart Board columns
# The Smart Board is 4 columns x 4 tiles, read left to right like a sentence.
COLUMNS = [
    ("questions", "Questions"),
    ("people", "People"),
    ("actions", "Actions & Feelings"),
    ("things", "Food & Things"),
]
PER_COLUMN = 4
COLUMN_CATS = {
    "questions": ["questions"],
    "people": ["people"],
    "actions": ["actions", "feelings"],
    "things": ["food", "things", "places"],
}
# good first tiles before anything is chosen
COLUMN_START = {
    "questions": ["what", "where", "can I", "when", "who", "how", "why", "do you"],
    "people": ["I", "you", "we", "mom", "dad", "it", "that", "they"],
    "actions": ["want", "need", "feel", "like", "go", "help", "eat", "drink", "tired", "happy"],
    "things": ["water", "food", "bathroom", "TV", "music", "phone", "home", "medicine"],
}

_CAT_OF = {}  # lower label -> column id (by vocabulary category)
for _col, _cats in COLUMN_CATS.items():
    for _c in _cats:
        for _it in CATEGORY_WORDS.get(_c, []):
            _CAT_OF.setdefault(_it["label"].lower(), _col)


def column_of(label, pos=None, question=False):
    """Which Smart Board column a word belongs in (None = not on the Smart Board)."""
    low = label.lower()
    if low in _CAT_OF:
        return _CAT_OF[low]
    pos = pos or guess_pos(label)
    if pos == "pronoun":
        return "people"
    if pos in ("verb", "describe"):
        return "actions"
    if pos in ("noun", "place"):
        return "things"
    if pos == "question":
        return "questions"
    if question and pos in ("yes", "no", "social"):
        return "questions"  # replies live in the first column while someone is asking
    return None


def predict_columns(message, ctx, usage: Usage, profile=None, ai=None):
    """Smart Board: {column id: [4 tiles]}. Rules + personal habits + conversation (+ AI)."""
    scores, info = {}, {}

    def add(label, score, source="predict", pos=None, emoji=None, col=None):
        key = label.lower()
        if not key:
            return
        col = col or column_of(label, pos, ctx.get("question"))
        if not col:
            return
        if key not in scores:
            scores[key] = 0.0
            info[key] = {"label": label, "source": source, "pos": pos, "emoji": emoji, "col": col}
        scores[key] += score
        # the strongest reason decides the badge shown on the tile
        if score >= 40 and source != "predict":
            info[key]["source"] = source

    # 1. every column always has its own words (vocabulary order = everyday frequency)
    for col, cats in COLUMN_CATS.items():
        i = 0
        for c in cats:
            for it in CATEGORY_WORDS.get(c, []):
                add(it["label"], 8 - 0.04 * i, "vocab", it["pos"], it["emoji"], col)
                i += 1
    if profile:
        for name in profile.get("family", []):
            add(name, 14, "vocab", "pronoun", "🧑", "people")
        for like in profile.get("likes", []):
            add(like, 12, "vocab", None, None, "things")

    # 2. grammar rules: what usually comes next
    if message:
        for i, w in enumerate(_candidates_after(message)):
            add(w, 100 - 4 * i)
    else:
        for col, words in COLUMN_START.items():
            for i, w in enumerate(words):
                add(w, 60 - 5 * i, "predict", None, None, col)

    # 3. personal habits (the more they use AdaptiBoard, the more this wins)
    prev = message[-1] if message else None
    prev2 = message[-2] if len(message) > 1 else None
    for w, n in usage.after2(prev2, prev).items():
        add(WORDS.get(w, {}).get("label", w), min(80, 28 * n), "history")
    for w, n in usage.after(prev).items():
        add(WORDS.get(w, {}).get("label", w), min(60, 18 * n), "history")
    for w, n in usage.now_words().items():
        add(WORDS.get(w, {}).get("label", w), min(18, 3 * n), "history")
    for w, n in usage.unigrams.items():
        add(WORDS.get(w, {}).get("label", w), min(16, 1.5 * n), "history")

    # 4. the conversation around them
    for w, weight in list(ctx.get("keywords", {}).items())[:8]:
        add(WORDS.get(w, {}).get("label", w), 55 * weight, "context")
    for it in ctx.get("items", []):
        add(it["label"], 90, "context", it.get("pos"), it.get("emoji"))
    for opt in ctx.get("options", []):  # "pizza or pasta?" -> both at the top
        add(opt, 240, "context")
    if ctx.get("question"):
        add("yes", 175, "context", "yes", "✅", "questions")
        add("no", 165, "context", "no", "❌", "questions")
        for a in ctx.get("answers", [])[:2]:
            add(a, 140, "context", "social", None, column_of(a) or "questions")
        add("I don't know", 60, "context", "social", "🤷", "questions")
    if profile:
        for name in profile.get("family", [])[:4]:
            if name.lower() in ctx.get("last", "").lower():
                add(name, 70, "context", "pronoun", "🧑", "people")

    # 5. AI suggestions (they already saw the habits + conversation)
    for col, labels in (ai or {}).items():
        for i, t in enumerate(labels):
            add(t["label"], 85 - 12 * i, "ai", t.get("pos"), t.get("emoji"), col)

    used = {w.lower() for w in message[-1:]}
    cols = {c: [] for c, _ in COLUMNS}
    for key in sorted(scores, key=lambda k: -scores[k]):
        if key in used:
            continue
        d = info[key]
        if len(cols[d["col"]]) < PER_COLUMN:
            t = make_tile(d["label"], d["source"], d["pos"], d["emoji"])
            t["id"] = f"{d['col']}:{key}"
            cols[d["col"]].append(t)
    return cols


# ---------------------------------------------------------------- other pages
def paged(items, page, key):
    """16 tiles per page; 15 + a More tile when there are more."""
    if len(items) <= SLOTS:
        return items
    per = SLOTS - 1
    pages = (len(items) + per - 1) // per
    page = page % pages
    return items[page * per:(page + 1) * per] + [more_tile(key, (page + 1) % pages)]


def more_page(categories):
    """The "More words" page: one tile per category."""
    return [{"id": f"cat:{cid}", "label": label, "speak": "", "pos": pos, "emoji": emoji,
             "kind": "category", "source": "nav", "picto": False, "target": cid}
            for cid, label, emoji, pos in categories]


def chat_page(page, usage: Usage):
    """Chat: sentences this user has said before (most used first), then ready-made ones."""
    tiles, seen = [], set()
    for text in usage.top_phrases(60):
        t = make_tile(text, "history", "question" if text.endswith("?") else "social", "💬")
        t["kind"], t["picto"] = "phrase", False
        tiles.append(t)
        seen.add(text.lower())
    defaults = CATEGORY_WORDS.get("chat", []) + [
        q for q in CATEGORY_WORDS.get("questions", []) if " " in q["label"]]
    for it in defaults:
        if it["label"].lower() in seen:
            continue
        seen.add(it["label"].lower())
        t = make_tile(it["label"], "vocab", it["pos"], it["emoji"], it.get("speak"))
        t["kind"] = "phrase"
        tiles.append(t)
    return paged(tiles, page, "chat")


def category_page(category, page, ctx, usage: Usage, profile=None):
    """Tiles for a category, most relevant first. 15 per page + a More tile if needed."""
    items = list(CATEGORY_WORDS.get(category, []))
    if category == "people" and profile:
        names = [n for n in profile.get("family", []) if n]
        items = [{"label": n, "pos": "pronoun", "emoji": "🧑", "speak": n} for n in names] + items
    kw = ctx.get("keywords", {})

    def score(i, it):
        low = it["label"].lower()
        return -i + 3 * min(usage.count(low), 10) + 40 * kw.get(low, 0)

    ranked = sorted(enumerate(items), key=lambda p: -score(*p))
    tiles = []
    for _, it in ranked:
        t = make_tile(it["label"], "vocab", it["pos"], it["emoji"], it.get("speak"))
        if it.get("speak") and it["speak"] != it["label"]:
            t["kind"] = "phrase"
        tiles.append(t)
    return paged(tiles, page, category)
