const API = '/api';

const $ = (selector) => document.querySelector(selector);

const els = {
  status: $('#status'),
  addForm: $('#add-form'),
  inventory: $('#inventory'),
  refresh: $('#refresh'),
  toast: $('#toast'),
};

let toastTimer;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function formatGrams(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  if (Math.abs(num) < 1) return '~0 g';
  return `~${Math.round(num)} g`;
}

function showToast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.classList.toggle('error', isError);
  els.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove('show'), 2800);
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function makeOpId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function renderLots(items) {
  if (!items.length) {
    els.inventory.innerHTML = '<p class="empty">Nothing here yet. Add something above.</p>';
    return;
  }
  els.inventory.innerHTML = items.map((item) => `
    <article class="lot">
      <div class="lot-head">
        <strong>${escapeHtml(item.product_name)}</strong>
        <span class="grams">${formatGrams(item.grams_remaining)}</span>
      </div>
      <div class="lot-meta">
        ${item.location ? `${escapeHtml(item.location)} · ` : ''}added ${escapeHtml(item.added_date)}
      </div>
      <div class="lot-actions">
        <button data-action="use" data-id="${escapeHtml(item.lot_id)}">Use grams</button>
        <button data-action="set" data-id="${escapeHtml(item.lot_id)}">Set left</button>
      </div>
    </article>
  `).join('');
}

async function loadInventory() {
  try {
    els.status.textContent = 'syncing…';
    const items = await request('/inventory');
    renderLots(items);
    els.status.textContent = 'ok';
  } catch (error) {
    els.status.textContent = 'error';
    showToast(error.message, true);
  }
}

async function handleAdd(event) {
  event.preventDefault();
  const form = new FormData(els.addForm);
  const payload = {
    name: (form.get('name') || '').trim(),
    qty_g: form.get('qty_g'),
    location: (form.get('location') || '').trim() || null,
    gtin: (form.get('gtin') || '').trim() || null,
    op_id: makeOpId(),
  };
  try {
    await request('/lots', { method: 'POST', body: JSON.stringify(payload) });
    els.addForm.reset();
    showToast(`Added ${payload.name}`);
    await loadInventory();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function handleAction(action, lotId) {
  if (action === 'use') {
    const raw = window.prompt('Grams used:');
    if (raw == null) return;
    const grams = Number(raw);
    if (!Number.isFinite(grams) || grams <= 0) {
      showToast('Enter a positive number of grams.', true);
      return;
    }
    try {
      await request(`/lots/${lotId}/use`, {
        method: 'POST',
        body: JSON.stringify({ grams_used: grams, method: 'ESTIMATE', op_id: makeOpId() }),
      });
      showToast('Recorded use');
      await loadInventory();
    } catch (error) {
      showToast(error.message, true);
    }
    return;
  }
  if (action === 'set') {
    const raw = window.prompt('Grams left:');
    if (raw == null) return;
    const grams = Number(raw);
    if (!Number.isFinite(grams) || grams < 0) {
      showToast('Enter the grams left (0 or more).', true);
      return;
    }
    try {
      await request(`/lots/${lotId}/remaining`, {
        method: 'POST',
        body: JSON.stringify({ grams_remaining: grams, method: 'ESTIMATE', op_id: makeOpId() }),
      });
      showToast('Updated');
      await loadInventory();
    } catch (error) {
      showToast(error.message, true);
    }
  }
}

els.addForm.addEventListener('submit', handleAdd);
els.refresh.addEventListener('click', loadInventory);
els.inventory.addEventListener('click', (event) => {
  const button = event.target.closest('[data-action]');
  if (button) handleAction(button.dataset.action, button.dataset.id);
});

loadInventory();
