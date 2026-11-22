// ──────────────────────────────────────────────────────────────────────
// Research Assistant: web UI
// Vanilla ES module. No framework.
// ──────────────────────────────────────────────────────────────────────

import { openCommandPalette, closeCommandPalette, isCommandPaletteOpen } from "./command-palette.js";

const STORAGE_KEY = "research-assistant:sessions:v2";
const LEGACY_KEY = "research-assistant:conversations";
const VAULT_NAME = "Library"; // Obsidian vault name for "open in Obsidian" links
const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 60; // 60 days
const PLACEHOLDER_EXAMPLES = [
  "Ask about your documents…",
  "What did the evaluation show?",
  "Which design decisions were rejected, and why?",
  "How does the search combine keywords and meaning?",
];

// ── State ─────────────────────────────────────────────────────────────

const state = {
  sessions: {},          // { [id]: { id, title, turns, createdAt, updatedAt, pinned } }
  activeSessionId: null,
  activeTurnId: null,    // which assistant turn's sources are in the rail
  topics: [],             // [{ name, count }]
  selectedLane: null,
  stats: { articles: 0, passages: 0 },
  isStreaming: false,
  abortController: null,
  marked: null,
  railUI: { expandAll: false, expanded: new Set() },
};

// ── DOM refs ──────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

const els = {
  header: $("header"),
  status: $("status"),
  kickerLane: $("kickerLane"),
  emptyState: $("emptyState"),
  emptyTrending: $("emptyTrending"),
  examples: null,
  turns: $("turns"),
  conversationColumn: $("conversationColumn"),
  rail: $("rail"),
  railBody: $("railBody"),
  railCount: $("railCount"),
  railExpandBtn: $("railExpandBtn"),
  input: $("input"),
  composerForm: $("composerForm"),
  sendBtn: $("sendBtn"),
  stopBtn: $("stopBtn"),
  corpusHint: $("corpusHint"),
  newChatBtn: $("newChatBtn"),
  newChatHeroBtn: $("newChatHeroBtn"),
  exportBtn: $("exportBtn"),
  topicButton: null,
  topicLabel: null,
  topicPanel: $("topicPanel"),
  topicSearch: $("topicSearch"),
  topicList: $("topicList"),
  composerLaneBtn: $("composerLaneBtn"),
  composerLaneLabel: $("composerLaneLabel"),
  composerLaneClear: $("composerLaneClear"),
  composerCmdkBtn: $("composerCmdkBtn"),
  navBody: $("navBody"),
  navFooter: $("navFooter"),
  main: document.querySelector(".ra-main"),
  overlay: $("overlay"),
  slideover: $("slideover"),
  slideoverIndex: $("slideoverIndex"),
  slideoverBody: $("slideoverBody"),
  slideoverClose: $("slideoverClose"),
  copyExcerptBtn: $("copyExcerptBtn"),
  openObsidianBtn: $("openObsidianBtn"),
};

let activeSlideoverSource = null;
let citePreviewEl = null;
let citePreviewTimer = null;
let composerFocused = false;
let placeholderIdx = 0;
let placeholderTimer = null;

// ── Util ──────────────────────────────────────────────────────────────

const uid = () => Math.random().toString(36).slice(2, 10);
const pad2 = (n) => String(n).padStart(2, "0");

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function relativeTime(ts) {
  if (!ts) return "";
  const diff = Date.now() - ts;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)}d ago`;
  return new Date(ts).toLocaleDateString();
}

function relativeTimeShort(ts) {
  // For source card "published" - accepts ISO strings too
  if (!ts) return "";
  const t = typeof ts === "number" ? ts : Date.parse(ts);
  if (isNaN(t)) return String(ts);
  const diff = Date.now() - t;
  if (diff < 0) return new Date(t).toLocaleDateString();
  if (diff < 86_400_000) return "today";
  if (diff < 172_800_000) return "yesterday";
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)}d ago`;
  if (diff < 2_592_000_000) return `${Math.floor(diff / 604_800_000)}w ago`;
  return new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function topicHue(name) {
  // Stable hash → hue. Deterministic per-topic color.
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) | 0;
  }
  return Math.abs(h) % 360;
}

async function loadMarked() {
  if (state.marked) return state.marked;
  try {
    const m = await import("https://cdn.jsdelivr.net/npm/marked@12/+esm");
    m.marked.setOptions({ breaks: false, gfm: true });
    state.marked = m.marked;
    return m.marked;
  } catch (e) {
    return null;
  }
}

function renderMarkdown(text) {
  if (state.marked) {
    return state.marked.parse(text || "");
  }
  return `<p>${escapeHTML(text).replace(/\n\n+/g, "</p><p>").replace(/\n/g, "<br>")}</p>`;
}

let streamingRenderFrame = null;

function scheduleStreamingRender(turnId) {
  if (streamingRenderFrame) return;
  streamingRenderFrame = requestAnimationFrame(() => {
    streamingRenderFrame = null;
    patchStreamingTurn(turnId);
  });
}

function streamingWaitMessage(turn) {
  if (turn.sources?.length) {
    return `Synthesizing from ${turn.sources.length} source${turn.sources.length === 1 ? "" : "s"}…`;
  }
  return "Researching…";
}

function updateStreamingBody(body, turn) {
  body.classList.add("is-streaming");

  let skeleton = body.querySelector(".ra-stream-skeleton");
  let waitEl = body.querySelector(".ra-stream-wait");
  let streamEl = body.querySelector(".ra-stream-text");

  if (!turn.content) {
    if (!waitEl) {
      body.innerHTML = "";
      if (turn.sources?.length) {
        skeleton = document.createElement("div");
        skeleton.className = "ra-stream-skeleton";
        skeleton.setAttribute("aria-hidden", "true");
        skeleton.innerHTML = `
          <div class="ra-skeleton-line"></div>
          <div class="ra-skeleton-line is-short"></div>
          <div class="ra-skeleton-line is-medium"></div>`;
        body.appendChild(skeleton);
      }
      waitEl = document.createElement("p");
      waitEl.className = "ra-stream-wait";
      body.appendChild(waitEl);
    }
    waitEl.textContent = streamingWaitMessage(turn);
    streamEl?.remove();
    return;
  }

  skeleton?.remove();
  waitEl?.remove();
  if (!streamEl) {
    body.innerHTML = "";
    streamEl = document.createElement("div");
    streamEl.className = "ra-stream-text";
    body.appendChild(streamEl);
  }
  streamEl.textContent = turn.content;
}

function patchStreamingTurn(turnId) {
  const turn = activeTurns().find((t) => t.id === turnId);
  if (!turn?.streaming) return;

  const wrap = els.turns.querySelector(`[data-turn-id="${CSS.escape(turnId)}"]`);
  if (!wrap) {
    renderConversation();
    return;
  }

  const body = wrap.querySelector(".ra-turn-body");
  if (body) updateStreamingBody(body, turn);

  const meta = wrap.querySelector(".ra-turn-meta");
  if (meta) {
    const time = formatTime(turn.createdAt);
    const parts = [];
    if (time) parts.push(time);
    if (turn.sources?.length) parts.push(`${turn.sources.length} sources`);
    if (turn.content) parts.push("writing");
    else if (turn.sources?.length) parts.push("synthesizing");
    meta.innerHTML = parts.map((p, i) => (i === 0 ? p : `<span class="ra-turn-sep">·</span>${p}`)).join("");
  }

  if (isNearBottom(els.conversationColumn)) {
    requestAnimationFrame(() => {
      els.conversationColumn.scrollTop = els.conversationColumn.scrollHeight;
    });
  }
}

function isNearBottom(el, threshold = 96) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function injectCitationLinks(html) {
  return html.replace(/\[(\d+)\]/g, (_m, n) => `<a class="ra-cite" data-cite="${n}" role="button" tabindex="0" aria-label="Jump to source ${n}">${n}</a>`);
}

function showToast(text, ms = 1500) {
  const t = document.createElement("div");
  t.className = "ra-toast";
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

// ── Active session helper ─────────────────────────────────────────────

function activeSession() {
  if (!state.activeSessionId) return null;
  return state.sessions[state.activeSessionId] || null;
}

function activeTurns() {
  return activeSession()?.turns || [];
}

// ── Stats / topics (boot) ──────────────────────────────────────────────

async function fetchWithRetry(path, attempts = 8, delayMs = 500) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      const r = await fetch(path);
      if (!r.ok) throw new Error(`${path} ${r.status}`);
      return r;
    } catch (err) {
      lastErr = err;
      if (i < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
  throw lastErr;
}

async function fetchStats() {
  try {
    const r = await fetchWithRetry("/api/stats");
    const d = await r.json();
    state.stats = { articles: d.articles, passages: d.chunks };
    setStatus("ok");
    updateCorpusHint();
  } catch {
    setStatus("err");
    els.corpusHint.textContent = "Backend unreachable";
  }
}

async function fetchLanes() {
  try {
    const r = await fetchWithRetry("/api/topics");
    state.topics = await r.json();
    renderLaneList();
    renderTrendingLanes();
  } catch {
    state.topics = [];
    renderLaneList();
    renderTrendingLanes();
  }
}

function setStatus(level) {
  els.status.classList.remove("is-warn", "is-err");
  if (level === "warn") els.status.classList.add("is-warn");
  if (level === "err") els.status.classList.add("is-err");
  els.status.textContent = level === "err" ? "Offline" : level === "warn" ? "Degraded" : "Live";
}

function updateCorpusHint() {
  const { articles, passages } = state.stats;
  if (!articles && !passages) {
    els.corpusHint.textContent = "Corpus is empty - run main.py ingest · Enter to send · Shift+Enter for new line";
    return;
  }
  els.corpusHint.textContent = `Grounded · ${articles} documents · ${passages} passages · Enter to send · Shift+Enter for new line`;
}

function updateNavFooter() {
  if (!els.navFooter) return;
  const sessions = Object.values(state.sessions).filter((s) => s.turns.length > 0);
  if (sessions.length === 0) {
    els.navFooter.textContent = "Live";
  } else {
    els.navFooter.textContent = `${sessions.length} session${sessions.length === 1 ? "" : "s"}`;
  }
}

function updateRailVisibility() {
  const isLanding = activeTurns().length === 0;
  els.rail.classList.toggle("is-collapsed", isLanding);
  if (els.main) els.main.classList.toggle("is-landing", isLanding);
}

function updateComposerChrome() {
  const hasTurns = activeTurns().length > 0;
  const showTools = hasTurns || composerFocused;
  if (els.composerForm) {
    els.composerForm.classList.toggle("is-minimal", !showTools);
  }
}

function startPlaceholderRotation() {
  if (placeholderTimer) return;
  placeholderTimer = setInterval(() => {
    if (activeTurns().length > 0 || els.input.value.trim() || composerFocused || state.isStreaming) return;
    placeholderIdx = (placeholderIdx + 1) % PLACEHOLDER_EXAMPLES.length;
    els.input.placeholder = PLACEHOLDER_EXAMPLES[placeholderIdx];
  }, 6000);
}

function renderTrendingLanes() {
  els.emptyTrending.innerHTML = "";
  if (!state.topics.length) return;
  const top = [...state.topics].sort((a, b) => b.count - a.count).slice(0, 6);
  for (const topic of top) {
    const chip = document.createElement("button");
    chip.className = "ra-trending-chip";
    chip.type = "button";
    chip.innerHTML = `${escapeHTML(topic.name)} <span class="ra-trending-count">${topic.count}</span>`;
    chip.addEventListener("click", () => {
      selectLane(topic.name);
      els.input.focus();
    });
    els.emptyTrending.appendChild(chip);
  }
}

// ── Topic dropdown ─────────────────────────────────────────────────────

function renderLaneList(filter = "") {
  const f = filter.trim().toLowerCase();
  els.topicList.innerHTML = "";

  const allLi = document.createElement("li");
  allLi.textContent = "All topics";
  if (!state.selectedLane) allLi.classList.add("is-active");
  allLi.addEventListener("click", () => selectLane(null));
  els.topicList.appendChild(allLi);

  if (state.topics.length === 0) {
    const empty = document.createElement("li");
    empty.className = "ra-topic-empty";
    empty.textContent = "No topics yet. Re-run ingest after Haiku classification.";
    els.topicList.appendChild(empty);
    return;
  }

  const filtered = state.topics.filter((l) => !f || l.name.toLowerCase().includes(f));

  if (filtered.length === 0) {
    const empty = document.createElement("li");
    empty.className = "ra-topic-empty";
    empty.textContent = "No topics match.";
    els.topicList.appendChild(empty);
    return;
  }

  for (const topic of filtered) {
    const li = document.createElement("li");
    if (state.selectedLane === topic.name) li.classList.add("is-active");
    li.innerHTML = `<span>${escapeHTML(topic.name)}</span><span class="ra-topic-count">${topic.count}</span>`;
    li.addEventListener("click", () => selectLane(topic.name));
    els.topicList.appendChild(li);
  }
}

function updateLaneUI() {
  const label = state.selectedLane || "All topics";
  if (els.composerLaneLabel) {
    els.composerLaneLabel.textContent = state.selectedLane || "All topics";
    els.composerLaneLabel.classList.toggle("is-active", !!state.selectedLane);
  }
  if (els.composerLaneClear) {
    els.composerLaneClear.hidden = !state.selectedLane;
  }
  if (els.composerLaneBtn) {
    els.composerLaneBtn.classList.toggle("is-topic-chip", !!state.selectedLane);
  }
  if (els.kickerLane) els.kickerLane.textContent = label;
}

function selectLane(name) {
  state.selectedLane = name;
  updateLaneUI();
  renderLaneList(els.topicSearch.value);
  closeLanePanel();

  const url = new URL(window.location.href);
  if (name) url.searchParams.set("topic", name);
  else url.searchParams.delete("topic");
  window.history.replaceState({}, "", url.toString());
}

function applyURLLane() {
  const param = new URL(window.location.href).searchParams.get("topic");
  if (!param) return;
  state.selectedLane = param;
  updateLaneUI();
  setTimeout(() => {
    const exists = state.topics.some((l) => l.name === param);
    if (!exists) {
      state.selectedLane = null;
      updateLaneUI();
      const url = new URL(window.location.href);
      url.searchParams.delete("topic");
      window.history.replaceState({}, "", url.toString());
      renderLaneList();
    }
  }, 300);
}

function openLanePanel() {
  els.topicPanel.hidden = false;
  if (els.composerLaneBtn) els.composerLaneBtn.setAttribute("aria-expanded", "true");
  els.topicSearch.value = "";
  renderLaneList();
  els.topicSearch.focus();
}
function closeLanePanel() {
  els.topicPanel.hidden = true;
  if (els.composerLaneBtn) els.composerLaneBtn.setAttribute("aria-expanded", "false");
}

// ── Sessions (multi-session localStorage) ─────────────────────────────

function newSessionObject() {
  const id = uid();
  return {
    id,
    title: "New chat",
    turns: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
    pinned: false,
  };
}

function saveSessions() {
  try {
    // Prune sessions older than TTL (unless pinned)
    const cutoff = Date.now() - SESSION_TTL_MS;
    for (const id of Object.keys(state.sessions)) {
      const s = state.sessions[id];
      if (!s.pinned && s.updatedAt < cutoff && id !== state.activeSessionId) {
        delete state.sessions[id];
      }
    }
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ sessions: state.sessions, activeSessionId: state.activeSessionId })
    );
  } catch (e) {
    const turn = activeTurns().find((t) => t.role === "assistant");
    if (turn) {
      turn.error = "Conversation history is full. Start a new chat to keep asking.";
      renderConversation();
    }
  }
}

function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed?.sessions && typeof parsed.sessions === "object") {
        state.sessions = parsed.sessions;
        state.activeSessionId = parsed.activeSessionId || Object.keys(parsed.sessions)[0] || null;
        if (!state.activeSessionId) ensureActiveSession();
        return;
      }
    }
    // Legacy migration
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      const turns = JSON.parse(legacy);
      if (Array.isArray(turns) && turns.length) {
        const session = newSessionObject();
        session.turns = turns.map((t) => ({ ...t, createdAt: t.createdAt || Date.now() }));
        session.title = autoTitleFromTurns(session.turns);
        state.sessions[session.id] = session;
        state.activeSessionId = session.id;
      }
    }
  } catch {
    showOneShotNotice("Previous conversation couldn't be restored.");
  }
  ensureActiveSession();
}

function ensureActiveSession() {
  if (state.activeSessionId && state.sessions[state.activeSessionId]) return;
  const s = newSessionObject();
  state.sessions[s.id] = s;
  state.activeSessionId = s.id;
}

function autoTitleFromTurns(turns) {
  const firstUser = turns.find((t) => t.role === "user");
  if (!firstUser) return "New chat";
  let text = String(firstUser.content || "").trim().replace(/\s+/g, " ");
  text = text.replace(/\?+$/, "").trim();
  if (text) text = text.charAt(0).toUpperCase() + text.slice(1);
  if (firstUser.topic) text = `${firstUser.topic} - ${text}`;
  return text.length > 52 ? `${text.slice(0, 52)}…` : text;
}

function bumpSession() {
  const s = activeSession();
  if (!s) return;
  s.updatedAt = Date.now();
  if (s.title === "New chat") {
    s.title = autoTitleFromTurns(s.turns);
  }
  // Re-set active turn to last assistant with sources
  const lastAssistant = [...s.turns].reverse().find((t) => t.role === "assistant" && t.sources?.length);
  if (lastAssistant) state.activeTurnId = lastAssistant.id;
}

function showOneShotNotice(text) {
  setTimeout(() => {
    const banner = document.createElement("div");
    banner.className = "ra-notice is-muted";
    banner.style.marginBottom = "16px";
    banner.textContent = text;
    els.emptyState.prepend(banner);
  }, 0);
}

// ── Nav rendering ─────────────────────────────────────────────────────

function renderNav() {
  els.navBody.innerHTML = "";

  const sessions = Object.values(state.sessions)
    .filter((s) => s.turns.length > 0 || s.id === state.activeSessionId)
    .sort((a, b) => b.updatedAt - a.updatedAt);

  if (sessions.length === 0) {
    const hint = document.createElement("div");
    hint.className = "ra-nav-section";
    hint.textContent = "No sessions yet";
    els.navBody.appendChild(hint);
    return;
  }

  // Group by recency
  const now = Date.now();
  const groups = { Pinned: [], Today: [], "This week": [], Earlier: [] };
  for (const s of sessions) {
    if (s.pinned) groups.Pinned.push(s);
    else if (now - s.updatedAt < 86_400_000) groups.Today.push(s);
    else if (now - s.updatedAt < 604_800_000) groups["This week"].push(s);
    else groups.Earlier.push(s);
  }

  for (const [name, items] of Object.entries(groups)) {
    if (!items.length) continue;
    const header = document.createElement("div");
    header.className = "ra-nav-section";
    header.textContent = name;
    els.navBody.appendChild(header);
    for (const s of items) {
      const btn = document.createElement("button");
      btn.className = "ra-session";
      btn.type = "button";
      if (s.id === state.activeSessionId) btn.classList.add("is-active");
      const titleEl = document.createElement("span");
      titleEl.textContent = s.title || "New chat";
      const timeEl = document.createElement("span");
      timeEl.className = "ra-session-time";
      timeEl.textContent = relativeTime(s.updatedAt);
      btn.appendChild(titleEl);
      btn.appendChild(timeEl);
      btn.addEventListener("click", () => switchSession(s.id));
      els.navBody.appendChild(btn);
    }
  }
}

function switchSession(id) {
  if (!state.sessions[id]) return;
  if (state.isStreaming) {
    showToast("Wait for response to finish");
    return;
  }
  state.activeSessionId = id;
  const s = state.sessions[id];
  const lastAssistant = [...s.turns].reverse().find((t) => t.role === "assistant" && t.sources?.length);
  state.activeTurnId = lastAssistant ? lastAssistant.id : null;
  resetRailUI();
  saveSessions();
  render();
  els.input.focus();
}

// ── Rendering ─────────────────────────────────────────────────────────

function appendStoppedBanner(wrap, turn) {
  const body = wrap.querySelector(".ra-turn-body");
  if (body) body.classList.add("is-partial");

  const banner = document.createElement("div");
  banner.className = "ra-status-banner is-stopped";
  banner.setAttribute("role", "status");

  const msg = document.createElement("p");
  msg.className = "ra-status-banner-text";
  msg.textContent = turn.content
    ? "Generation stopped - partial answer below"
    : "Generation stopped before an answer was written";

  const actions = document.createElement("div");
  actions.className = "ra-status-banner-actions";
  actions.appendChild(makeActionButton("Regenerate", () => regenerateTurn(turn)));
  if (turn.content) {
    actions.appendChild(makeActionButton("Continue", () => continueTurn(turn)));
    actions.appendChild(makeActionButton("Copy", () => copyTurnContent(turn)));
  }

  banner.appendChild(msg);
  banner.appendChild(actions);
  wrap.appendChild(banner);
}

function render() {
  els.emptyState.hidden = activeTurns().length > 0;
  updateRailVisibility();
  updateComposerChrome();
  renderConversation();
  renderRail();
  renderNav();
  updateNavFooter();
}

function renderConversation() {
  els.turns.innerHTML = "";

  for (const turn of activeTurns()) {
    const wrap = document.createElement("article");
    wrap.className = `ra-turn ra-turn-${turn.role}`;
    wrap.dataset.turnId = turn.id;
    if (turn.id === state.activeTurnId) wrap.classList.add("is-active");
    else if (turn.role === "assistant") wrap.classList.add("is-inactive");

    // Head row: avatar + name + meta
    const head = document.createElement("div");
    head.className = "ra-turn-head";

    const avatar = document.createElement("span");
    avatar.className = `ra-avatar ra-avatar-${turn.role}`;
    avatar.textContent = turn.role === "user" ? "·" : "RA";
    avatar.setAttribute("aria-hidden", "true");
    head.appendChild(avatar);

    const name = document.createElement("span");
    name.className = "ra-turn-name";
    name.textContent = turn.role === "user" ? "YOU" : "ASSISTANT";
    head.appendChild(name);

    const meta = document.createElement("span");
    meta.className = "ra-turn-meta";
    const time = formatTime(turn.createdAt);
    const parts = [];
    if (time) parts.push(time);
    if (turn.role === "user" && turn.topic) parts.push(`${turn.topic} topic`);
    if (turn.role === "assistant" && turn.sources?.length) parts.push(`${turn.sources.length} sources`);
    meta.innerHTML = parts.map((p, i) => i === 0 ? p : `<span class="ra-turn-sep">·</span>${p}`).join("");
    head.appendChild(meta);

    wrap.appendChild(head);

    // Body
    const body = document.createElement("div");
    body.className = "ra-turn-body";

    if (turn.role === "user") {
      body.textContent = turn.content;
    } else if (turn.error) {
      const notice = document.createElement("div");
      notice.className = "ra-notice";
      notice.textContent = turn.error;
      body.appendChild(notice);
    } else if (turn.streaming) {
      updateStreamingBody(body, turn);
    } else {
      if (turn.stopped) body.classList.add("is-partial");
      body.innerHTML = injectCitationLinks(renderMarkdown(turn.content));
    }
    wrap.appendChild(body);

    if (turn.stopped) {
      appendStoppedBanner(wrap, turn);
    }

    // Action row (assistant only, not while streaming, not stopped banner duplicate)
    if (turn.role === "assistant" && !turn.streaming && !turn.error && !turn.stopped && turn.content) {
      const actions = document.createElement("div");
      actions.className = "ra-actions";
      actions.appendChild(makeActionButton("Copy", () => copyTurnContent(turn)));
      actions.appendChild(makeActionButton("Cite", () => copyTurnAsCitation(turn)));
      actions.appendChild(makeActionButton("Regenerate", () => regenerateTurn(turn), turn.streaming || state.isStreaming));
      wrap.appendChild(actions);
    }

    // Mobile rail toggle
    if (turn.role === "assistant" && turn.sources?.length) {
      const toggle = document.createElement("button");
      toggle.className = "ra-mobile-rail-toggle";
      toggle.type = "button";
      toggle.textContent = `View ${turn.sources.length} sources →`;
      toggle.addEventListener("click", () => {
        state.activeTurnId = turn.id;
        renderRail();
        els.rail.classList.add("is-mobile-open");
        renderConversation(); // re-mark active
      });
      wrap.appendChild(toggle);
    }

    // Click anywhere on assistant turn → activate its sources in the rail
    if (turn.role === "assistant" && turn.sources?.length) {
      wrap.addEventListener("click", (e) => {
        if (e.target.closest(".ra-cite")) return;
        if (e.target.closest(".ra-action")) return;
        if (e.target.closest(".ra-status-banner")) return;
        state.activeTurnId = turn.id;
        state.railUI.expanded.clear();
        state.railUI.expandAll = false;
        renderRail();
        renderConversation();
      });
    }

    els.turns.appendChild(wrap);
  }

  // Scroll to bottom
  requestAnimationFrame(() => {
    els.conversationColumn.scrollTop = els.conversationColumn.scrollHeight;
  });

  // Bind citation marker events
  els.turns.querySelectorAll(".ra-cite").forEach((cite) => {
    cite.addEventListener("click", (e) => {
      e.stopPropagation();
      const n = parseInt(cite.dataset.cite, 10);
      jumpToSource(n);
    });
    cite.addEventListener("mouseenter", (e) => scheduleCitePreview(parseInt(cite.dataset.cite, 10), cite));
    cite.addEventListener("mouseleave", hideCitePreview);
    cite.addEventListener("focus", (e) => scheduleCitePreview(parseInt(cite.dataset.cite, 10), cite));
    cite.addEventListener("blur", hideCitePreview);
  });
}

function makeActionButton(label, onClick, disabled = false) {
  const btn = document.createElement("button");
  btn.className = "ra-action";
  btn.type = "button";
  btn.textContent = label;
  if (disabled) btn.disabled = true;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick();
  });
  return btn;
}

async function copyTurnContent(turn) {
  try {
    // Strip citation markers for clean copy
    const clean = (turn.content || "").replace(/\[\d+\]/g, "");
    await navigator.clipboard.writeText(clean.trim());
    showToast("Copied");
  } catch {
    showToast("Copy failed");
  }
}

async function copyTurnAsCitation(turn) {
  try {
    const lines = [(turn.content || "").trim(), ""];
    if (turn.sources?.length) {
      lines.push("Sources:");
      turn.sources.forEach((src, i) => {
        const meta = src.metadata || {};
        const title = meta.title || (meta.source || "Untitled").replace(/\.md$/, "");
        const topic = meta.topics || "";
        lines.push(`[${pad2(i + 1)}] ${title}${topic ? ` - ${topic}` : ""}`);
      });
    }
    await navigator.clipboard.writeText(lines.join("\n"));
    showToast("Copied with sources");
  } catch {
    showToast("Copy failed");
  }
}

function continueTurn(turn) {
  if (state.isStreaming) {
    showToast("Wait for response to finish");
    return;
  }
  const turns = activeTurns();
  const idx = turns.findIndex((t) => t.id === turn.id);
  if (idx < 1) return;
  const userTurn = turns[idx - 1];
  if (!userTurn || userTurn.role !== "user") return;
  const session = activeSession();
  session.turns = turns.slice(0, idx);
  state.activeTurnId = null;
  ask(userTurn.content, { continueFrom: turn.content || "" });
}

function regenerateTurn(turn) {
  if (state.isStreaming) {
    showToast("Wait for response to finish");
    return;
  }
  const turns = activeTurns();
  const idx = turns.findIndex((t) => t.id === turn.id);
  if (idx < 1) return;
  const userTurn = turns[idx - 1];
  if (!userTurn || userTurn.role !== "user") return;
  // Drop this assistant turn and the user turn (ask() will re-add them)
  const session = activeSession();
  session.turns = turns.slice(0, idx - 1);
  state.activeTurnId = null;
  ask(userTurn.content);
}

function resetRailUI() {
  state.railUI.expandAll = false;
  state.railUI.expanded.clear();
}

function sourceTitle(src) {
  const meta = src.metadata || {};
  return meta.title || (meta.source || "Untitled").replace(/\.md$/, "");
}

function groupSourcesByDocument(sources) {
  const groups = [];
  const map = new Map();
  sources.forEach((src, i) => {
    const meta = src.metadata || {};
    const key = meta.source || meta.title || `idx-${i}`;
    if (!map.has(key)) {
      const g = { key, title: sourceTitle(src), items: [] };
      map.set(key, g);
      groups.push(g);
    }
    map.get(key).items.push({ src, index: i + 1 });
  });
  return groups;
}

function topicsForCard(topicsStr) {
  let topics = (topicsStr || "").split(",").map((l) => l.trim()).filter(Boolean);
  if (state.selectedLane) topics = topics.filter((l) => l !== state.selectedLane);
  return topics;
}

function buildLanePillsHtml(topics) {
  if (!topics.length) return "";
  const max = 3;
  const visible = topics.slice(0, max);
  const overflow = topics.length - max;
  let html = visible.map((l) => {
    const hue = topicHue(l);
    return `<span class="ra-card-topic" style="border-color:hsla(${hue},65%,55%,0.45);background:hsla(${hue},65%,45%,0.10);color:hsl(${hue},45%,80%)">${escapeHTML(l)}</span>`;
  }).join("");
  if (overflow > 0) html += `<span class="ra-card-topic ra-card-topic-more">+${overflow}</span>`;
  return html;
}

function isSourceExpanded(index) {
  return state.railUI.expandAll || state.railUI.expanded.has(index);
}

function toggleSourceExpanded(index) {
  if (state.railUI.expandAll) {
    state.railUI.expandAll = false;
    const turn = activeTurns().find((t) => t.id === state.activeTurnId);
    turn?.sources?.forEach((_, i) => {
      if (i + 1 !== index) state.railUI.expanded.add(i + 1);
    });
  } else if (state.railUI.expanded.has(index)) {
    state.railUI.expanded.delete(index);
  } else {
    state.railUI.expanded.add(index);
  }
  renderRail();
}

function updateRailExpandBtn() {
  if (!els.railExpandBtn) return;
  const turn = activeTurns().find((t) => t.id === state.activeTurnId);
  els.railExpandBtn.hidden = !turn?.sources?.length;
  els.railExpandBtn.textContent = state.railUI.expandAll ? "Collapse all" : "Expand all";
}

function similarityLabel(src) {
  if (src.distance == null) return "";
  return `${Math.max(0, Math.min(100, Math.round((1 - src.distance) * 100)))}%`;
}

function buildSourceCard(src, index, turn, { inGroup = false } = {}) {
  const expanded = isSourceExpanded(index);
  const card = document.createElement("article");
  card.className = `ra-card${expanded ? " is-expanded" : " is-collapsed"}${inGroup ? " is-nested" : ""}`;
  card.dataset.sourceIdx = String(index);

  const meta = src.metadata || {};
  const title = sourceTitle(src);
  const topics = topicsForCard(meta.topics || "");
  const section = meta.section || "";
  const confidence = (meta.confidence || "").toLowerCase();
  const sourceType = meta.source_type || "";
  const published = meta.published || "";
  const sim = similarityLabel(src);

  const confClass = confidence === "high" ? "is-high" : confidence === "medium" || confidence === "med" ? "is-med" : confidence === "low" ? "is-low" : "";
  const confLabel = confidence ? confidence.toUpperCase() : "";
  const topicsHtml = buildLanePillsHtml(topics);
  const footLeft = [sourceType, section].filter(Boolean).map(escapeHTML);
  const footLeftHtml = footLeft.map((p, idx) => (idx === 0 ? p : `<span class="ra-card-foot-sep">·</span>${p}`)).join("");
  const dateStr = published ? relativeTimeShort(published) : "";
  const cardTitle = inGroup && section ? section : title;

  card.innerHTML = `
    <div class="ra-card-top">
      <span class="ra-card-num">${pad2(index)}</span>
      <span class="ra-card-top-meta">
        ${sim ? `<span class="ra-card-sim">${sim}</span>` : ""}
        ${confLabel ? `<span class="ra-card-confidence ${confClass}">${confLabel}</span>` : ""}
      </span>
    </div>
    <div class="ra-card-rule"></div>
    <div class="ra-card-title">${escapeHTML(cardTitle)}</div>
    ${!inGroup && section && section !== cardTitle ? `<div class="ra-card-section">${escapeHTML(section)}</div>` : ""}
    ${topicsHtml ? `<div class="ra-card-topics">${topicsHtml}</div>` : ""}
    <div class="ra-card-excerpt">${escapeHTML(src.text || "")}</div>
    <div class="ra-card-foot">
      <span class="ra-card-foot-left">${footLeftHtml}${dateStr ? `${footLeft.length ? '<span class="ra-card-foot-sep">·</span>' : ""}${dateStr}` : ""}</span>
      <span class="ra-card-foot-cta">View →</span>
    </div>
  `;

  card.querySelector(".ra-card-foot-cta")?.addEventListener("click", (e) => {
    e.stopPropagation();
    openSlideover(src, index, turn.sources.length);
  });
  card.addEventListener("click", (e) => {
    if (e.target.closest(".ra-card-foot-cta")) return;
    toggleSourceExpanded(index);
  });

  return card;
}

function renderSourceGroup(group, turn) {
  if (group.items.length === 1) {
    return buildSourceCard(group.items[0].src, group.items[0].index, turn);
  }

  const wrap = document.createElement("article");
  const groupExpanded = group.items.some((it) => isSourceExpanded(it.index));
  wrap.className = `ra-card-group${groupExpanded ? " is-expanded" : ""}`;

  const nums = group.items.map((it) => pad2(it.index)).join(", ");
  const head = document.createElement("button");
  head.type = "button";
  head.className = "ra-card-group-head";
  head.innerHTML = `
    <span class="ra-card-group-title">${escapeHTML(group.title)}</span>
    <span class="ra-card-group-meta">${group.items.length} passages · ${nums}</span>
  `;
  head.addEventListener("click", () => {
    const expandedNow = group.items.every((it) => isSourceExpanded(it.index));
    if (expandedNow && !state.railUI.expandAll) {
      group.items.forEach((it) => state.railUI.expanded.delete(it.index));
    } else {
      group.items.forEach((it) => state.railUI.expanded.add(it.index));
    }
    state.railUI.expandAll = false;
    renderRail();
  });

  const body = document.createElement("div");
  body.className = "ra-card-group-body";
  group.items.forEach(({ src, index }) => {
    body.appendChild(buildSourceCard(src, index, turn, { inGroup: true }));
  });

  wrap.appendChild(head);
  wrap.appendChild(body);
  return wrap;
}

function renderRail() {
  const turn = activeTurns().find((t) => t.id === state.activeTurnId);
  els.railBody.innerHTML = "";
  updateRailExpandBtn();

  if (!turn || !turn.sources?.length) {
    els.railCount.textContent = "";
    const hint = document.createElement("div");
    hint.className = "ra-rail-hint";
    hint.textContent = "Citations for the current answer appear here.";
    els.railBody.appendChild(hint);
    return;
  }

  els.railCount.textContent = `· ${turn.sources.length}`;

  const groups = groupSourcesByDocument(turn.sources);
  groups.forEach((group, gi) => {
    const el = renderSourceGroup(group, turn);
    el.style.animationDelay = `${gi * 40}ms`;
    els.railBody.appendChild(el);
  });
}

function ensureSourceExpanded(n) {
  state.railUI.expanded.add(n);
  renderRail();
}

function jumpToSource(n) {
  const turn = activeTurns().find((t) => t.id === state.activeTurnId);
  if (!turn || !turn.sources || n < 1 || n > turn.sources.length) return;

  ensureSourceExpanded(n);

  const card = els.railBody.querySelector(`[data-source-idx="${n}"]`);
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  card.classList.remove("is-flash");
  void card.offsetWidth;
  card.classList.add("is-flash");
  setTimeout(() => card.classList.remove("is-flash"), 900);
}

// ── Citation hover preview ────────────────────────────────────────────

function scheduleCitePreview(n, anchorEl) {
  clearTimeout(citePreviewTimer);
  citePreviewTimer = setTimeout(() => showCitePreview(n, anchorEl), 220);
}

function showCitePreview(n, anchorEl) {
  hideCitePreview();
  const turn = activeTurns().find((t) => t.id === state.activeTurnId);
  if (!turn || !turn.sources || n < 1 || n > turn.sources.length) return;
  const src = turn.sources[n - 1];
  const meta = src.metadata || {};
  const title = meta.title || (meta.source || "Untitled").replace(/\.md$/, "");

  const el = document.createElement("div");
  el.className = "ra-cite-preview";
  el.innerHTML = `
    <div class="ra-cite-preview-num">SOURCE ${pad2(n)}</div>
    <div class="ra-cite-preview-title">${escapeHTML(title)}</div>
    <div class="ra-cite-preview-excerpt">${escapeHTML(src.text || "")}</div>
  `;
  document.body.appendChild(el);
  citePreviewEl = el;

  const r = anchorEl.getBoundingClientRect();
  const pw = 320;
  const ph = el.offsetHeight;
  let left = r.left + r.width / 2 - pw / 2;
  let top = r.top - ph - 12;
  if (top < 8) top = r.bottom + 12;
  left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
}

function hideCitePreview() {
  clearTimeout(citePreviewTimer);
  if (citePreviewEl) {
    citePreviewEl.remove();
    citePreviewEl = null;
  }
}

// ── Slide-over ────────────────────────────────────────────────────────

function openSlideover(source, idx, total) {
  activeSlideoverSource = source;
  els.slideoverIndex.textContent = `Source ${pad2(idx)} of ${pad2(total)}`;

  const meta = source.metadata || {};
  const title = meta.title || (meta.source || "Untitled").replace(/\.md$/, "");
  const section = meta.section || "";

  const skip = new Set(["title", "section"]);
  const dlRows = Object.entries(meta)
    .filter(([k, v]) => !skip.has(k) && v !== "" && v != null)
    .map(([k, v]) => `<dt>${escapeHTML(k)}</dt><dd>${escapeHTML(String(v))}</dd>`)
    .join("");

  els.slideoverBody.innerHTML = `
    <div class="ra-slideover-title">${escapeHTML(title)}</div>
    ${section ? `<div class="ra-slideover-meta">${escapeHTML(section)}</div>` : ""}
    ${dlRows ? `<dl class="ra-frontmatter">${dlRows}</dl>` : ""}
    <div class="ra-excerpt-full">${escapeHTML(source.text || "")}</div>
  `;

  els.overlay.hidden = false;
  els.slideover.hidden = false;
  els.slideover.classList.add("is-entering");
  requestAnimationFrame(() => {
    els.slideover.classList.remove("is-entering");
  });
}

function closeSlideover() {
  els.slideover.classList.add("is-entering");
  setTimeout(() => {
    els.slideover.hidden = true;
    els.overlay.hidden = true;
    els.slideover.classList.remove("is-entering");
    activeSlideoverSource = null;
  }, 320);
}

// ── Ask (SSE) ─────────────────────────────────────────────────────────

async function ask(question, opts = {}) {
  if (!question.trim() || state.isStreaming) return;
  ensureActiveSession();
  const session = activeSession();

  let userTurn;
  if (opts.continueFrom != null) {
    userTurn = session.turns[session.turns.length - 1];
    if (!userTurn || userTurn.role !== "user") return;
  } else {
    userTurn = {
      id: uid(),
      role: "user",
      content: question.trim(),
      createdAt: Date.now(),
      topic: state.selectedLane || null,
    };
    session.turns.push(userTurn);
  }

  const apiQuestion = opts.continueFrom
    ? `${userTurn.content}\n\nContinue your previous answer without repeating what you already wrote. You had written:\n\n${opts.continueFrom}\n\nPick up exactly where you stopped.`
    : userTurn.content;

  const asstTurn = {
    id: uid(),
    role: "assistant",
    content: "",
    sources: [],
    streaming: true,
    createdAt: Date.now(),
  };
  session.turns.push(asstTurn);
  state.activeTurnId = asstTurn.id;
  resetRailUI();
  state.isStreaming = true;
  toggleSendStop(true);
  els.input.disabled = true;
  render();

  const ctrl = new AbortController();
  state.abortController = ctrl;

  const history = session.turns.slice(0, -1)
    .filter((t) => t.role === "user" || (t.role === "assistant" && t.content && !t.error))
    .slice(-20)
    .map((t) => ({ role: t.role, content: t.content }));
  history.pop();

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: apiQuestion,
        history,
        topic: state.selectedLane || null,
      }),
      signal: ctrl.signal,
    });

    if (!res.ok || !res.body) {
      asstTurn.error = "Research backend unreachable. Confirm the server (start-web.sh) is still running on port 8787.";
      asstTurn.streaming = false;
      finalizeStream();
      return;
    }

    await consumeSSE(res.body, asstTurn);
  } catch (e) {
    if (e.name === "AbortError") {
      asstTurn.streaming = false;
      asstTurn.stopped = true;
    } else {
      asstTurn.error = "Research backend unreachable. Confirm the server (start-web.sh) is still running on port 8787.";
      asstTurn.streaming = false;
    }
    finalizeStream();
  }
}

async function consumeSSE(body, asstTurn) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const evt = parseSSEBlock(raw);
      if (!evt) continue;
      handleSSE(evt, asstTurn);
      if (evt.event === "done" || evt.event === "error") {
        finalizeStream();
        return;
      }
    }
  }
  finalizeStream();
}

function parseSSEBlock(raw) {
  let event = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return null;
  }
}

function handleSSE(evt, asstTurn) {
  if (evt.event === "sources") {
    asstTurn.sources = evt.data;
    renderRail();
    scheduleStreamingRender(asstTurn.id);
    return;
  }
  if (evt.event === "delta") {
    asstTurn.content += evt.data;
    scheduleStreamingRender(asstTurn.id);
    return;
  }
  if (evt.event === "done") {
    asstTurn.streaming = false;
    return;
  }
  if (evt.event === "error") {
    asstTurn.streaming = false;
    asstTurn.error = evt.data?.message || "Something went wrong upstream.";
  }
}

function finalizeStream() {
  streamingRenderFrame = null;
  state.isStreaming = false;
  state.abortController = null;
  toggleSendStop(false);
  els.input.disabled = false;
  bumpSession();
  saveSessions();
  render();
  els.input.focus();
}

function toggleSendStop(streaming) {
  els.sendBtn.hidden = streaming;
  els.stopBtn.hidden = !streaming;
}

// ── Export ────────────────────────────────────────────────────────────

function exportMarkdown() {
  const turns = activeTurns();
  if (turns.length === 0) {
    showToast("Nothing to export");
    return;
  }
  const date = new Date().toISOString().slice(0, 10);
  const session = activeSession();
  const lines = [`# ${session?.title || "Research Assistant"} - ${date}`, ""];

  for (const turn of turns) {
    if (turn.role === "user") {
      lines.push(`## You`, "", turn.content, "");
    } else if (turn.error) {
      lines.push(`## Assistant`, "", `> ${turn.error}`, "");
    } else {
      lines.push(`## Assistant`, "", turn.content, "");
      if (turn.sources?.length) {
        lines.push(`### Sources`, "");
        turn.sources.forEach((src, i) => {
          const meta = src.metadata || {};
          const title = meta.title || (meta.source || "Untitled").replace(/\.md$/, "");
          const topic = meta.topics || "";
          const section = meta.section || "";
          lines.push(`**[${pad2(i + 1)}] ${title}**${topic ? ` - ${topic}` : ""}${section ? ` · ${section}` : ""}`);
          lines.push(`> ${(src.text || "").trim().split("\n").join("\n> ")}`, "");
        });
      }
    }
  }

  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `research-assistant-${date}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── New chat ──────────────────────────────────────────────────────────

function newChat() {
  if (state.isStreaming) {
    showToast("Wait for response to finish");
    return;
  }
  const current = activeSession();
  // If current session is empty, just reuse it
  if (current && current.turns.length === 0) {
    els.input.focus();
    return;
  }
  const s = newSessionObject();
  state.sessions[s.id] = s;
  state.activeSessionId = s.id;
  state.activeTurnId = null;
  saveSessions();
  render();
  els.input.focus();
}

// ── Open in Obsidian ──────────────────────────────────────────────────

function openInObsidian() {
  if (!activeSlideoverSource) return;
  const meta = activeSlideoverSource.metadata || {};
  const source = meta.source || "";
  if (!source) {
    showToast("No source path on this excerpt");
    return;
  }
  const file = source.replace(/\.md$/, "");
  const uri = `obsidian://open?library=${encodeURIComponent(VAULT_NAME)}&file=${encodeURIComponent(file)}`;
  window.location.href = uri;
}

async function copyExcerpt() {
  if (!activeSlideoverSource) return;
  try {
    await navigator.clipboard.writeText(activeSlideoverSource.text || "");
    showToast("Copied");
  } catch {
    showToast("Copy failed");
  }
}

// ── Composer ──────────────────────────────────────────────────────────

function autoGrow() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 6 * 1.45 * 17 + 24) + "px";
  els.sendBtn.disabled = !els.input.value.trim() || state.isStreaming;
}

function handleSend() {
  if (state.isStreaming) return;
  const q = els.input.value.trim();
  if (!q) return;
  els.input.value = "";
  autoGrow();
  ask(q);
}

function submitFromComposer(e) {
  if (e) e.preventDefault();
  handleSend();
}

function onComposerKeydown(e) {
  if (e.key !== "Enter" && e.code !== "NumpadEnter") return;
  if (e.shiftKey || e.altKey || e.metaKey || e.ctrlKey) return;
  if (e.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  submitFromComposer();
}

function handleStop() {
  if (state.abortController) {
    state.abortController.abort();
  }
}

// ── Command palette ───────────────────────────────────────────────────

function buildCommands() {
  const cmds = [];

  // Actions
  cmds.push({
    group: "Actions",
    icon: "+",
    label: "New chat",
    hint: "Start a fresh research session",
    shortcut: "⌘⇧N",
    keywords: ["new", "chat", "session", "fresh"],
    run: () => newChat(),
  });
  cmds.push({
    group: "Actions",
    icon: "↗",
    label: "Export current chat as Markdown",
    hint: "Download the active session",
    shortcut: "⌘⇧E",
    keywords: ["export", "markdown", "download", "save"],
    run: () => exportMarkdown(),
  });
  cmds.push({
    group: "Actions",
    icon: "/",
    label: "Focus composer",
    hint: "Jump to the question input",
    shortcut: "⌘/",
    keywords: ["focus", "input", "compose", "ask", "question"],
    run: () => els.input.focus(),
  });

  // Topics - selected topic first, then "All topics" option, then top topics
  cmds.push({
    group: "Topics",
    icon: "≡",
    label: state.selectedLane ? `Topic: ${state.selectedLane} (active)` : "All topics (no filter)",
    hint: "Clear topic filter",
    keywords: ["topic", "filter", "all", "clear"],
    run: () => selectLane(null),
  });
  for (const topic of state.topics.slice(0, 12)) {
    if (topic.name === state.selectedLane) continue;
    cmds.push({
      group: "Topics",
      icon: "≡",
      label: `Filter by ${topic.name}`,
      hint: `${topic.count} passages`,
      keywords: ["topic", "filter", topic.name.toLowerCase()],
      run: () => selectLane(topic.name),
    });
  }

  // Sessions - list active and recent
  const allSessions = Object.values(state.sessions)
    .filter((s) => s.turns.length > 0)
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  for (const session of allSessions.slice(0, 10)) {
    if (session.id === state.activeSessionId) continue;
    cmds.push({
      group: "Sessions",
      icon: "▦",
      label: session.title || "Untitled chat",
      hint: relativeTime(session.updatedAt || session.createdAt),
      keywords: ["session", "switch", "history", (session.title || "").toLowerCase()],
      run: () => switchSession(session.id),
    });
  }

  // Sources - only when there's an active answer with sources
  const turn = activeTurns().find((t) => t.id === state.activeTurnId);
  if (turn && Array.isArray(turn.sources)) {
    turn.sources.forEach((src, i) => {
      const meta = src.metadata || {};
      const title = meta.title || "Untitled source";
      cmds.push({
        group: "Sources in current answer",
        icon: String(i + 1).padStart(2, "0"),
        label: title,
        hint: meta.topics || "",
        keywords: ["source", "citation", "card", title.toLowerCase()],
        run: () => {
          jumpToSource(i + 1);
          openSlideover(i + 1);
        },
      });
    });
  }

  return cmds;
}

function openPalette() {
  if (isCommandPaletteOpen()) {
    closeCommandPalette();
    return;
  }
  openCommandPalette(buildCommands());
}

// ── Header scroll shadow ──────────────────────────────────────────────

function bindHeaderScroll() {
  let ticking = false;
  els.conversationColumn.addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      els.header.classList.toggle("is-scrolled", els.conversationColumn.scrollTop > 8);
      ticking = false;
    });
  });
}

// ── Boot ──────────────────────────────────────────────────────────────

function bind() {
  els.examples = document.querySelectorAll(".ra-example");

  // Composer - form submit + Enter (Shift+Enter = newline)
  if (els.composerForm) {
    els.composerForm.addEventListener("submit", submitFromComposer);
  }
  els.input.addEventListener("input", autoGrow);
  els.input.addEventListener("keydown", onComposerKeydown);
  els.input.addEventListener("focus", () => {
    composerFocused = true;
    updateComposerChrome();
  });
  els.input.addEventListener("blur", () => {
    composerFocused = false;
    updateComposerChrome();
  });
  els.sendBtn.addEventListener("click", (e) => {
    e.preventDefault();
    submitFromComposer();
  });
  els.stopBtn.addEventListener("click", handleStop);

  if (els.composerLaneClear) {
    els.composerLaneClear.addEventListener("click", (e) => {
      e.stopPropagation();
      selectLane(null);
      els.input.focus();
    });
  }

  // Examples
  els.examples.forEach((btn) => {
    btn.addEventListener("click", () => {
      els.input.value = btn.textContent.trim();
      autoGrow();
      els.input.focus();
    });
  });

  // Topic dropdown - composer trigger
  if (els.composerLaneBtn) {
    els.composerLaneBtn.addEventListener("click", () => {
      if (els.topicPanel.hidden) openLanePanel();
      else closeLanePanel();
    });
  }
  if (els.composerCmdkBtn) {
    els.composerCmdkBtn.addEventListener("click", () => openPalette());
  }
  if (els.railExpandBtn) {
    els.railExpandBtn.addEventListener("click", () => {
      state.railUI.expandAll = !state.railUI.expandAll;
      state.railUI.expanded.clear();
      renderRail();
    });
  }
  els.topicSearch.addEventListener("input", (e) => renderLaneList(e.target.value));
  document.addEventListener("click", (e) => {
    if (!els.topicPanel.hidden && !e.target.closest(".ra-topic") && !e.target.closest("#composerLaneBtn") && !e.target.closest("#composerLaneClear")) {
      closeLanePanel();
    }
  });

  // Header buttons
  els.newChatBtn.addEventListener("click", newChat);
  els.newChatHeroBtn.addEventListener("click", newChat);
  els.exportBtn.addEventListener("click", exportMarkdown);

  // Slide-over
  els.slideoverClose.addEventListener("click", closeSlideover);
  els.overlay.addEventListener("click", closeSlideover);
  els.copyExcerptBtn.addEventListener("click", copyExcerpt);
  els.openObsidianBtn.addEventListener("click", openInObsidian);

  // Keyboard shortcuts
  document.addEventListener("keydown", (e) => {
    // Esc
    if (e.key === "Escape") {
      if (isCommandPaletteOpen()) closeCommandPalette();
      else if (citePreviewEl) hideCitePreview();
      else if (!els.slideover.hidden) closeSlideover();
      else if (!els.topicPanel.hidden) closeLanePanel();
      else if (els.rail.classList.contains("is-mobile-open")) els.rail.classList.remove("is-mobile-open");
      return;
    }
    const meta = e.metaKey || e.ctrlKey;
    if (!meta) return;
    // ⌘K → command palette
    if (!e.shiftKey && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      openPalette();
      return;
    }
    // ⌘/  → focus composer
    if (e.key === "/") {
      e.preventDefault();
      els.input.focus();
      return;
    }
    // ⌘⇧N → new chat
    if (e.shiftKey && (e.key === "N" || e.key === "n")) {
      e.preventDefault();
      newChat();
      return;
    }
    // ⌘⇧E → export
    if (e.shiftKey && (e.key === "E" || e.key === "e")) {
      e.preventDefault();
      exportMarkdown();
      return;
    }
    // ⌘⇧L → topic panel
    if (e.shiftKey && (e.key === "L" || e.key === "l")) {
      e.preventDefault();
      if (els.topicPanel.hidden) openLanePanel();
      else closeLanePanel();
      return;
    }
  });

  bindHeaderScroll();
}

async function init() {
  bind();
  loadSessions();
  applyURLLane();
  updateLaneUI();
  await Promise.all([fetchStats(), fetchLanes(), loadMarked()]);
  render();
  autoGrow();
  startPlaceholderRotation();
  if (activeTurns().length > 0) els.input.focus();
}

init();
