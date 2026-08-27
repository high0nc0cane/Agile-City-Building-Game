'use strict';

const currentUser = window.currentUser || null;

const BUILDING_INFO = {
  R: { name: 'Residential', desc: '+1 per adj Residential or Commercial\n+2 per adj Park\n−1 if adj to Industry', cls: 'bc-R', sym: 'R' },
  I: { name: 'Industry',    desc: '+1 per Industry building in the city\nGenerates +1 coin per adj Residential', cls: 'bc-I', sym: 'I' },
  C: { name: 'Commercial',  desc: '+1 per adj Commercial\nGenerates +1 coin per adj Residential', cls: 'bc-C', sym: 'C' },
  O: { name: 'Park',        desc: '+1 per adj Park\nGives +2 bonus to each adj Residential', cls: 'bc-O', sym: 'O' },
  '*': { name: 'Road',      desc: '+1 per connected Road in the same row', cls: 'bc-road', sym: '*' },
};

const CHALLENGE_MODE = 'challenge';
const LIMITED_MODES = new Set(['arcade', CHALLENGE_MODE]);

const EVENT_POPUP_DURATION_NORMAL = 5000;
const EVENT_POPUP_DURATION_WARNING = 6000;
const EVENT_POPUP_DURATION_DISASTER = 7000;
const EVENT_FEED_LIMIT = 50;

let bonusTaskPopupQueue = [];
let bonusTaskPopupActive = false;
let bonusTaskPopupTimer = null;

function queueBonusTaskPopup(title, description) {
  bonusTaskPopupQueue.push({ title, description });
  showNextBonusPopup();
}

function showNextBonusPopup() {
  if (bonusTaskPopupActive || bonusTaskPopupQueue.length === 0) return;

  const popup = document.getElementById('bonus-task-popup');
  if (!popup) return;

  const message = bonusTaskPopupQueue.shift();
  bonusTaskPopupActive = true;

  popup.classList.remove('hidden', 'closing');
  set('bonus-popup-title', message.title);
  set('bonus-popup-desc', message.description);

  clearTimeout(bonusTaskPopupTimer);
  bonusTaskPopupTimer = setTimeout(dismissBonusPopup, 4500);
}

function dismissBonusPopup() {
  if (!bonusTaskPopupActive) return;
  const popup = document.getElementById('bonus-task-popup');
  clearTimeout(bonusTaskPopupTimer);

  if (!popup) {
    bonusTaskPopupActive = false;
    showNextBonusPopup();
    return;
  }

  popup.classList.add('closing');
  const finishClose = () => {
    popup.classList.add('hidden');
    popup.classList.remove('closing');
    bonusTaskPopupActive = false;
    showNextBonusPopup();
  };

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    finishClose();
  } else {
    setTimeout(finishClose, 250);
  }
}

let eventPopupQueue = [];
let eventPopupActive = false;
let eventPopupTimer = null;

function isLimitedMode(mode) {
  return LIMITED_MODES.has(mode);
}

let state = null;
let selectedBuilding = null;
let isDemolishMode = false;
let validSet = new Set();
let actionInFlight = false;
let confirmModalOnConfirm = null;
let hasSavedGame = false;

function navigateWithMusicFade(href) {
  window.dispatchEvent(new CustomEvent('music:navigate', {
    detail: { href }
  }));
}

function openConfirmModal(title, message, onConfirm, confirmLabel = 'Confirm', isDanger = false) {
  const modal = document.getElementById('confirmModal');
  const titleEl = document.getElementById('confirmModalTitle');
  const messageEl = document.getElementById('confirmModalMessage');
  const confirmBtn = document.getElementById('confirmModalConfirmBtn');
  if (!modal || !titleEl || !messageEl || !confirmBtn) return;

  titleEl.textContent = title;
  messageEl.innerHTML = message;
  confirmBtn.textContent = confirmLabel;
  confirmBtn.classList.toggle('btn-danger', isDanger);
  confirmModalOnConfirm = onConfirm;
  modal.classList.remove('hidden');
}

function closeConfirmModal() {
  confirmModalOnConfirm = null;
  const confirmBtn = document.getElementById('confirmModalConfirmBtn');
  if (confirmBtn) confirmBtn.classList.remove('btn-danger');
  closeModalById('confirmModal');
}

function runConfirmModalAction() {
  const action = confirmModalOnConfirm;
  closeConfirmModal();
  if (typeof action === 'function') {
    action();
  }
}

// ── Init ─────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  const closeButton = document.getElementById('city-event-popup-close');
  if (closeButton) closeButton.addEventListener('click', dismissEventPopup);

  const confirmBtn = document.getElementById('confirmModalConfirmBtn');
  if (confirmBtn) confirmBtn.addEventListener('click', runConfirmModalAction);

  document.querySelectorAll('.gl-switch-btn').forEach(button => {
    button.addEventListener('click', () => toggleBonusPanel(button.dataset.panel));
  });

  initBonusTaskFilters();

  const res = await fetch('/api/state');
  if (!res.ok) { navigateWithMusicFade('/'); return; }
  hasSavedGame = false;
  applyState(await res.json());
});

let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (state) renderBoard(state);
  }, 120);
});

// ── State management ──────────────────────────────────────────────

function toggleBonusPanel(panel) {
  document.querySelectorAll('.gl-switch-btn').forEach(button => {
    button.classList.toggle('active', button.dataset.panel === panel);
  });
  document.querySelectorAll('.gl-panel-view').forEach(view => {
    view.classList.toggle('active', view.id === `${panel}-panel`);
  });
}

let bonusTaskFilter = 'active';

function initBonusTaskFilters() {
  document.querySelectorAll('.bonus-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      bonusTaskFilter = btn.dataset.filter;
      document.querySelectorAll('.bonus-filter-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.filter === bonusTaskFilter);
      });
      renderBonusTasks(state);
    });
  });
}

function renderBonusTasks(s) {
  const list = document.getElementById('bonus-task-list');
  const completionText = document.getElementById('bonus-completion-text');
  const fill = document.getElementById('bonus-progress-fill');
  if (!list || !completionText || !fill) return;

  const tasks = Array.isArray(s.bonus_tasks) ? s.bonus_tasks : [];
  const completed = Array.isArray(s.completed_bonus_task_ids) ? s.completed_bonus_task_ids.length : 0;

  // CHANGE: the denominator now reflects the cumulative number of bonus
  // tasks ever dealt out (bonus_tasks_dealt_total), which grows by one
  // batch (bonus_task_total, e.g. 5) each time a fresh batch is handed
  // out — so this reads 3/5, then once that batch clears and a new one
  // starts, 5/10, 8/15, and so on, instead of resetting back to X/5
  // every batch.
  const total = Math.max(1, Number(s.bonus_tasks_dealt_total || s.bonus_task_total || 5));
  const progressPercent = Math.round((completed / total) * 100);

  completionText.textContent = `${completed}/${total} completed`;
  fill.style.width = `${Math.min(100, progressPercent)}%`;

  let filteredTasks = tasks;
  
  if (bonusTaskFilter === 'active') {
    filteredTasks = tasks.filter(t => t.status !== 'completed');
  } else if (bonusTaskFilter === 'completed') {
    filteredTasks = tasks.filter(t => t.status === 'completed');
  }

  if (!filteredTasks.length) {
    const emptyMsg = bonusTaskFilter === 'completed' 
      ? 'No completed tasks yet.'
      : 'No active tasks right now.';
    list.innerHTML = `<p class="bonus-task-empty">${emptyMsg}</p>`;
    return;
  }

  list.innerHTML = filteredTasks.map(task => {
    const progressText = `${task.progress || 0}/${task.goal_value || 0}`;
    const statusClass = task.status === 'completed' ? 'completed' : task.status === 'expired' ? 'expired' : '';
    return `
      <div class="bonus-task-item ${statusClass}">
        <div class="bonus-task-title">${task.title}</div>
        <div class="bonus-task-desc">${task.description}</div>
        <div class="bonus-task-meta">
          <span>${task.reward_text || ''}</span>
          <span class="bonus-task-progress">${progressText}</span>
        </div>
      </div>
    `;
  }).join('');
}

function applyState(s, opts = {}) {
  state = s;
  validSet = new Set((s.valid_cells || []).map(([r, c]) => `${r},${c}`));

  updateStats(s);
  renderBuildingOptions(s);
  renderChallengeEventFeed(s);
  renderBonusTasks(s);

  if (opts.placedAt) {
    renderBoard(s, opts.placedAt);
  } else {
    renderBoard(s);
  }

  queueEventPopups(s.event_notifications || []);

  const bonusNotifications = s.bonus_task_notifications || [];
  bonusNotifications.forEach(notification => {
    // FIX: the backend (game_state.py) sends bonus-task-complete
    // notifications prefixed with the 🎯 emoji, not 🏆 — this check was
    // checking for the wrong emoji, so the "bonus task complete" toast
    // popup never actually fired.
    if (notification.startsWith('🎯')) {
      const match = notification.match(/Bonus task complete: (.+?) \((.+?)\)/);
      if (match) {
        queueBonusTaskPopup(match[1], match[2]);
      }
    }
  });
}

// ── Stats - haoying ─────────────────────────────────────────────────────────

function updateStats(s) {
  set('stat-turn', s.turn);
  set('stat-score', s.score.toLocaleString());
  set('stat-buildings', s.buildings_count);

  const limitedMode = isLimitedMode(s.mode);
  document.querySelectorAll('.fp-only').forEach(el => {
    el.classList.toggle('hidden', s.mode !== 'freeplay');
  });
  document.querySelectorAll('.challenge-only').forEach(el => {
    el.classList.toggle('hidden', s.mode !== CHALLENGE_MODE);
  });

  if (limitedMode) {
    set('stat-coins', s.coins);
  } else {
    set('stat-coins', '∞');
    set('stat-profit', s.profit);
    set('stat-upkeep', s.upkeep);
    const net = s.profit - s.upkeep;
    const netEl = document.getElementById('stat-net');
    if (netEl) {
      netEl.textContent = (net >= 0 ? '+' : '') + net;
      netEl.style.color = net >= 0 ? 'var(--positive)' : 'var(--negative)';
    }
    set('stat-loss', s.loss_turns);
    const lossCard = document.getElementById('loss-stat');
    if (lossCard) lossCard.classList.toggle('hidden', s.loss_turns === 0);
  }

  if (s.mode === CHALLENGE_MODE) {
    set('stat-challenge-income', s.challenge_income || 0);
    set('stat-challenge-upkeep', s.challenge_upkeep || 0);
  }
}

// ── Building options - haoying ──────────────────────────────────────────────

function renderBuildingOptions(s) {
  const container = document.getElementById('building-options');
  const title = document.getElementById('panel-chooser-title');
  const hint = document.getElementById('panel-hint');
  const limitedMode = isLimitedMode(s.mode);
  const placementCost = limitedMode ? (s.placement_cost || 1) : 0;

  const types = limitedMode ? s.offered_buildings : ['R', 'I', 'C', 'O', '*'];
  title.textContent = limitedMode ? 'Choose a Building' : 'Build';
  hint.textContent = isDemolishMode
    ? 'Click a building to demolish it.'
    : limitedMode
      ? `Select a building, then click a cell. Current cost: ${placementCost} coin${placementCost === 1 ? '' : 's'}.`
      : 'Select a building, then click a cell.';

  container.innerHTML = '';
  types.forEach(type => {
    const info = BUILDING_INFO[type];
    if (!info) return;

    const card = document.createElement('button');
    card.className = `building-card ${info.cls}`;
    card.dataset.type = type;
    if (selectedBuilding === type) card.classList.add('selected');

    const symbol = document.createElement('span');
    symbol.className = 'bc-sym';
    symbol.textContent = info.sym;

    const infoWrap = document.createElement('span');
    infoWrap.className = 'bc-info';

    const name = document.createElement('span');
    name.className = 'bc-name';
    name.textContent = info.name;

    const description = document.createElement('span');
    description.className = 'bc-desc';
    description.textContent = info.desc;

    const cost = document.createElement('span');
    cost.className = 'bc-cost';
    cost.textContent = limitedMode
      ? `Cost: ${placementCost} coin${placementCost === 1 ? '' : 's'}`
      : 'Cost: Unlimited';

    infoWrap.append(name, description, cost);
    card.append(symbol, infoWrap);

    card.addEventListener('click', () => {
      isDemolishMode = false;
      updateDemolishBtn(false);
      selectBuilding(type);
    });
    container.appendChild(card);
  });
}

function selectBuilding(type) {
  selectedBuilding = selectedBuilding === type ? null : type;
  document.querySelectorAll('.building-card').forEach(card => {
    card.classList.toggle('selected', card.dataset.type === selectedBuilding);
  });

  const placementCost = state && isLimitedMode(state.mode) ? (state.placement_cost || 1) : 0;
  document.getElementById('panel-hint').textContent = selectedBuilding
    ? `Placing: ${BUILDING_INFO[selectedBuilding].name}${placementCost ? ` (${placementCost} coin${placementCost === 1 ? '' : 's'})` : ''} — click a highlighted cell.`
    : isLimitedMode(state.mode)
      ? `Select a building, then click a cell. Current cost: ${placementCost} coin${placementCost === 1 ? '' : 's'}.`
      : 'Select a building, then click a cell.';
  refreshHighlights();
}

// ── Grid rendering ────────────────────────────────────────────────

function cellClass(type) {
  if (!type) return '';
  return type === '*' ? 'building-road' : `building-${type}`;
}

// Renders (or re-renders) the row/column number labels around the board.
// Called every time renderBoard runs, so labels always match the current
// grid size — including after Free Play expansions.
function renderGridLabels(size, cellPx) {
  const wrap = document.getElementById('grid-with-labels');
  const colLabels = document.getElementById('grid-col-labels');
  const rowLabels = document.getElementById('grid-row-labels');

  wrap.style.setProperty('--cell-size', `${cellPx}px`);

  colLabels.style.gridTemplateColumns = `repeat(${size}, var(--cell-size))`;
  rowLabels.style.gridTemplateRows = `repeat(${size}, var(--cell-size))`;

  colLabels.innerHTML = '';
  for (let c = 0; c < size; c++) {
    const lbl = document.createElement('div');
    lbl.className = 'grid-label';
    lbl.textContent = c + 1;
    colLabels.appendChild(lbl);
  }

  rowLabels.innerHTML = '';
  for (let r = 0; r < size; r++) {
    const lbl = document.createElement('div');
    lbl.className = 'grid-label';
    lbl.textContent = r + 1;
    rowLabels.appendChild(lbl);
  }
}

// Computes a cell size (px) that makes the whole board — including the
// coordinate label row/column — fit inside .gl-main with no scrolling,
// no matter how big the grid gets (e.g. after Free Play expansions).
function computeCellSize(size) {
  const mainEl = document.querySelector('.gl-main');
  const rect = mainEl.getBoundingClientRect();
  const availW = rect.width - 6;
  const availH = rect.height - 6;
  const usable = Math.max(10, Math.min(availW, availH));

  // +1 unit accounts for the label row/column alongside the board cells.
  const units = size + 1;
  let cellPx = Math.floor(usable / units) - 1; // leave a little room for gaps
  cellPx = Math.max(12, Math.min(cellPx, 110));
  return cellPx;
}

function renderBoard(s, placedAt = null) {
  const grid = document.getElementById('game-grid');
  const board = s.board;
  const size = board.length;

  // Cell size is computed to always fit the available space — no fixed
  // thresholds, so the board never needs to scroll at any grid size.
  const cellPx = computeCellSize(size);

  grid.style.setProperty('--cell-size', `${cellPx}px`);
  grid.style.gridTemplateColumns = `repeat(${size}, var(--cell-size))`;

  // Keep the coordinate labels in sync with the current grid size/scale.
  // Works the same way in both Arcade and Free Play — Free Play's board
  // can grow (expand_board on the server), and this re-render picks that
  // up automatically since it's driven by board.length every time.
  renderGridLabels(size, cellPx);

  // Full re-render
  grid.innerHTML = '';
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      const cell = document.createElement('div');
      cell.className = 'grid-cell';
      cell.dataset.row = r;
      cell.dataset.col = c;

      const type = board[r][c];
      if (type) {
        cell.classList.add(cellClass(type));
        cell.textContent = type;
        if (placedAt && placedAt[0] === r && placedAt[1] === c) {
          cell.classList.add('just-placed');
        }
      } else if (selectedBuilding && !isDemolishMode && validSet.has(`${r},${c}`)) {
        cell.classList.add('valid-cell');
      }

      attachCellListeners(cell, r, c);
      grid.appendChild(cell);
    }
  }
}

function attachCellListeners(cell, r, c) {
  cell.addEventListener('click', () => handleCellClick(r, c));

  if (isDemolishMode) {
    cell.addEventListener('mouseenter', () => {
      if (state.board[r][c]) cell.classList.add('demolish-hover');
    });
    cell.addEventListener('mouseleave', () => {
      cell.classList.remove('demolish-hover');
    });
  }
}

function refreshHighlights() {
  const cells = document.querySelectorAll('.grid-cell');
  cells.forEach(cell => {
    const r = +cell.dataset.row;
    const c = +cell.dataset.col;
    const type = state.board[r][c];

    cell.classList.remove('valid-cell', 'demolish-hover');

    if (!type && selectedBuilding && !isDemolishMode && validSet.has(`${r},${c}`)) {
      cell.classList.add('valid-cell');
    }
  });
}

// ── Cell interaction ──────────────────────────────────────────────

async function handleCellClick(row, col) {
  if (actionInFlight) return;

  if (isDemolishMode) {
    if (!state.board[row][col]) return;
    actionInFlight = true;
    try {
      await demolishBuilding(row, col);
    } finally {
      actionInFlight = false;
    }
    return;
  }
  if (!selectedBuilding) return;
  if (state.board[row][col]) return;
  if (!validSet.has(`${row},${col}`)) return;

  actionInFlight = true;
  try {
    await placeBuilding(row, col);
  } finally {
    actionInFlight = false;
  }
}

async function placeBuilding(row, col) {
  try {
    const res = await fetch('/api/place', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ row, col, building: selectedBuilding }),
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.error || 'Cannot place here.', 'error');
      return;
    }

    const data = await res.json();
    selectedBuilding = null;

    applyState(data, { placedAt: [row, col] });

    if (data.notifications && data.notifications.length > 0) {
      data.notifications.forEach((message, index) => {
        queueBonusTaskPopup('Challenge Complete', message.replace(/^[^\w]+/, '').trim());
      });
    }

    if (data.game_over) showGameOver(data);
  } catch (e) {
    showToast('Something went wrong — resyncing…', 'error');
    await resyncState();
  }
}

async function resyncState() {
  try {
    const res = await fetch('/api/state');
    if (res.ok) applyState(await res.json());
  } catch (e) {
    // give up quietly; user can refresh manually
  }
}

async function demolishBuilding(row, col) {
  try {
    // Kyston: this sends the selected occupied cell to the backend so one
    // building can be removed and the board can open up for a better move.
    const res = await fetch('/api/demolish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ row, col }),
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.error || 'Cannot demolish.', 'error');
      return;
    }

    const data = await res.json();
    applyState(data);

    if (data.game_over) showGameOver(data);
  } catch (e) {
    showToast('Something went wrong — resyncing…', 'error');
    await resyncState();
  }
}

// ── Demolish toggle ───────────────────────────────────────────────

function toggleDemolish() {
  isDemolishMode = !isDemolishMode;
  if (isDemolishMode) selectedBuilding = null;
  updateDemolishBtn(isDemolishMode);
  // Kyston: the hint reminds players that demolishing is a special action
  // and shows the 1-coin cost in limited modes before they click the grid.
  document.getElementById('panel-hint').textContent = isDemolishMode
    ? `Click a building on the grid to demolish it${isLimitedMode(state.mode) ? ' (costs 1 coin).' : '.'}`
    : 'Select a building, then click a cell.';
  renderBoard(state); // re-render to attach demolish listeners
}

function updateDemolishBtn(active) {
  const btn = document.getElementById('demolish-btn');
  btn.classList.toggle('active', active);
  btn.textContent = active ? '✕ Stop demolishing' : '🔨 Demolish Building';
}

// ── Challenge event popup and feed ─────────────────────────────────

function queueEventPopups(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return;
  messages.forEach(message => {
    if (message && typeof message === 'object') eventPopupQueue.push(message);
  });
  showNextEventPopup();
}

function popupDurationFor(message) {
  if (message.popup_type === 'disaster') return EVENT_POPUP_DURATION_DISASTER;
  if (message.popup_type === 'warning') return EVENT_POPUP_DURATION_WARNING;
  return EVENT_POPUP_DURATION_NORMAL;
}

function showNextEventPopup() {
  if (eventPopupActive || eventPopupQueue.length === 0) return;

  const popup = document.getElementById('city-event-popup');
  if (!popup) return;

  const message = eventPopupQueue.shift();
  eventPopupActive = true;
  popup.classList.remove('hidden', 'city-event-popup-closing', 'city-event-popup-normal', 'city-event-popup-warning', 'city-event-popup-disaster');
  popup.classList.add(`city-event-popup-${message.popup_type || 'normal'}`);

  set('city-event-popup-category', String(message.category || 'City Event').toUpperCase());
  set('city-event-popup-title', message.title || 'City Event');
  set('city-event-popup-description', message.description || 'The city event has been updated.');
  set('city-event-popup-effect', message.effect || 'Check the City Event Feed for details.');

  const countdown = document.getElementById('city-event-popup-countdown');
  const remaining = Number(message.turns_remaining);
  if (countdown && Number.isFinite(remaining) && remaining > 0) {
    countdown.textContent = `${remaining} turn${remaining === 1 ? '' : 's'} remaining`;
    countdown.classList.remove('hidden');
  } else if (countdown) {
    countdown.textContent = '';
    countdown.classList.add('hidden');
  }

  clearTimeout(eventPopupTimer);
  eventPopupTimer = setTimeout(dismissEventPopup, popupDurationFor(message));
}

function dismissEventPopup() {
  if (!eventPopupActive) return;
  const popup = document.getElementById('city-event-popup');
  clearTimeout(eventPopupTimer);

  if (!popup) {
    eventPopupActive = false;
    showNextEventPopup();
    return;
  }

  popup.classList.add('city-event-popup-closing');
  const finishClose = () => {
    popup.classList.add('hidden');
    popup.classList.remove('city-event-popup-closing');
    eventPopupActive = false;
    showNextEventPopup();
  };

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    finishClose();
  } else {
    setTimeout(finishClose, 220);
  }
}

function formatEventTime(timestamp) {
  const date = timestamp ? new Date(timestamp) : new Date();
  const validDate = Number.isNaN(date.getTime()) ? new Date() : date;
  return validDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function createEventFeedEntry(entry) {
  const item = document.createElement('article');
  const status = String(entry.status || 'occurred').toLowerCase();
  item.className = `g-event-entry g-event-${status}`;
  item.dataset.eventId = String(entry.id || 'event');

  const meta = document.createElement('div');
  meta.className = 'g-event-meta';

  const time = document.createElement('span');
  time.className = 'g-event-timestamp';
  time.textContent = formatEventTime(entry.timestamp);

  const turn = document.createElement('span');
  turn.className = 'g-event-turn';
  turn.textContent = `Turn ${entry.turn || 1}`;

  const statusLabel = document.createElement('span');
  statusLabel.className = 'g-event-status';
  statusLabel.textContent = status.toUpperCase();

  meta.append(time, turn, statusLabel);

  const title = document.createElement('h3');
  title.className = 'g-event-title';
  title.textContent = entry.title || 'City Event';

  const message = document.createElement('p');
  message.className = 'g-event-message';
  message.textContent = entry.message || 'Event details are unavailable.';

  item.append(meta, title, message);

  if (entry.countdown) {
    const countdown = document.createElement('p');
    countdown.className = 'g-event-countdown';
    countdown.textContent = entry.countdown;
    item.appendChild(countdown);
  }

  return item;
}

function renderChallengeEventFeed(s) {
  const panel = document.getElementById('challenge-event-panel');
  const feed = document.getElementById('challenge-event-feed');
  if (!panel || !feed) return;

  const isChallenge = s.mode === CHALLENGE_MODE;
  panel.classList.toggle('hidden', !isChallenge);
  if (!isChallenge) {
    feed.replaceChildren();
    return;
  }

  const challengeState = s.challenge_state || {};
  const entries = [];

  (challengeState.pending_events || []).forEach(event => {
    const remaining = Math.max(0, Number(event.remaining_turns) || 0);
    const title = event.type === 'tornado' ? 'Tornado Warning' : (event.title || 'Upcoming Event');
    entries.push({
      id: event.id,
      status: 'upcoming',
      timestamp: event.announced_at,
      turn: event.announced_turn,
      title,
      message: event.type === 'tax_collector'
        ? `Tax Collector will collect 10 coins in ${remaining} turn${remaining === 1 ? '' : 's'}.`
        : `A tornado may strike in ${remaining} turn${remaining === 1 ? '' : 's'}.`,
      countdown: `Due on turn ${event.due_turn}`,
      priority: 3,
    });
  });

  (challengeState.active_effects || []).forEach(effect => {
    const remaining = Math.max(0, Number(effect.turns_remaining) || 0);
    entries.push({
      id: effect.id,
      status: 'active',
      timestamp: effect.announced_at,
      turn: effect.announced_turn,
      title: effect.title || 'Temporary Effect',
      message: effect.message || 'A temporary city modifier is active.',
      countdown: `${remaining} turn${remaining === 1 ? '' : 's'} remaining`,
      priority: 2,
    });
  });

  (challengeState.event_history || []).slice().reverse().forEach(event => {
    entries.push({
      id: event.id,
      status: event.status || 'occurred',
      timestamp: event.occurred_at,
      turn: event.turn,
      title: event.title || 'City Event',
      message: event.message || 'The event was completed.',
      priority: 1,
    });
  });

  const visibleEntries = entries
    .sort((left, right) => right.priority - left.priority)
    .slice(0, EVENT_FEED_LIMIT);

  feed.replaceChildren();
  if (visibleEntries.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'g-event-empty';
    empty.textContent = 'No city events yet. Continue building your city.';
    feed.appendChild(empty);
    return;
  }

  visibleEntries.forEach(entry => feed.appendChild(createEventFeedEntry(entry)));
}

// ── Save ──────────────────────────────────────────────────────────

function openSaveModal() {
  document.getElementById('saveFilename').value = `save-${Date.now()}`;
  document.getElementById('saveModal').classList.remove('hidden');
  setTimeout(() => document.getElementById('saveFilename').select(), 50);
}

async function doSave() {
  const filename = document.getElementById('saveFilename').value.trim();
  if (!filename) return;

  // Theresa: send the current city state to the save endpoint so the
  // player can continue this run later without losing progress.
  const res = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename }),
  });
  if (res.ok) {
    hasSavedGame = true;
    closeModalById('saveModal');
    showToast('Game saved!', 'ok');
  } else {
    const err = await res.json().catch(() => ({}));
    showToast(err.error || 'Failed to save.', 'error');
  }
}

// ── Game over ─────────────────────────────────────────────────────
// Every score is saved to history under the logged-in account.
// The modal copy still tells the player up front whether the run is
// tracking for the Top 10 (data.qualifies is a pre-submission estimate).

function showGameOver(data) {
  const reasons = {
    arcade_full: 'The board is full!',
    arcade_coins: 'You ran out of coins!',
    freeplay_loss: 'The city made a loss for 20 consecutive turns.',
  };
  let reason = data.game_over_reason || data.summary || '';
  if (!reason) {
    if (data.mode === 'freeplay') reason = reasons.freeplay_loss;
    else if (data.coins === 0) reason = reasons.arcade_coins;
    else reason = reasons.arcade_full;
  }

  set('gameover-score', data.score.toLocaleString());
  set('gameover-reason', reason);

  const nameEntry = document.getElementById('name-entry');
  const saveScoreBtn = document.getElementById('save-score-btn');
  const backMainMenuBtn = document.getElementById('back-main-menu-btn');
  nameEntry.classList.remove('hidden');
  if (saveScoreBtn) saveScoreBtn.classList.remove('hidden');
  if (backMainMenuBtn) backMainMenuBtn.textContent = 'Back Main Menu';

  const nameEntryText = nameEntry.querySelector('p');
  if (nameEntryText) {
    nameEntryText.textContent = 'Would you like to save your score?';
  }

  document.getElementById('gameOverModal').classList.remove('hidden');
}

async function submitScore() {
  // Theresa: after a finished or manually ended run, this keeps the final
  // result and lets qualifying scores reach the global leaderboard.
  const res = await fetch('/api/submit_score', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  const result = await res.json();

  document.getElementById('name-entry').classList.add('hidden');
  document.getElementById('save-score-btn').classList.add('hidden');
  document.getElementById('gameOverModal').classList.add('hidden');

  sessionStorage.setItem('menuToastMessage', 'Saved successfully!');
  sessionStorage.setItem('menuToastType', 'ok');
  sessionStorage.setItem('menuToastPosition', 'top');
  sessionStorage.setItem('menuToastDuration', '3000');
  goToMainMenu();
}

// --- NEW: Manual End Game Logic (A2S-[TICKET-NUMBER]) ---
function triggerManualEnd() {
    const confirmMessage = hasSavedGame
      ? 'Are you sure you want to end the game?'
      : 'Are you sure you want to end the game?<br><strong>Any unsaved files will be lost.</strong>';

    openConfirmModal(
      'End Game',
      confirmMessage,
      () => {
        if (hasSavedGame) {
          goToMainMenu();
          return;
        }

        // Theresa: ending early asks the backend for a final summary, then
        // shows the same score-save choice the player gets at normal game over.
        fetch('/api/end_game_early', { method: 'POST' })
          .then(response => response.json())
          .then(data => {
            if (data.error) {
              showToast(data.error, 'error');
              return;
            }

            document.getElementById('gameover-reason').innerText = data.summary;
            document.getElementById('gameover-score').innerText = Number(data.score).toLocaleString();
            document.getElementById('score-save-message').innerText = 'Would you like to save your score?';
            document.getElementById('name-entry').classList.remove('hidden');
            document.getElementById('save-score-btn').classList.remove('hidden');
            document.getElementById('back-main-menu-btn').textContent = 'Back Main Menu';
            document.getElementById('gameOverModal').classList.remove('hidden');
          })
          .catch(error => {
            console.error('Error ending game:', error);
            showToast('Failed to end game.', 'error');
          });
      },
      'End Game',
      true
    );
}
// ---------------------------------------------------------

function goToMainMenu() {
  sessionStorage.setItem('jumpToMainMenu', '1');
  navigateWithMusicFade('/');
}

// ── Modals ────────────────────────────────────────────────────────

function closeModal(event, id) {
  if (event.target === event.currentTarget) closeModalById(id);
}
function closeModalById(id) {
  document.getElementById(id).classList.add('hidden');
}

// ── Toast ─────────────────────────────────────────────────────────

function showToast(msg, type = 'ok', position = 'bottom') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = msg;
  const verticalPosition = position === 'top' ? 'top:24px;' : 'bottom:24px;';
  t.style.cssText = `
    position:fixed; ${verticalPosition} left:50%; transform:translateX(-50%);
    padding:10px 20px; border-radius:8px; font-size:13px; font-weight:500;
    z-index:200; animation: fadein .15s ease;
    background:${type === 'error' ? 'var(--negative)' : '#22c55e'};
    color:#fff; box-shadow:0 4px 16px rgba(0,0,0,.4);
  `;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2400);
}

// ── Helpers ───────────────────────────────────────────────────────

function set(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function toggle(id, show) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('hidden', !show);
}

