// ──────────────────────────────────────────────────────────────────────
// Research Assistant: command palette
// Lightweight ⌘K overlay. Takes commands as input - no app coupling.
// ──────────────────────────────────────────────────────────────────────

let paletteEl = null;
let commands = [];
let filtered = [];
let activeIndex = 0;

export function openCommandPalette(cmds) {
  commands = Array.isArray(cmds) ? cmds : [];
  filtered = commands.slice();
  activeIndex = 0;
  if (!paletteEl) build();
  paletteEl.hidden = false;
  document.body.classList.add("is-palette-open");
  const input = paletteEl.querySelector(".ra-palette-input");
  input.value = "";
  renderList();
  // Focus after the next paint so the show animation doesn't fight focus.
  requestAnimationFrame(() => input.focus());
}

export function closeCommandPalette() {
  if (!paletteEl || paletteEl.hidden) return;
  paletteEl.hidden = true;
  document.body.classList.remove("is-palette-open");
}

export function isCommandPaletteOpen() {
  return !!paletteEl && !paletteEl.hidden;
}

function build() {
  paletteEl = document.createElement("div");
  paletteEl.className = "ra-palette-overlay";
  paletteEl.hidden = true;
  paletteEl.innerHTML = `
    <div class="ra-palette" role="dialog" aria-modal="true" aria-label="Command palette">
      <div class="ra-palette-search">
        <svg class="ra-palette-search-icon" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" stroke-width="1.5"/>
          <path d="M9.5 9.5l3 3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <input
          type="text"
          class="ra-palette-input"
          placeholder="Run a command…"
          autocomplete="off"
          spellcheck="false"
          aria-label="Search commands"
        />
        <kbd class="ra-palette-esc">esc</kbd>
      </div>
      <ul class="ra-palette-list" role="listbox" aria-label="Commands"></ul>
      <div class="ra-palette-foot">
        <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
        <span><kbd>↵</kbd> select</span>
        <span><kbd>esc</kbd> close</span>
      </div>
    </div>
  `;
  document.body.appendChild(paletteEl);

  // Backdrop click closes
  paletteEl.addEventListener("mousedown", (e) => {
    if (e.target === paletteEl) closeCommandPalette();
  });

  const input = paletteEl.querySelector(".ra-palette-input");

  input.addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    filtered = q
      ? commands.filter((c) => {
          const hay = `${c.label} ${c.hint || ""} ${c.group || ""} ${(c.keywords || []).join(" ")}`.toLowerCase();
          return hay.includes(q);
        })
      : commands.slice();
    activeIndex = 0;
    renderList();
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      closeCommandPalette();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, Math.max(filtered.length - 1, 0));
      renderList(true);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      renderList(true);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      runActive();
      return;
    }
  });
}

function runActive() {
  const cmd = filtered[activeIndex];
  if (!cmd || typeof cmd.run !== "function") return;
  closeCommandPalette();
  // Defer so the close animation/state happens before any side effects (focus).
  requestAnimationFrame(() => cmd.run());
}

function renderList(scrollIntoView = false) {
  const list = paletteEl.querySelector(".ra-palette-list");
  if (filtered.length === 0) {
    list.innerHTML = `<li class="ra-palette-empty">No matches.</li>`;
    return;
  }
  // Group consecutive items by group label
  let lastGroup = null;
  const html = [];
  filtered.forEach((c, i) => {
    if (c.group && c.group !== lastGroup) {
      html.push(`<li class="ra-palette-group" aria-hidden="true">${escapeHTML(c.group)}</li>`);
      lastGroup = c.group;
    }
    html.push(`
      <li class="ra-palette-item ${i === activeIndex ? "is-active" : ""}" role="option" data-index="${i}" aria-selected="${i === activeIndex}">
        <span class="ra-palette-icon" aria-hidden="true">${c.icon || ""}</span>
        <span class="ra-palette-label">${escapeHTML(c.label)}</span>
        ${c.hint ? `<span class="ra-palette-hint">${escapeHTML(c.hint)}</span>` : ""}
        ${c.shortcut ? `<kbd class="ra-palette-shortcut">${escapeHTML(c.shortcut)}</kbd>` : ""}
      </li>
    `);
  });
  list.innerHTML = html.join("");

  list.querySelectorAll(".ra-palette-item").forEach((el) => {
    const i = Number(el.dataset.index);
    el.addEventListener("mousemove", () => {
      if (i === activeIndex) return;
      activeIndex = i;
      list.querySelectorAll(".ra-palette-item").forEach((x, j) => {
        const idx = Number(x.dataset.index);
        x.classList.toggle("is-active", idx === activeIndex);
        x.setAttribute("aria-selected", idx === activeIndex);
      });
    });
    el.addEventListener("click", () => {
      activeIndex = i;
      runActive();
    });
  });

  if (scrollIntoView) {
    const active = list.querySelector(".ra-palette-item.is-active");
    if (active) active.scrollIntoView({ block: "nearest" });
  }
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}
