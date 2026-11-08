"""
grammar.py - turn the chosen tiles into a grammatical sentence.

    "I was walk"        -> "I was walking."
    "he want go park"   -> "He wants to go to the park."
    "I is tired"        -> "I am tired."

With an LLM key (OPENAI_API_KEY etc.) GPT does it (llm.polish), and the result is only
accepted if it keeps all of the user's own words in order. Without a key, or if GPT
is slow / changes the meaning, the offline rules below are used.
"""
import re

from vocab import WORDS

COMMON_VERBS = set("""
walk run go eat drink sleep play watch read write talk say tell help want need like love
hate make cook bake wash brush clean sit stand lie rest swim dance sing listen look see
hear feel think know call come get give take put open close turn buy pay ride drive work
study learn draw paint shop visit stay wait sit hug kiss cry laugh smile jump climb
move push pull carry bring send find try use wear change fix start stop finish leave
""".split())
VERBS = COMMON_VERBS | {w for w, e in WORDS.items() if e.get("pos") == "verb" and " " not in w}
STATIVE = {"want", "need", "like", "love", "hate", "know", "have", "see", "hear", "think", "understand"}
WANT_LIKE = {"want", "need", "like", "love", "hate", "have", "try", "wanted", "needed", "liked",
             "wants", "needs", "likes", "loves", "has", "tries"}

BE = {"am", "is", "are", "was", "were", "be", "been"}
SUBJECT_BE = {"i": "am", "you": "are", "we": "are", "they": "are", "he": "is", "she": "is", "it": "is"}
SUBJECT_BE_PAST = {"i": "was", "he": "was", "she": "was", "it": "was", "you": "were", "we": "were", "they": "were"}
THIRD = {"he", "she", "it", "mom", "dad", "grandma", "grandpa", "mommy", "daddy", "nurse", "doctor"}
QUESTION_START = {"what", "where", "when", "who", "why", "how", "which", "can", "could", "do", "does",
                  "did", "is", "are", "will", "would", "should", "may"}
THE_PLACES = {"park", "store", "shop", "bathroom", "hospital", "beach", "kitchen", "doctor", "mall",
              "library", "pool", "zoo", "garden", "bedroom", "gym", "movies", "restaurant"}
NO_ARTICLE_PLACES = {"home", "school", "church", "work", "bed", "outside", "inside", "there", "here"}
DOUBLE = {"run", "swim", "sit", "get", "stop", "shop", "put", "hit", "cut", "plan", "jog", "dig",
          "hug", "chat", "nap", "begin", "skip", "drop", "clap", "tap", "win"}
IRREGULAR_S = {"go": "goes", "do": "does", "have": "has", "be": "is"}


def ing(v):
    if v.endswith("ie"):
        return v[:-2] + "ying"
    if v in DOUBLE:
        return v + v[-1] + "ing"
    if v.endswith("e") and not v.endswith(("ee", "ye", "oe")) and v != "be":
        return v[:-1] + "ing"
    return v + "ing"


def third_person(v):
    if v in IRREGULAR_S:
        return IRREGULAR_S[v]
    if v.endswith(("s", "sh", "ch", "x", "z", "o")):
        return v + "es"
    if v.endswith("y") and len(v) > 1 and v[-2] not in "aeiou":
        return v[:-1] + "ies"
    return v + "s"


def offline(words):
    """Small rule-based fixer. Works on the raw word list, returns a sentence string."""
    toks = [t for w in words for t in str(w).split() if t]
    if not toks:
        return ""
    out = []
    for i, t in enumerate(toks):
        low = t.lower()
        prev = out[-1].lower() if out else ""
        prev2 = out[-2].lower() if len(out) > 1 else ""
        nxt = toks[i + 1].lower() if i + 1 < len(toks) else ""

        # subject + wrong "be":  I is -> I am, he am -> he is, you was -> you were
        if low in BE and prev in SUBJECT_BE and low not in ("be", "been"):
            low = SUBJECT_BE_PAST[prev] if low in ("was", "were") else SUBJECT_BE[prev]
            out.append(low)
            continue
        # be + verb -> -ing:  I was walk -> I was walking
        if prev in BE and low in VERBS and low not in STATIVE:
            out.append(ing(low))
            continue
        # question word + subject -> add do/does:  what you want -> what do you want
        if len(out) == 1 and prev in ("what", "where", "when", "why", "how") and low in SUBJECT_BE \
                and nxt in VERBS:
            out.append("does" if low in ("he", "she", "it") else "do")
        # want/need/like + verb -> "to":  I want go -> I want to go
        if prev in WANT_LIKE and low in VERBS and low != "to":
            out.append("to")
        # he/she/Mom + verb -> -s:  he want -> he wants
        elif prev in THIRD and prev2 not in ("can", "will", "do", "does", "did", "could", "would", "should") \
                and low in VERBS:
            out.append(third_person(low))
            continue
        # go / come / went + place -> "to the":  go park -> go to the park
        if prev in ("go", "goes", "going", "went", "come", "coming") and low in THE_PLACES:
            out.extend(["to", "the"])
        elif prev in ("go", "goes", "going", "went", "come", "coming") and low not in NO_ARTICLE_PLACES \
                and WORDS.get(low, {}).get("pos") == "place":
            out.append("to")
        # a + vowel -> an
        if prev == "a" and low[:1] in "aeiou" and out:
            out[-1] = "an"
        out.append("I" if low == "i" else t if t[:1].isupper() else low)

    text = " ".join(out)
    text = re.sub(r"\s+([?.!,'])", r"\1", text).replace(" n't", "n't")
    text = text[:1].upper() + text[1:]
    if not re.search(r"[.?!]$", text):
        text += "?" if toks[0].lower() in QUESTION_START else "."
    return text


_CONTENT_SKIP = BE | {"a", "an", "the", "to", "i", "do", "does", "did"}


def keeps_words(sentence, words):
    """True if every content word of the user (or its stem) still appears, in order."""
    low, pos = sentence.lower(), 0
    for w in " ".join(words).lower().split():
        w = w.strip("?.!,")
        if not w or w in _CONTENT_SKIP:
            continue
        stem = w if len(w) <= 3 else w[:max(3, len(w) - 2)]  # walk~walking, study~studies
        i = low.find(stem, pos)
        if i < 0:
            return False
        pos = i + len(stem)
    n_user = len(" ".join(words).split())
    return len(sentence.split()) <= n_user * 2 + 4  # no long made-up additions
