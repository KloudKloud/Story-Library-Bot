/* pvp/static/game.js */
"use strict";

// SESSION_ID and PRESET_P1/P2 are injected by the HTML template before this script loads.

// ── State ─────────────────────────────────────────────────────────────────────
let G = {
  state:          null,
  myPlayerIdx:    0,
  pendingPass:    null,
  discardMode:    false,
  selectedCard:   null,
  p1Affinity:     "fire",
  p2Affinity:     "ice",
};

const EL_EMOJI = { fire:"🔥", ice:"❄️", lightning:"⚡" };
const EL_IMG   = { fire:"/images/fire.jpg", ice:"/images/ice.jpg", lightning:"/images/lightning.jpg" };

// ── Screen helpers ─────────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  const el = document.getElementById("screen-" + id);
  if (el) el.classList.add("active");
}

// ── API helpers ───────────────────────────────────────────────────────────────
// All requests are scoped to this session: /api/<SESSION_ID>/<endpoint>
async function api(endpoint, body = null) {
  const path = `/api/${SESSION_ID}/${endpoint}`;
  const opts = body
    ? { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body) }
    : { method:"GET" };
  const r = await fetch(path, opts);
  const data = await r.json();
  if (data.error === "Session not found or expired.") {
    showToast("⚠️ Session expired. Please start a new battle from Discord.");
  }
  return data;
}

// ── Pre-fill names from Discord if provided ────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  if (PRESET_P1) document.getElementById("p1-name").value = PRESET_P1;
  if (PRESET_P2) document.getElementById("p2-name").value = PRESET_P2;
});

// ── Setup screen ──────────────────────────────────────────────────────────────
document.querySelectorAll(".affinity-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const player = btn.dataset.player;
    document.querySelectorAll(`.affinity-btn[data-player="${player}"]`)
      .forEach(b => b.classList.remove("selected"));
    btn.classList.add("selected");
    if (player === "1") G.p1Affinity = btn.dataset.el;
    else                G.p2Affinity = btn.dataset.el;
  });
});

document.getElementById("btn-start-game").addEventListener("click", async () => {
  const p1Name = document.getElementById("p1-name").value.trim() || "Player 1";
  const p2Name = document.getElementById("p2-name").value.trim() || "Player 2";
  const state  = await api("new_game", {
    p1_name: p1Name, p1_affinity: G.p1Affinity,
    p2_name: p2Name, p2_affinity: G.p2Affinity,
  });
  G.state = state;
  G.myPlayerIdx = 0;
  showCharSelect(0);
});

// ── Character select ──────────────────────────────────────────────────────────
function showCharSelect(playerIdx) {
  const s   = G.state;
  const p   = s.players[playerIdx];
  const choices = p.char_choices || [];

  document.getElementById("charselect-title").textContent =
    `${p.name} — Choose Your Character`;
  document.getElementById("charselect-sub").textContent =
    "This card is purely cosmetic. Pick whoever calls to you.";

  const grid = document.getElementById("char-choices-grid");
  grid.innerHTML = "";

  choices.forEach((char, i) => {
    const card = document.createElement("div");
    card.className = "char-choice-card";

    let imgHtml = `<div class="char-placeholder">🧙</div>`;
    if (char.image_url) {
      imgHtml = `<img src="${char.image_url}" alt="${char.name}" onerror="this.style.display='none'">`;
    }

    const personality = char.personality || char.bio || "A mysterious fighter.";
    const snippet = personality.length > 80 ? personality.slice(0, 80) + "…" : personality;

    card.innerHTML = `
      ${imgHtml}
      <div class="char-info">
        <h3>${char.name || "Unknown"}</h3>
        <p>${snippet}</p>
      </div>
    `;
    card.addEventListener("click", async () => {
      const newState = await api("action", {
        action: "select_character",
        player: playerIdx,
        char_index: i,
      });
      G.state = newState.state || newState;

      if (G.state.phase === "char_select") {
        showPassScreen(
          `Pass to ${s.players[1].name}`,
          `${s.players[1].name}, it's your turn to choose a character.`,
          () => showCharSelect(1)
        );
      } else {
        G.myPlayerIdx = 0;
        showPassScreen(
          `Pass to ${G.state.players[0].name}`,
          `${G.state.players[0].name}, the battle is about to begin!`,
          () => renderBattle()
        );
      }
    });
    grid.appendChild(card);
  });

  showScreen("charselect");
}

// ── Pass screen ───────────────────────────────────────────────────────────────
function showPassScreen(title, subtitle, callback) {
  document.getElementById("pass-title").textContent    = title;
  document.getElementById("pass-subtitle").textContent = subtitle;
  G.pendingPass = callback;
  showScreen("pass");
}

document.getElementById("btn-pass-ready").addEventListener("click", () => {
  if (G.pendingPass) {
    const cb = G.pendingPass;
    G.pendingPass = null;
    cb();
  }
});

// ── Battle rendering ──────────────────────────────────────────────────────────
function renderBattle() {
  const s   = G.state;
  const you = s.players[G.myPlayerIdx];
  const opp = s.players[1 - G.myPlayerIdx];

  if (s.phase === "end") { showEndScreen(); return; }
  showScreen("battle");

  const myTurn    = s.current_turn === G.myPlayerIdx;
  const currentP  = s.players[s.current_turn];
  document.getElementById("turn-banner").textContent =
    `${currentP.name}'s Turn — Turn ${s.turn_number}`;

  renderHP("you",  you);
  renderHP("opp",  opp);
  renderMana("you-mana-pips", you.mana, you.max_mana);
  renderMana("opp-mana-pips", opp.mana, opp.max_mana);
  renderStatus("you-status", you);
  renderStatus("opp-status", opp);

  document.getElementById("you-name").textContent = you.name;
  document.getElementById("opp-name").textContent = opp.name;

  renderPortrait("you-portrait", you.character);
  renderPortrait("opp-portrait", opp.character);

  const oppBacks = document.getElementById("opp-hand-backs");
  oppBacks.innerHTML = "";
  (opp.hand || []).forEach(() => {
    const b = document.createElement("div");
    b.className = "card-back";
    oppBacks.appendChild(b);
  });

  renderHand(you.hand_cards || [], myTurn, you.mana);

  document.getElementById("btn-draw").disabled =
    !myTurn || you.drew_this_turn;
  document.getElementById("btn-discard-mode").disabled =
    !myTurn || you.discarded_this_turn;
  document.getElementById("btn-end-turn").disabled = !myTurn;

  const fnotice = document.getElementById("freeze-notice");
  if (myTurn && you.freeze_turns > 0) {
    fnotice.style.display = "block";
    fnotice.textContent   = `❄️  You are frozen — can't play cards for ${you.freeze_turns} more turn(s).`;
  } else {
    fnotice.style.display = "none";
  }

  renderLog(s.log);

  document.getElementById("discard-hint").style.display =
    G.discardMode ? "inline" : "none";
  document.getElementById("btn-discard-mode").textContent =
    G.discardMode ? "❌ Cancel Discard" : "🗑️ Discard Mode";
}

function renderHP(prefix, player) {
  const pct = Math.max(0, player.hp / player.max_hp * 100);
  document.getElementById(prefix + "-hp-bar").style.width = pct + "%";
  document.getElementById(prefix + "-hp-text").textContent =
    `${player.hp} / ${player.max_hp} HP` +
    (player.shield > 0 ? `  🛡️${player.shield}` : "");
}

function renderMana(id, current, max) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  for (let i = 0; i < max; i++) {
    const pip = document.createElement("div");
    pip.className = "mana-pip" + (i < current ? " full" : "");
    el.appendChild(pip);
  }
  for (let i = max; i < current; i++) {
    const pip = document.createElement("div");
    pip.className = "mana-pip full";
    pip.style.borderColor = "#ff80ff";
    pip.style.background  = "#a040c0";
    el.appendChild(pip);
  }
}

function renderStatus(id, player) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  if (player.burn_turns > 0)
    el.innerHTML += `<span class="status-tag tag-burn">🔥 Burn ${player.burn_value}×${player.burn_turns}</span>`;
  if (player.freeze_turns > 0)
    el.innerHTML += `<span class="status-tag tag-freeze">❄️ Frozen ${player.freeze_turns}t</span>`;
  if (player.shield > 0)
    el.innerHTML += `<span class="status-tag tag-shield">🛡️ ${player.shield}</span>`;
  if (player.stun_mana > 0)
    el.innerHTML += `<span class="status-tag tag-stun">⚡ -${player.stun_mana} mana</span>`;
}

function renderPortrait(id, character) {
  const el = document.getElementById(id);
  if (!character) { el.innerHTML = ""; return; }
  if (character.image_url) {
    el.innerHTML = `<img src="${character.image_url}" alt="${character.name}">
                    <span>${character.name}</span>`;
  } else {
    el.innerHTML = `<div class="char-icon">🧙</div><span>${character.name || "?"}</span>`;
  }
}

function renderHand(cards, myTurn, mana) {
  const hand = document.getElementById("your-hand");
  hand.innerHTML = "";
  cards.forEach(card => {
    const affordable = card.cost <= mana;
    const el = buildCardEl(card, myTurn, affordable);
    hand.appendChild(el);
  });
}

function buildCardEl(card, myTurn, affordable) {
  const div = document.createElement("div");
  div.className = "action-card" +
    (G.selectedCard === card.id ? " selected" : "") +
    (!affordable && !G.discardMode ? " unaffordable" : "");
  div.dataset.element = card.element;
  div.dataset.id      = card.id;

  const emoji = EL_EMOJI[card.element] || "✨";
  div.innerHTML = `
    <div class="card-element-bar"></div>
    <div class="card-header">
      <div class="card-name">${card.name}</div>
      <div class="card-cost">${card.cost}</div>
    </div>
    <img class="card-img" src="${EL_IMG[card.element]}" alt="${card.element}"
         onerror="this.style.display='none'">
    <div class="card-desc">${card.description}</div>
    <div class="card-tooltip">
      <div class="tt-name">${emoji} ${card.name}</div>
      <div class="tt-cost">Cost: ${card.cost} mana</div>
      <div style="margin-top:4px">${card.description}</div>
    </div>
  `;

  if (myTurn) {
    div.addEventListener("click", () => {
      if (G.discardMode) {
        doDiscard(card.id);
      } else if (affordable) {
        doPlayCard(card.id, div);
      }
    });
  }
  return div;
}

function renderLog(log) {
  const el = document.getElementById("log-entries");
  const existing = el.querySelectorAll(".log-entry").length;
  for (let i = existing; i < log.length; i++) {
    const entry = document.createElement("div");
    entry.className = "log-entry new";
    entry.textContent = log[i];
    el.appendChild(entry);
  }
  el.scrollTop = el.scrollHeight;

  const playedCards = log.slice().reverse();
  for (const line of playedCards) {
    if (line.startsWith("▶️")) {
      const match = line.match(/plays \*\*(.*?)\*\*/);
      if (match) {
        const slot = document.getElementById("last-played-slot");
        slot.innerHTML = `<div style="color:var(--text);font-size:.85rem;text-align:center">
          ${line.replace(/\*\*/g,"")}</div>`;
        break;
      }
    }
  }
}

// ── Battle actions ────────────────────────────────────────────────────────────
async function doPlayCard(cardId) {
  G.selectedCard = null;
  const result = await api("action", {
    action: "play_card", player: G.myPlayerIdx, card_id: cardId,
  });
  if (result.error) { showToast("❌ " + result.error); G.state = result.state || G.state; }
  else { G.state = result; }
  renderBattle();
}

async function doDiscard(cardId) {
  G.discardMode = false;
  const result = await api("action", {
    action: "discard_card", player: G.myPlayerIdx, card_id: cardId,
  });
  if (result.error) { showToast("❌ " + result.error); G.state = result.state || G.state; }
  else { G.state = result; }
  renderBattle();
}

document.getElementById("btn-draw").addEventListener("click", async () => {
  const result = await api("action", {
    action: "draw_card", player: G.myPlayerIdx,
  });
  if (result.error) { showToast("❌ " + result.error); G.state = result.state || G.state; }
  else { G.state = result; }
  renderBattle();
});

document.getElementById("btn-discard-mode").addEventListener("click", () => {
  G.discardMode = !G.discardMode;
  renderBattle();
});

document.getElementById("btn-end-turn").addEventListener("click", async () => {
  const result = await api("action", {
    action: "end_turn", player: G.myPlayerIdx,
  });
  if (result.error) { showToast("❌ " + result.error); G.state = result.state || G.state; }
  else { G.state = result; }

  if (G.state.phase === "end") {
    showEndScreen();
    return;
  }

  const nextIdx = G.state.current_turn;
  const nextP   = G.state.players[nextIdx];
  G.myPlayerIdx = nextIdx;
  showPassScreen(
    `Pass to ${nextP.name}`,
    `${nextP.name}, it's your turn! Hand has been hidden.`,
    () => renderBattle()
  );
});

// ── End screen ────────────────────────────────────────────────────────────────
function showEndScreen() {
  const s      = G.state;
  const winner = s.winner !== null ? s.players[s.winner] : null;
  document.getElementById("end-winner").textContent =
    winner ? `🏆  ${winner.name} Wins!` : "It's a Draw!";
  document.getElementById("end-subtitle").textContent =
    winner ? `${winner.name} has defeated their opponent!` : "";

  const logEl = document.getElementById("end-log");
  logEl.innerHTML = "";
  (s.log || []).forEach(line => {
    const e = document.createElement("div");
    e.className   = "log-entry";
    e.textContent = line;
    logEl.appendChild(e);
  });
  logEl.scrollTop = logEl.scrollHeight;

  showScreen("end");
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg) {
  let t = document.getElementById("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    t.style.cssText = `
      position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
      background:#2a0808;border:1px solid #802020;color:#ff8080;
      padding:10px 20px;border-radius:8px;font-size:.85rem;z-index:9999;
      opacity:0;transition:opacity .2s;pointer-events:none;
    `;
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity = "1";
  clearTimeout(t._to);
  t._to = setTimeout(() => { t.style.opacity = "0"; }, 2500);
}
