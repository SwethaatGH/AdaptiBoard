"""
needs.py - the Needs page: one-select triggers that DO something, not just words.

Each need has a level:
    emergency  full-screen red alert on the board + alarm + the sentence spoken
               (repeated) + a red banner on the controller + caregiver phone push
    urgent     chime + sentence spoken twice + caregiver phone push
    normal     sentence spoken once

Caregiver phone push (optional): set NTFY_TOPIC=some-long-random-name in server/.env,
install the free "ntfy" app on the caregiver's phone and subscribe to the same topic.
AdaptiBoard does NOT dial 911 itself - it says it out loud and alerts people nearby.

Edit this list freely: label | emoji (legacy, not shown) | level | sentence | ARASAAC pictogram word.
The first row (4 tiles) is reachable fastest, so emergencies go first.
"""

NEEDS = [
    # label,              emoji, level,       spoken sentence,                                          pictogram
    ("Chest pain",        "💔", "emergency", "Emergency! I have chest pain. Please call nine one one now.", "chest pain"),
    ("Can't breathe",     "🫁", "emergency", "Emergency! I can't breathe. Please call nine one one now.",   "can't breathe"),
    ("Seizure",           "⚡", "emergency", "Emergency! I think I'm having a seizure. Call nine one one and stay with me.", "seizure"),
    ("Dizzy / faint",     "😵", "urgent",    "I feel dizzy and faint. Please help me right now.",            "dizzy"),
    ("Bad pain",          "🤕", "urgent",    "I'm in a lot of pain. Please get help.",                       "pain"),
    ("Call nurse",        "🔔", "urgent",    "Please call the nurse.",                                       "nurse"),
    ("Call family",       "📞", "urgent",    "Please call my family.",                                       "family"),
    ("Medicine",          "💊", "normal",    "I need my medicine.",                                          "medicine"),
    ("Bathroom",          "🚻", "normal",    "I need to use the bathroom.",                                  "bathroom"),
    ("Water",             "💧", "normal",    "Can I have some water, please?",                               "water"),
    ("Move me",           "🔄", "normal",    "Please help me change my position.",                           "move me"),
    ("Too hot",           "🥵", "normal",    "I'm too hot.",                                                 "hot"),
    ("Too cold",          "🥶", "normal",    "I'm cold.",                                                    "cold"),
    ("Too loud",          "🔊", "normal",    "It's too loud.",                                               "too loud"),
    ("Tired / rest",      "😴", "normal",    "I'm tired. I want to rest.",                                   "tired"),
    ("Stop",              "✋", "normal",    "Stop, please.",                                                "stop"),
]

POS = {"emergency": "no", "urgent": "no", "normal": "noun"}


def need_tiles():
    tiles = []
    for label, emoji, level, say, picto in NEEDS:
        tiles.append({
            "id": f"need:{label.lower()}",
            "label": label,
            "speak": say,
            "pos": POS[level] if label not in ("Water", "Medicine", "Bathroom") else "noun",
            "emoji": emoji,
            "kind": "need",
            "source": "vocab",
            "picto": picto is not None,
            "icon": picto,
            "need": {"level": level, "say": say},
        })
    return tiles
