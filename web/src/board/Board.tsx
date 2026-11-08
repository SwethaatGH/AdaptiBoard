import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { Mic, Volume2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chime, siren, unlockAlarm } from "../lib/alarm";
import { postJSON, useHub } from "../lib/hub";
import { Listener } from "../lib/stt";
import { prefetch, setVoice, speak, speechDone, stop as stopSpeech, unlockAudio } from "../lib/tts";
import type { Alert, Category, Column, ContextInfo, Direction, MessageItem, Pos, Tile } from "../lib/types";
import { AlertOverlay } from "./AlertOverlay";
import { ContextStrip } from "./ContextStrip";
import { COLS, Grid, rowsOf } from "./Grid";
import { HintBar } from "./HintBar";
import { buildKeyRows, KeyboardPage } from "./Keyboard";
import { fit, move, type Focus, type Layout } from "./nav";
import { NavBar } from "./NavBar";
import { SettingsDrawer } from "./SettingsDrawer";
import { useSettings } from "./settings";
import { SmartBoard } from "./SmartBoard";
import { TopBar, type ActionId } from "./TopBar";

interface Page {
  id: string; // smart | more | keyboard | chat | needs | <category id>
  index: number; // page number inside long lists
  label?: string; // category name, for the breadcrumb
}
interface LexEntry {
  label: string;
  pos: Pos;
  n: number;
}

const SMART: Page = { id: "smart", index: 0 };
const BACK: Category = { id: "back", label: "Back", emoji: "↩️" };
const FALLBACK_CATS: Category[] = [
  { id: "smart", label: "Smart Board", emoji: "✨" },
  { id: "more", label: "More words", emoji: "📚" },
  { id: "keyboard", label: "Keyboard", emoji: "⌨️" },
  { id: "chat", label: "Chat", emoji: "💬" },
  { id: "needs", label: "Needs", emoji: "🆘" },
];
const TOP_PAGES = new Set(["smart", "more", "keyboard", "chat", "needs"]);
const KEYBOARD: Page = { id: "keyboard", index: 0 };
// after choosing a word from a "More words" category, jump to the column that usually comes next
const CATEGORY_COLUMN: Record<string, number> = {
  questions: 0, people: 1, actions: 2, feelings: 2, activities: 2, food: 3, things: 3, places: 3,
};

/** Text that is shown + spoken for a list of chosen tiles. */
const sentence = (m: MessageItem[]) => m.map((x) => x.text).join(" ").replace(/\s+([?.!,])/g, "$1");
const afterColumn = (col: number): Focus => (col < 3 ? { zone: "cols", col: col + 1 } : { zone: "actions", index: 0 });
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const pageHome = (id: string): Focus =>
  id === "smart" ? { zone: "cols", col: 0 } : id === "keyboard" ? { zone: "krows", row: 1 } : { zone: "rows", row: 0 };

export default function Board() {
  const [settings, update] = useSettings();
  const [cats, setCats] = useState<Category[]>(FALLBACK_CATS);
  const [voices, setVoices] = useState<{ id: string; label: string }[]>([]);
  const [lexicon, setLexicon] = useState<LexEntry[]>([]);
  const [started, setStarted] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const [page, setPage] = useState<Page>(SMART);
  const [history, setHistory] = useState<Page[]>([]);
  const [tiles, setTiles] = useState<Tile[]>([]); // rows pages
  const [columns, setColumns] = useState<Column[]>([]); // Smart Board
  const [loading, setLoading] = useState(true);
  const [completion, setCompletion] = useState("");
  const [loadN, setLoadN] = useState(0);

  const [message, setMessage] = useState<MessageItem[]>([]);
  const [spoken, setSpoken] = useState(false);
  const [typed, setTyped] = useState("");
  const [polished, setPolished] = useState<{ key: string; text: string; source: string } | null>(null);
  const [focus, setFocus] = useState<Focus>({ zone: "cols", col: 0 });
  const [pulseId, setPulseId] = useState<string | null>(null);
  const [lastCmd, setLastCmd] = useState<{ dir: Direction; n: number; source: string } | null>(null);

  const [alert, setAlert] = useState<Alert | null>(null);
  const [alertArmed, setAlertArmed] = useState(false);
  const [notified, setNotified] = useState(false);

  const [ctx, setCtx] = useState<ContextInfo | null>(null);
  const [pendingCtx, setPendingCtx] = useState(false);
  const [interim, setInterim] = useState("");
  const [micError, setMicError] = useState("");
  const levelRef = useRef(0);

  const reqRef = useRef(0);
  const ctxVersionRef = useRef(0);
  const pristineRef = useRef(true); // no navigation since the tiles appeared
  const lastOkRef = useRef(0);
  const cmdN = useRef(0);
  const typingRef = useRef(false); // a physical keyboard is being used to type letters

  // ---------------------------------------------------------------- data
  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((c) => {
        setCats(c.categories);
        setVoices(c.voices);
        setLexicon(c.lexicon ?? []);
      })
      .catch(() => {});
  }, []);

  useEffect(() => setVoice(settings.voice), [settings.voice]);

  const load = useCallback(
    async (pg: Page, msg: MessageItem[]) => {
      const req = ++reqRef.current;
      if (pg.id === "keyboard") {
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const d = await postJSON("/api/predict", {
          message: msg.map((m) => m.label),
          page: pg.id,
          pageIndex: pg.index,
          profile: settings.profile,
        });
        if (req !== reqRef.current) return; // a newer request replaced this one
        if (pg.id === "smart") setColumns(d.columns ?? []);
        else setTiles(d.tiles);
        setCompletion(d.completion || "");
        ctxVersionRef.current = d.contextVersion;
        pristineRef.current = true;
        setPendingCtx(false);
        setLoadN((n) => n + 1);
        if (settings.speakOnSelect) {
          const all: Tile[] = pg.id === "smart" ? (d.columns ?? []).flatMap((c: Column) => c.tiles) : d.tiles;
          prefetch(all.filter((t) => t.kind === "word" || t.kind === "phrase").map((t) => t.speak));
        }
      } catch {
        if (req === reqRef.current) pg.id === "smart" ? setColumns([]) : setTiles([]);
      } finally {
        if (req === reqRef.current) setLoading(false);
      }
    },
    [settings.profile, settings.speakOnSelect],
  );

  useEffect(() => {
    load(SMART, []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------------------------------------------------------------- keyboard suggestions
  const suggestions = useMemo(() => {
    const token = typed.split(" ").pop()?.toLowerCase() ?? "";
    if (!token) return [];
    const heard = new Set([...(ctx?.keywords ?? []), ...(ctx?.items ?? [])].map((w) => w.toLowerCase()));
    return lexicon
      .filter((e) => e.label.toLowerCase().startsWith(token))
      .map((e) => ({ e, s: e.n * 3 + (heard.has(e.label.toLowerCase()) ? 20 : 0) - e.label.length * 0.3 }))
      .sort((a, b) => b.s - a.s)
      .slice(0, 6)
      .map((x) => x.e.label);
  }, [typed, lexicon, ctx]);
  const keyRows = useMemo(() => buildKeyRows(suggestions, typed), [suggestions, typed]);

  // ---------------------------------------------------------------- grammar (I was walk -> I was walking.)
  const rawSentence = sentence(message);
  const msgKey = message.map((m) => m.text).join(" ");
  useEffect(() => {
    if (spoken || message.length < 2) return;
    const key = msgKey;
    const t = setTimeout(() => {
      postJSON("/api/polish", { words: message.map((m) => m.text) })
        .then((r) => r.text && setPolished({ key, text: r.text, source: r.source }))
        .catch(() => {});
    }, 150);
    return () => clearTimeout(t);
  }, [msgKey, spoken]); // eslint-disable-line react-hooks/exhaustive-deps
  const fixed = polished && polished.key === msgKey && message.length >= 2 ? polished : null;
  const shownSentence = fixed?.text ?? rawSentence;

  // ---------------------------------------------------------------- layout
  const navItems = useMemo(() => [BACK, ...cats], [cats]);
  const navId = TOP_PAGES.has(page.id) ? page.id : "more"; // category pages live under More words
  const actions: ActionId[] = useMemo(
    () => (completion && !spoken ? ["speak", "complete", "delete", "clear"] : ["speak", "delete", "clear"]),
    [completion, spoken],
  );
  const layout: Layout = useMemo(
    () => ({
      mode: page.id === "smart" ? "smart" : page.id === "keyboard" ? "keys" : "rows",
      actions: actions.length,
      nav: navItems.length,
      navActive: Math.max(1, navItems.findIndex((c) => c.id === navId)),
      rowLens: rowsOf(tiles).map((r) => r.length),
      colLens: Array.from({ length: 4 }, (_, c) => columns[c]?.tiles.length ?? 0),
      keyRows: keyRows.map((r) => r.length),
    }),
    [page.id, actions, navItems, navId, tiles, columns, keyRows],
  );

  useEffect(() => setFocus((f) => fit(f, layout)), [layout]);

  // ---------------------------------------------------------------- navigation
  const goTo = (pg: Page, msg: MessageItem[], opts: { push?: boolean; focus?: Focus } = {}) => {
    const { push = true } = opts;
    if (push && (pg.id !== page.id || pg.index !== page.index)) setHistory((h) => [...h.slice(-20), page]);
    if (pg.id !== page.id && pg.id !== "smart") setTiles([]); // don't flash the old page's tiles
    setPage(pg);
    setFocus(opts.focus ?? pageHome(pg.id));
    load(pg, msg);
  };

  const pulse = (id: string) => {
    setPulseId(id);
    setTimeout(() => setPulseId(null), 450);
  };

  /** Add a word to the message, say it, learn it, and show the Smart Board's next columns. */
  const addWord = (
    w: { label: string; text: string; pos: Pos; emoji: string; picto: boolean },
    focusAfter: Focus | null, // null = stay on this page (Keyboard)
    pulseKey?: string,
  ) => {
    const base = spoken ? [] : message;
    const next = [...base, w];
    setMessage(next);
    setSpoken(false);
    if (pulseKey) pulse(pulseKey);
    if (settings.speakOnSelect) speak(w.text);
    postJSON("/api/select", {
      prev: base[base.length - 1]?.label ?? null,
      prev2: base[base.length - 2]?.label ?? null,
      word: w.label,
    }).catch(() => {});
    if (!focusAfter) return;
    setTimeout(() => {
      setHistory([]);
      goTo(SMART, next, { push: false, focus: focusAfter });
    }, 260);
  };

  const asWord = (t: Tile) => ({
    label: t.label,
    text: t.kind === "phrase" ? t.speak : t.label,
    pos: t.pos,
    emoji: t.emoji,
    picto: t.picto,
  });

  const triggerNeed = (t: Tile) => {
    const n = t.need!;
    pulse(t.id);
    setMessage([{ label: t.label, text: n.say, pos: t.pos, emoji: t.emoji, picto: false }]);
    setSpoken(true);
    postJSON("/api/need", { level: n.level, label: t.label, say: n.say })
      .then((r) => setNotified(!!r.notify))
      .catch(() => {});
    if (n.level === "normal") speak(n.say);
    else setAlert({ level: n.level, label: t.label, say: n.say, t: Date.now() });
  };

  /** A tile on a rows page (Chat, Needs, More words, a category). */
  const chooseRowTile = (t: Tile) => {
    if (t.kind === "more") return goTo({ ...page, index: t.page ?? 0 }, message, { push: false });
    if (t.kind === "category") return goTo({ id: t.target!, index: 0, label: t.label }, message);
    if (t.kind === "need") return triggerNeed(t);
    if (page.id === "chat") {
      // a ready sentence: say it now, stay on Chat
      const base = spoken ? [] : message;
      setMessage([...base, asWord(t)]);
      setSpoken(base.length === 0);
      pulse(t.id);
      speak(t.speak);
      postJSON("/api/spoken", { text: t.speak }).catch(() => {});
      return;
    }
    const col = CATEGORY_COLUMN[page.id] ?? 2;
    addWord(asWord(t), afterColumn(col), t.id);
  };

  /** A tile in a Smart Board column. */
  const chooseColumnTile = (col: number, row: number) => {
    const t = columns[col]?.tiles[row];
    if (!t) return;
    addWord(asWord(t), afterColumn(col), t.id);
  };

  const addTyped = (text: string) => {
    const word = text.trim();
    if (!word) return;
    const known = lexicon.find((e) => e.label.toLowerCase() === word.toLowerCase());
    setTyped("");
    setLexicon((lx) =>
      known ? lx.map((e) => (e === known ? { ...e, n: e.n + 1 } : e)) : [...lx, { label: word, pos: "noun", n: 1 }],
    );
    addWord(
      { label: known?.label ?? word, text: known?.label ?? word, pos: known?.pos ?? "noun", emoji: "", picto: !!known },
      page.id === "keyboard" ? null : { zone: "cols", col: 0 },
    );
  };

  const pressKey = (row: number, col: number) => {
    const k = keyRows[row]?.[col];
    if (!k) return;
    if (k.kind === "letter") setTyped((s) => (s + k.label.toLowerCase()).slice(0, 40));
    else if (k.kind === "suggest") addTyped(typed.replace(/[^ ]*$/, k.label));
    else if (k.kind === "add") addTyped(typed);
    else if (k.kind === "space") setTyped((s) => (s && !s.endsWith(" ") ? s + " " : s));
    else if (k.kind === "backspace") setTyped((s) => s.slice(0, -1));
    else if (k.kind === "clear") setTyped("");
  };

  const doAction = (id: ActionId) => {
    if (id === "speak") {
      if (!message.length) return;
      const text = shownSentence;
      speak(text);
      if (!spoken) postJSON("/api/spoken", { text }).catch(() => {});
      setSpoken(true);
      setHistory([]);
      goTo(SMART, [], { push: false });
    } else if (id === "complete" && completion) {
      setMessage([{ label: completion, text: completion, pos: "social", emoji: "✨", picto: false }]);
      speak(completion);
      postJSON("/api/spoken", { text: completion }).catch(() => {});
      setSpoken(true);
      setCompletion("");
      setHistory([]);
      goTo(SMART, [], { push: false });
    } else if (id === "delete") {
      const next = message.slice(0, -1);
      setMessage(next);
      setSpoken(false);
      setCompletion("");
      if (page.id === "smart") load(SMART, next);
      setFocus({ zone: "actions", index: 1 });
    } else if (id === "clear") {
      setMessage([]);
      setSpoken(false);
      setTyped("");
      setHistory([]);
      goTo(SMART, [], { push: false });
    }
  };

  const pickNav = (i: number) => {
    const item = navItems[i];
    if (!item) return;
    const msg = spoken ? [] : message;
    if (item.id === "back") {
      const prev = history[history.length - 1] ?? (page.id === "smart" ? null : SMART);
      if (!prev) return;
      setHistory((h) => h.slice(0, -1));
      if (prev.id !== page.id && prev.id !== "smart") setTiles([]);
      setPage(prev);
      setFocus({ zone: "nav", index: 0 }); // stay on Back so OK again goes back further
      load(prev, msg);
      return;
    }
    if (item.id === "smart") {
      setHistory([]);
      return goTo(SMART, msg, { push: false });
    }
    goTo({ id: item.id, index: 0 }, msg);
  };

  // ---------------------------------------------------------------- alerts (Needs)
  const closeAlert = () => {
    setAlert(null);
    stopSpeech();
    postJSON("/api/alert/clear", {}).catch(() => {});
  };

  useEffect(() => {
    if (!alert) return;
    let cancelled = false;
    setAlertArmed(false);
    const arm = setTimeout(() => setAlertArmed(true), 3000);
    (async () => {
      const cycles = alert.level === "emergency" ? 3 : 2;
      for (let i = 0; i < cycles && !cancelled; i++) {
        await (alert.level === "emergency" ? siren(1.8) : chime());
        if (cancelled) break;
        await speak(alert.say);
        await speechDone();
        await wait(1500);
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(arm);
      stopSpeech();
    };
  }, [alert?.t]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------- the 5 commands
  const command = (dir: Direction, source: string) => {
    pristineRef.current = false;
    setLastCmd({ dir, n: ++cmdN.current, source });
    if (alert) {
      if (dir === "ok" && alertArmed) closeAlert();
      return; // nothing else moves while an alert is up
    }
    if (dir !== "ok") {
      setFocus((f) => move(f, dir, layout));
      return;
    }
    const now = Date.now();
    if (now - lastOkRef.current < 500) return; // one gaze = one OK
    lastOkRef.current = now;
    const f = focus;
    if (f.zone === "actions") return doAction(actions[f.index]);
    if (f.zone === "nav") return pickNav(f.index);
    if (f.zone === "krows") return layout.keyRows[f.row] ? setFocus({ zone: "keys", row: f.row, col: 0 }) : undefined;
    if (f.zone === "keys") return pressKey(f.row, f.col);
    if (loading) return; // tiles are changing: ignore OK so nothing is chosen by mistake
    if (f.zone === "cols") return layout.colLens[f.col] ? setFocus({ zone: "ctiles", col: f.col, row: 0 }) : undefined;
    if (f.zone === "ctiles") return chooseColumnTile(f.col, f.row);
    if (f.zone === "rows") return layout.rowLens[f.row] ? setFocus({ zone: "tiles", row: f.row, col: 0 }) : undefined;
    const t = tiles[f.row * COLS + f.col];
    if (t) chooseRowTile(t);
  };

  const commandRef = useRef(command);
  commandRef.current = command;

  // ---------------------------------------------------------------- server messages
  const alertRef = useRef(alert);
  alertRef.current = alert;
  const { connected, status, send } = useHub("board", (msg) => {
    if (msg.type === "command") commandRef.current(msg.direction, msg.source);
    else if (msg.type === "alert") {
      if (msg.clear) setAlert(null);
      else if (!alertRef.current) setAlert({ level: msg.level, label: msg.label, say: msg.say, t: msg.t * 1000 });
    } else if (msg.type === "context") {
      setCtx(msg);
      if (msg.version > ctxVersionRef.current) {
        // only refresh tiles if the user hasn't started moving (tiles never jump under the highlight)
        const z = focusRef.current.zone;
        if (pristineRef.current && !loadingRef.current && z !== "tiles" && z !== "ctiles") {
          load(pageRef.current, spokenRef.current ? [] : messageRef.current);
        } else setPendingCtx(true);
      }
    }
  });
  const loadingRef = useRef(loading);
  const focusRef = useRef(focus);
  const pageRef = useRef(page);
  const messageRef = useRef(message);
  const spokenRef = useRef(spoken);
  loadingRef.current = loading;
  focusRef.current = focus;
  pageRef.current = page;
  messageRef.current = message;
  spokenRef.current = spoken;

  useEffect(() => {
    if (connected) send({ type: "profile", profile: settings.profile });
  }, [connected, settings.profile]); // eslint-disable-line react-hooks/exhaustive-deps

  // physical keyboard: arrows + Enter = the five commands; letters type into the on-screen keyboard
  const openKeyboard = () => goTo(KEYBOARD, spoken ? [] : message);
  const typeRef = useRef({ typed, page, addTyped, openKeyboard });
  typeRef.current = { typed, page, addTyped, openKeyboard };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || showSettings) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const T = typeRef.current;
      const onKeyboard = T.page.id === "keyboard" && !alertRef.current;
      if (!alertRef.current && /^[a-zA-Z'?]$/.test(e.key)) {
        typingRef.current = true;
        if (!onKeyboard) T.openKeyboard(); // typing anywhere opens the Keyboard page
        setTyped((s) => (s + e.key.toLowerCase()).slice(0, 40));
        return;
      }
      if (onKeyboard && typingRef.current && T.typed) {
        if (e.key === "Backspace") return setTyped((s) => s.slice(0, -1));
        if (e.key === " ") {
          e.preventDefault();
          return setTyped((s) => (s.endsWith(" ") ? s : s + " "));
        }
        if (e.key === "Enter") {
          e.preventDefault();
          typingRef.current = false;
          return T.addTyped(T.typed);
        }
      }
      const map: Record<string, Direction> = {
        ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "ok", " ": "ok",
      };
      const d = map[e.key];
      if (d) {
        e.preventDefault();
        typingRef.current = false;
        if (!e.repeat) commandRef.current(d, "keyboard");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showSettings]);

  // ---------------------------------------------------------------- microphone
  const listener = useRef<Listener | null>(null);
  const [browserFailed, setBrowserFailed] = useState(false);
  const serverStt = !!status?.stt;
  const serverSttRef = useRef(serverStt);
  serverSttRef.current = serverStt;
  // auto: the server's Whisper (Groq / OpenAI / local) when it has one, otherwise Chrome's own
  const sttMode: "browser" | "server" | "off" | null =
    settings.sttMode === "off" ? "off"
      : settings.sttMode === "server" ? "server"
        : settings.sttMode === "browser" && !browserFailed ? "browser"
          : !status ? null // wait to hear what the server supports
            : serverStt ? "server" : browserFailed ? "off" : "browser";
  useEffect(() => {
    listener.current = new Listener({
      onFinal: (text) => {
        setInterim("");
        setMicError("");
        send({ type: "heard", text });
      },
      onInterim: setInterim,
      onError: setMicError,
      onLevel: (l) => (levelRef.current = l),
      onFallback: () => {
        console.warn("[stt] browser speech recognition failed; switching to server mode");
        setBrowserFailed(true);
        return serverSttRef.current;
      },
    });
    return () => listener.current?.stop();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!started || !sttMode) return;
    setMicError(
      browserFailed && sttMode === "off"
        ? "Chrome speech recognition isn't working here. Add GROQ_API_KEY to server/.env for server listening."
        : "",
    );
    setInterim("");
    listener.current?.start(sttMode);
  }, [started, sttMode]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = () => {
    unlockAudio();
    unlockAlarm();
    setStarted(true);
  };

  // ---------------------------------------------------------------- render
  const last = message.length && !spoken ? message[message.length - 1].text : "";
  const smartSub = last
    ? `After “${last}” · the columns update with every choice`
    : ctx?.topic
      ? `Talking about ${ctx.topic} · Questions → People → Actions → Things`
      : "Build left to right: Questions → People → Actions → Things";
  const rowsTitle =
    page.id === "chat" ? "Chat"
      : page.id === "needs" ? "Needs"
        : page.id === "more" ? "More words"
          : `More words  ›  ${page.label ?? page.id}`;
  const rowsSub =
    page.id === "chat" ? "Your sentences first · everything you Speak is saved here"
      : page.id === "needs" ? "Red tiles sound an alarm, speak for you and alert your caregiver"
        : page.id === "more" ? "Choose a group of words · a word you pick goes back to the Smart Board"
          : page.index > 0 ? `Page ${page.index + 1}` : "Most relevant first";

  return (
    <LayoutGroup>
      <div className="board-app">
        <TopBar
          message={message}
          polished={fixed && fixed.text.replace(/[.?!]$/, "").toLowerCase() !== rawSentence.replace(/[.?!]$/, "").toLowerCase() ? fixed : null}
          spoken={spoken}
          completion={completion}
          actions={actions}
          focus={focus}
          onAction={doAction}
        />
        <NavBar items={navItems} activeId={navId} focus={focus} onPick={pickNav} />
        <ContextStrip
          ctx={ctx}
          interim={interim}
          micOn={started && !!sttMode && sttMode !== "off"}
          micError={micError}
          levelRef={levelRef}
          pending={pendingCtx}
          status={status}
          connected={connected}
          onSettings={() => setShowSettings(true)}
        />
        {page.id === "smart" ? (
          <SmartBoard
            columns={columns}
            loading={loading && columns.length === 0}
            focus={focus}
            pageKey={`smart:${loadN}`}
            pulseId={pulseId}
            subtitle={smartSub}
            onTile={(c, r) => {
              setFocus({ zone: "ctiles", col: c, row: r });
              if (!loading) chooseColumnTile(c, r);
            }}
          />
        ) : page.id === "keyboard" ? (
          <KeyboardPage
            rows={keyRows}
            typed={typed}
            focus={focus}
            subtitle="Spell a word · suggestions appear as you type · Add word puts it in your sentence"
            onKey={(r, c) => {
              setFocus({ zone: "keys", row: r, col: c });
              pressKey(r, c);
            }}
          />
        ) : (
          <Grid
            tiles={tiles}
            loading={loading && tiles.length === 0}
            focus={focus}
            pageKey={`${page.id}:${page.index}:${loadN}`}
            pulseId={pulseId}
            title={rowsTitle}
            subtitle={rowsSub}
            onTileClick={(r, c) => {
              setFocus({ zone: "tiles", row: r, col: c });
              const t = tiles[r * COLS + c];
              if (t && !loading) chooseRowTile(t);
            }}
          />
        )}
        <HintBar focus={focus} lastCmd={lastCmd} />
        {loading && <div className="loading-bar" />}
      </div>

      <AnimatePresence>
        {alert && <AlertOverlay alert={alert} armed={alertArmed} notified={notified} onClose={closeAlert} />}
      </AnimatePresence>

      <AnimatePresence>
        {showSettings && (
          <SettingsDrawer settings={settings} update={update} voices={voices} status={status} onClose={() => setShowSettings(false)} />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {!started && (
          <motion.div className="gate" exit={{ opacity: 0 }} onClick={start}>
            <motion.div className="gate-card" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
              <div className="logo">
                <i /><i /><i /><i />
              </div>
              <h1>AdaptiBoard</h1>
              <p>A communication board you control with your eyes and an EEG headset.</p>
              <button type="button" className="gate-btn">Start</button>
              <p className="gate-note">
                <Volume2 size={14} /> enables the voice · <Mic size={14} /> listens for conversation context
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </LayoutGroup>
  );
}
