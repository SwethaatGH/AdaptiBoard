# AdaptiBoard

**A context-aware AAC communication board you control with your eyes and an EEG headset.**

AdaptiBoard helps people who can't speak or use their hands to build sentences from picture tiles.
It runs on two screens:
- **Board screen:** the symbol board.
- **Controller screen:** five keys that flicker at different rates. The arrows sit in the four corners (← top-left, ↑ top-right, ↓ bottom-left, → bottom-right) and **OK / Select** is in the middle, so the keys are as far apart as possible.

The user looks at a key. A NeuroPawn EEG headset picks up that key's flicker rate in the visual cortex (SSVEP), and the highlight on the board moves like a TV remote. Each chosen word is spoken aloud. The next page of tiles is predicted from the words chosen so far *and* from what people nearby are saying.

| Smart Board, after someone asked "pizza or pasta?" | Controller, mid-flicker |
|---|---|
| ![board](docs/board-context.png) | ![controller](docs/controller-flicker.png) |
| **More words** (categories → words) | **Needs** (one-select triggers) |
| ![more words](docs/board-more-words.png) | ![needs](docs/board-needs.png) |

Built at BR41N.IO (Neurotech @ NC State) for the NeuroPawn track.

---

## What it does

- **Remote-control navigation using only 5 commands** (↑ ↓ ← → OK). Each key on the controller has its own colour and flicker rate: **Up 6 Hz (yellow), Down 8 Hz (purple), Left 10 Hz (blue), Right 12 Hz (pink), OK 15 Hz (mint)**.
- **Side menu: Back, Smart Board, More words, Keyboard, Chat, Needs.** Each one opens its own page.
- **Smart Board, chosen column by column.** It has 4 columns of 4 tiles, read left to right like a sentence: **Questions → People → Actions & Feelings → Food & Things**. Columns are colour-coded (purple, yellow, green, orange) with no text labels.
  1. Pick a **column** with ← → and open it with **OK**.
  2. Pick a **tile** with ↑ ↓ and say it with **OK**.
  3. The highlight jumps to the **next column**, and every column re-predicts from the words chosen so far. After the last column it lands on **Speak**.
- **More words** (menu page). It opens 12 categories: People, Actions, Feelings, Food & Drink, Places, Things, Questions, Describe, Body, Time, Activities and Little words.
  - Pick a category, then a word. The word is added, and you go back to the Smart Board with the next column highlighted.
  - **Back** goes up one level (word page → categories).
- **Keyboard** (menu page). Type any word letter by letter with the remote, or with a physical keyboard (typing letters anywhere opens this page).
  - Word suggestions appear as you type ("piz" suggests **pizza**), ranked by what this user uses.
  - **Add word** puts the typed word into the sentence and stays on the keyboard for the next word. New words are learned.
- **Grammar fix.** Tiles give base words, so the message bar shows a corrected sentence above them, and **Speak** says the corrected one: "I was walk" → **"I was walking."**, "he want go park" → **"He wants to go to the park."**. GPT does it when a key is set (only accepted if it keeps all the user's words in order); otherwise offline rules in `server/grammar.py` handle the common cases.
  - **Chat** lists sentences this user has said before, most used first, then ready-made phrases and questions. Everything the user **Speaks** is saved there automatically.
  - **Needs** holds one-select triggers that *do* something:
    - Red **emergency** tiles (Chest pain, Can't breathe, Seizure) sound a siren and speak *"Emergency! … Please call nine one one now."* three times. They show a full-screen **Call 911** alert on the board and a red banner on the controller, and send a phone push to the caregiver (optional, via [ntfy](https://ntfy.sh)).
    - Pink **urgent** tiles (Dizzy, Bad pain, Call nurse, Call family) chime, speak twice and notify the caregiver.
    - The rest just speak their sentence.
    - AdaptiBoard never dials 911 itself.
- **Every choice is spoken immediately** using natural neural voices (free Microsoft Edge voices via `edge-tts`, cached). If those fail, the browser's own voice is used.
- **Conversation context.** The board laptop's microphone listens to the people around the user. "Do you want pizza or pasta?" puts **yes / no** at the top of Questions and **pizza / pasta** at the top of Food & Things.
- **Personalised, and gets better with use.** The server learns what this user picks (`server/data/usage.json`):
  - after each word, and after each pair of words ("I want" → juice);
  - at each time of day;
  - which whole sentences they say.

  Those habits rank the Smart Board and are sent to the AI.
- **AI layer (optional).** With one API key (OpenAI GPT, Gemini, Groq or local Ollama):
  - the model suggests tiles for every column, using the conversation, the profile *and the user's habits*;
  - it offers a one-select **"Use sentence"** completion ("I want go park" → "I want to go to the park.").

  Completions that change the user's own words are thrown away.
- **Safety and accessibility.**
  - Clean white board with AAC colour coding and text on every tile, the high-legibility Atkinson Hyperlegible font, and ARASAAC pictograms.
  - Tiles never change under the highlight. OK is ignored while tiles load, and one long gaze can't select twice.
  - An emergency alert can only be cancelled after 3 s, so the gaze that triggered it can't cancel it.
  - Flicker needs an epilepsy warning and stops when the tab is hidden. Audio is never stored.

---

## How it fits together

```
 ┌────────────── LAPTOP A: Board ───────────────┐          ┌──── LAPTOP B: Controller ────┐
 │  Chrome: http://localhost:8000               │          │  Chrome: http://A-IP:8000/   │
 │  - 4x4 board, menu, Speak  (speakers)        │◄──┐  ┌──►│          controller          │
 │  - microphone → conversation context         │   │  │   │  5 flickering keys           │
 │                                              │  WebSocket │                              │
 │  python server/main.py   (port 8000)  ───────┼───┴──┘   └──────────────────────────────┘
 │  - hub between board / controller / decoder  │                   ▲ the user looks here
 │  - predictor + LLM, neural TTS, pictograms   │◄────┐             │
 └──────────────────────────────────────────────┘     │       NeuroPawn headset (USB)
                                                      │             │
                                       python eeg/decoder.py  (on A or B, wherever
                                       the headset is plugged in) → up/down/left/right/ok
```

| Folder | What's inside |
|---|---|
| `server/` | FastAPI server: WebSocket hub, `predictor.py` (Smart Board columns + personal learning), `llm.py` (AI), `needs.py` (Needs triggers), `speech.py` (TTS/STT), `icons.py` (pictograms), `vocab.py` (all words and categories) |
| `web/` | React + TypeScript + Vite + Framer Motion app. `/` = board, `/controller` = controller |
| `eeg/` | `decoder.py` (SSVEP → commands), `fbcca.py` (training-free filter-bank CCA), `eeg_bci.py` (the team's headset tools: signal check, clench model) |

**Tech stack:**
- React 18
- TypeScript
- Vite
- Framer Motion (the gliding mint focus ring)
- Lucide icons
- FastAPI + WebSockets
- BrainFlow
- NumPy/SciPy
- edge-tts
- ARASAAC pictograms
- Gemini / Groq / OpenAI / Ollama

---

## Quick test on one laptop (no headset)

Needs **Python 3.10+**, **Node 18+** and **Chrome**.

```bash
cd adaptiboard
./start.sh            # Windows: start.bat
```

The first run installs everything and builds the web app (about 1–2 minutes). Then:

1. Open **http://localhost:8000** in Chrome and click **Start**. This allows sound and asks for the microphone.
2. Open **http://localhost:8000/controller** in a second window.
3. Click **Keys only (click to test)**, then click the arrow keys. The board's highlight moves.
4. The **arrow keys + Enter** on the board itself also work.
5. **Settings (⚙ on the board) → Simulate the conversation** lets you inject sentences like "Do you want tea or coffee?" when the room is too noisy for the mic.

---

## Run on two laptops (the real setup)

Both laptops must be on the **same Wi-Fi**. Campus and guest Wi-Fi often block laptops from talking to each other. If the controller can't connect, use a **phone hotspot** for both laptops.

### Laptop A: Board (runs the server, has the speakers + mic)

```bash
cd adaptiboard
./start.sh                    # Windows: start.bat
```

It prints something like:

```
  Board (this laptop):  http://localhost:8000/
  Controller laptop:    http://192.168.1.23:8000/controller
  EEG decoder:          python eeg/decoder.py --server http://192.168.1.23:8000 ...
```

- Open **http://localhost:8000** in Chrome on Laptop A and click **Start**.
- Use `localhost` on this laptop, not the IP. The microphone only works on `localhost`.
- macOS asks *"Allow Python to accept incoming connections?"*: click **Allow**. On Windows, allow Python through the firewall for **Private networks**.

### Laptop B: Controller (only needs Chrome)

1. Open the **Controller laptop** address printed above, e.g. `http://192.168.1.23:8000/controller`.
2. The setup panel should show **Server connected · Board connected**.
3. Test first: click **Keys only (click to test)**, click a few keys, and watch Laptop A's board move.
4. Press **Full screen**, set the display to **60 Hz**, then **Start flicker** (or press Space). Esc stops it and reopens setup.

### The EEG decoder (on whichever laptop the headset is plugged into)

```bash
# one-time setup (in the adaptiboard folder)
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r eeg/requirements.txt

# find the headset port:  macOS  ls /dev/cu.*     Windows  Device Manager → Ports (COMx)
# close the NeuroPawn EXG Visualizer first (only one program can use the headset)

python eeg/decoder.py --server http://192.168.1.23:8000 --port /dev/cu.usbmodemXXXX
#   add --imu if your box says IMU;  use --port COM3 on Windows;  --notch 50 outside the Americas
```

When the decoder connects, the controller shows **EEG decoder connected**. Start the flicker and look at a key:
- A mint bar under the key fills as the decoder becomes confident.
- Once it decides, the key flashes and the board moves.
- The decoder only decides while the keys are flickering.

**No headset yet?** `python eeg/decoder.py --server http://localhost:8000 --simulate` makes fake EEG. Type `r`, `l`, `u`, `d` or `o` + Enter in that terminal to "look" at a key, and see the full EEG → board path work.

**Getting a clean signal:**
- Put electrodes over the back of the head: O1, Oz, O2, PO3, POz, PO4.
- Use conductive paste, and part the hair under each electrode.
- Check signal quality with `python eeg/eeg_bci.py check --port …`.
- Check the SSVEP peaks with `python eeg/eeg_bci.py spectrum --port … --freqs 6 8 10 12 15` while looking at one key.
- **Tuning:**
  - `--window 4`: seconds of EEG per decision. Longer is steadier but slower.
  - `--z 3`: evidence needed. Higher means fewer mistakes but slower.
  - `--ok-strict 1.3`: OK needs extra evidence.
  - `--ok-rearm 8`: after OK, look away (or keep looking for 8 s) before another OK.
- **Optional jaw clench as a second OK:** train with `eeg_bci.py record/train` (see its header), then add `--clench-model switch.joblib`.

---

## AI and speech settings (optional)

Copy `server/.env.example` to `server/.env` and set **one** key. With no key, the offline predictor still works.

| Option | Cost | Notes |
|---|---|---|
| `GEMINI_API_KEY` | free for NC State | best default; get a key at aistudio.google.com |
| `GROQ_API_KEY` | free tier | very fast; also enables server speech-to-text (Whisper) |
| `OPENAI_API_KEY` | paid | gpt-4o-mini by default |
| `OLLAMA_MODEL=llama3.2` | free, local, open source | install Ollama and run `ollama pull llama3.2` |

**Caregiver phone alerts (optional):** set `NTFY_TOPIC=some-long-random-name` in `server/.env`, install the free **ntfy** app on the caregiver's phone and subscribe to the same name. Emergency and urgent Needs then push a notification.

The board's status pill shows which AI is active.

**Listening options** (board ⚙ settings):
- **Auto** (default). Uses Server Whisper when the server has it (a `GROQ_API_KEY` is enough, free), otherwise Browser.
- **Server Whisper.** Records each spoken sentence, cuts it at the pause after it (~0.8 s) and sends it to Groq / OpenAI / local `faster-whisper`. Silence is never sent. Text appears about a second after the speaker stops.
- **Browser** (Chrome's built-in recognition, free, live words). It needs Google's servers; if it fails (e.g. a "network" error), the board switches to Server Whisper by itself and shows the error otherwise.
- **Off.**

**Voices:** 10 neural voices (US/UK/India/Australia, female/male/child), selectable in ⚙ settings. They need internet; without it the board uses the browser voice.

---

## Controls cheat sheet

**Smart Board** (column-wise)

| Highlight is on… | ↑ / ↓ | ← / → | OK |
|---|---|---|---|
| a **column** | ↑ top bar | previous / next column (← from the first opens the menu) | enter the column |
| a **tile** in a column | previous / next tile (↑ past the first leaves the column) | leave the column, move to the next one | **say it**, add it, jump to the next column |

**Keyboard page**

| Highlight is on… | ↑ / ↓ | ← / → | OK |
|---|---|---|---|
| a **keyboard row** | previous / next row (↑ from the top reaches Speak) | ← menu | enter the row |
| a **key** | leave the row, move up / down | previous / next key | type it (Add word adds the typed word) |

**More words, category pages, Chat, Needs** (row-wise)

| Highlight is on… | ↑ / ↓ | ← / → | OK |
|---|---|---|---|
| a **row** | previous / next row (↑ from the top row reaches Speak) | ← opens the menu | enter the row |
| a **tile** | leave the row and move up / down | previous / next tile (← past the first leaves the row) | choose it |

**Everywhere**

| Highlight is on… | ↑ / ↓ | ← / → | OK |
|---|---|---|---|
| the **menu** | previous / next item | → back to the page | open it (Back = up one level) |
| the **top bar** | ↓ back to the page | Speak · Use sentence · Delete · Clear | do it |
| an **emergency alert** | – | – | cancel (after 3 s) |

Physical keyboard on the board:
- **Arrows + Enter** are the five commands.
- **Letters** open the Keyboard page and type into it; **Enter** adds the typed word.
- **Space** toggles the flicker on the controller.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Controller says "Connecting to server…" | Same Wi-Fi? Correct IP? Firewall allowed? Try a phone hotspot. |
| No sound | Click **Start** on the board (browsers block audio until a click). Check volume. |
| "Microphone needs http://localhost" | Open the board on Laptop A via `localhost`, not the IP. |
| Wrong or slow EEG moves | Check signal quality, add paste, set the screen to 60 Hz, raise `--z`, lengthen `--window`. Confirm frequencies match on the controller and in the decoder log. |
| `No module named brainflow` | `pip install -r eeg/requirements.txt` in the active venv. |
| Pictograms missing | They download from ARASAAC on first use (needs internet once, then cached). Emoji are shown meanwhile. |
| Changed the web code | `cd web && npm run build`, then refresh. For live editing: `npm run dev` → http://localhost:5173. |

---

## Honest limitations

- **Frequency choice:** 12 Hz is exactly double 6 Hz, so the decoder can mistake Up for Right. On simulated EEG the decoder (FBCCA, 4 s window) got:

  | Up frequency (rest 8 / 10 / 12 / 15 Hz) | Accuracy, strong signal | Accuracy, weak signal |
  |---|---|---|
  | **6 Hz** (default) | 83% | 55% |
  | **6.67 Hz** | 95% | 64% |

  If Up and Right get confused with the real headset, set Up to **6.67** on the controller's setup panel (the decoder follows automatically).
- The EEG path was tested end to end with simulated EEG and with the controller's manual keys. Real-headset accuracy depends on electrode contact, the person, the screen and the room. **Measure it and report real numbers** (correct commands, seconds per selection, accidental OKs).
- SSVEP flicker isn't suitable for people with photosensitive epilepsy.
- Prediction quality depends on the AI provider. The offline predictor is rule-based plus personal learning.
- An always-on microphone raises privacy concerns: tell everyone in the room, and use the Mic → Off setting when needed.
- ARASAAC pictograms are licensed **CC BY-NC-SA** (non-commercial).

## Credits

- Pictograms: Sergio Palao, [ARASAAC](https://arasaac.org), Government of Aragon (CC BY-NC-SA 4.0).
- `eeg/fbcca.py` is adapted from [NeuroKnights](https://github.com/alexyurchuk/NeuroKnights) (MIT).
- The headset is a NeuroPawn Knight board, connected via BrainFlow.
