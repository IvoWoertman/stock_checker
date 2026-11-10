const API = '/api';

const $ = (selector) => document.querySelector(selector);

const els = {
  status: $('#status'),
  addForm: $('#add-form'),
  inventory: $('#inventory'),
  refresh: $('#refresh'),
  toast: $('#toast'),
  scanBtn: $('#scan-btn'),
  scanInline: $('#scan-inline'),
  scanModal: $('#scan-modal'),
  scanClose: $('#scan-close'),
  scanStatus: $('#scan-status'),
  shopForm: $('#shop-form'),
  shopping: $('#shopping'),
};

let toastTimer;
let scanner = null;

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function fmtGrams(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) < 1) return '~0 g';
  return `~${Math.round(n)} g`;
}

function expiryBadge(bestBefore) {
  if (!bestBefore) return '';
  const d = new Date(`${bestBefore}T00:00:00`);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const days = Math.round((d - today) / 86400000);
  if (days < 0) return `<span class="expiry exp-overdue">expired ${Math.abs(days)}d ago</span>`;
  if (days === 0) return '<span class="expiry exp-soon">expires today</span>';
  if (days <= 7) return `<span class="expiry exp-soon">${days}d left</span>`;
  return `<span class="expiry">best before ${esc(bestBefore)}</span>`;
}

function showToast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.classList.toggle('error', isError);
  els.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove('show'), 3000);
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function opId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function isUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

// ---- inventory rendering -------------------------------------------------

function renderProducts(products) {
  if (!products.length) {
    els.inventory.innerHTML = '<p class="empty">Nothing in stock yet. Add something above or scan a package.</p>';
    return;
  }
  els.inventory.innerHTML = products.map((p) => `
    <article class="product" data-id="${esc(p.product_id)}">
      <button class="product-head" data-expand="${esc(p.product_id)}">
        <div class="product-title">
          <strong>${esc(p.name)}</strong>
          ${p.category ? `<span class="badge">${esc(p.category)}</span>` : ''}
        </div>
        <div class="product-meta">
          <span>${p.lot_count} ${Number(p.lot_count) === 1 ? 'package' : 'packages'}</span>
          <span class="grams">${fmtGrams(p.total_grams)}</span>
        </div>
      </button>
      <div class="lots" id="lots-${esc(p.product_id)}" hidden></div>
    </article>
  `).join('');
}

async function toggleProduct(productId) {
  const box = document.getElementById(`lots-${productId}`);
  if (!box) return;
  if (!box.hidden) { box.hidden = true; return; }
  try {
    const lots = await request(`/products/${productId}/lots`);
    box.innerHTML = lots.length ? lots.map((l) => `
      <div class="lot-row">
        <div class="lot-info">
          <span class="grams">${fmtGrams(l.grams_remaining)}</span>
          <span class="lot-meta">
            ${l.location ? `${esc(l.location)} · ` : ''}${esc(l.added_date)}
          </span>
          ${expiryBadge(l.best_before_date)}
        </div>
        <div class="lot-actions">
          <button data-act="use" data-id="${esc(l.lot_id)}">Use</button>
          <button data-act="set" data-id="${esc(l.lot_id)}">Set</button>
          <button data-act="discard" data-id="${esc(l.lot_id)}" title="Throw away">✕</button>
        </div>
      </div>
    `).join('') : '<p class="empty">No active packages.</p>';
    box.hidden = false;
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadInventory() {
  try {
    els.status.textContent = 'syncing…';
    const products = await request('/inventory');
    renderProducts(products);
    els.status.textContent = 'ok';
  } catch (error) {
    els.status.textContent = 'error';
    showToast(error.message, true);
  }
}

// ---- actions -------------------------------------------------------------

async function handleAdd(event) {
  event.preventDefault();
  const form = new FormData(els.addForm);
  const payload = {
    name: (form.get('name') || '').trim(),
    qty_g: form.get('qty_g'),
    location: (form.get('location') || '').trim() || null,
    gtin: (form.get('gtin') || '').trim() || null,
    shelf_life_days: (form.get('shelf_life_days') || '').trim() || null,
    op_id: opId(),
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

async function useLot(lotId, gramsUsed) {
  await request(`/lots/${lotId}/use`, {
    method: 'POST',
    body: JSON.stringify({ grams_used: gramsUsed, method: 'ESTIMATE', op_id: opId() }),
  });
}

async function handleAction(action, lotId) {
  const promptText = action === 'use'
    ? 'Grams used:'
    : action === 'set' ? 'Grams left:' : null;

  if (action === 'discard') {
    if (!window.confirm('Throw away everything left in this package?')) return;
    try {
      await request(`/lots/${lotId}/discard`, { method: 'POST', body: JSON.stringify({ op_id: opId() }) });
      showToast('Discarded');
      await loadInventory();
      document.querySelectorAll('.lots').forEach((box) => { box.hidden = true; });
    } catch (error) { showToast(error.message, true); }
    return;
  }

  const raw = window.prompt(promptText);
  if (raw == null) return;
  const grams = Number(raw);
  if (!Number.isFinite(grams) || grams < 0) {
    showToast('Enter a valid number of grams.', true);
    return;
  }
  if (action === 'use' && grams <= 0) {
    showToast('Enter a positive number of grams.', true);
    return;
  }
  try {
    if (action === 'use') {
      await useLot(lotId, grams);
    } else {
      await request(`/lots/${lotId}/remaining`, {
        method: 'POST',
        body: JSON.stringify({ grams_remaining: grams, method: 'ESTIMATE', op_id: opId() }),
      });
    }
    showToast('Updated');
    await loadInventory();
    document.querySelectorAll('.lots').forEach((box) => { box.hidden = true; });
  } catch (error) { showToast(error.message, true); }
}

// ---- shopping list -------------------------------------------------------

async function loadShopping() {
  try {
    renderShopping(await request('/shopping'));
  } catch (error) { /* non-fatal */ }
}

function renderShopping(items) {
  if (!items.length) {
    els.shopping.innerHTML = '<p class="empty">Nothing to buy.</p>';
    return;
  }
  els.shopping.innerHTML = items.map((it) => `
    <div class="shop-row">
      <span class="shop-name">${esc(it.name)}${it.note ? ` <small>· ${esc(it.note)}</small>` : ''}</span>
      <button class="shop-done" data-id="${esc(it.item_id)}" title="Bought">✓</button>
    </div>`).join('');
}

async function handleShopAdd(event) {
  event.preventDefault();
  const form = new FormData(els.shopForm);
  const name = (form.get('shop-name') || '').trim();
  if (!name) return;
  try {
    await request('/shopping', { method: 'POST', body: JSON.stringify({ name }) });
    els.shopForm.reset();
    await loadShopping();
  } catch (error) { showToast(error.message, true); }
}

async function handleShopDone(itemId) {
  try {
    await request(`/shopping/${itemId}/done`, { method: 'POST', body: '{}' });
    await loadShopping();
  } catch (error) { showToast(error.message, true); }
}

// ---- scanning ------------------------------------------------------------

function fillAddForm(name, grams, gtin, shelfLifeDays) {
  const form = els.addForm;
  if (name != null) form.elements.name.value = name;
  if (grams != null) form.elements.qty_g.value = grams;
  if (gtin != null) form.elements.gtin.value = gtin;
  if (shelfLifeDays != null) form.elements.shelf_life_days.value = shelfLifeDays;
}

async function lookupOff(code) {
  try {
    const response = await fetch(`https://world.openfoodfacts.org/api/v2/product/${encodeURIComponent(code)}.json`);
    if (!response.ok) return null;
    const data = await response.json();
    const product = data.product || {};
    const name = product.product_name_nl || product.product_name || product.generic_name || null;
    return { name, grams: parseProductQuantity(product) };
  } catch {
    return null;
  }
}

function parseProductQuantity(product) {
  // product_quantity is a number in grams (or ml for liquids). Prefer it.
  const numeric = Number(product && product.product_quantity);
  if (Number.isFinite(numeric) && numeric > 0) return Math.round(numeric);
  // Fall back to parsing a human string like "500 g" from `quantity`.
  const match = /(\d+(?:[.,]\d+)?)\s*g\b/i.exec((product && product.quantity) || '');
  if (match) return Math.round(Number(match[1].replace(',', '.')));
  return null;
}

async function handleLotScan(lotId) {
  try {
    const data = await request(`/lots/${lotId}`);
    const lot = data.lot;
    if (!lot) { showToast('Unknown label', true); return; }
    const raw = window.prompt(`${lot.product_name} — ${fmtGrams(lot.grams_remaining)} left. Grams used:`);
    if (raw == null) return;
    const grams = Number(raw);
    if (!Number.isFinite(grams) || grams <= 0) { showToast('Enter a positive number.', true); return; }
    await useLot(lotId, grams);
    showToast('Recorded use');
    await loadInventory();
  } catch (error) { showToast(error.message, true); }
}

async function handleBarcodeScan(code) {
  try {
    const data = await request(`/products/lookup?code=${encodeURIComponent(code)}`);
    if (data.product) {
      fillAddForm(data.product.name, data.product.usual_package_size_g, code, data.product.default_best_before_days);
      showToast(`Found: ${data.product.name}`);
      return;
    }
    const off = await lookupOff(code);
    if (off && off.name) {
      fillAddForm(off.name, off.grams, code, null);
      showToast(off.grams ? `Found online: ${off.name} (~${off.grams} g)` : `Found online: ${off.name}`);
    } else {
      fillAddForm('', null, code, null);
      showToast('New barcode — add a name.', true);
    }
  } catch (error) { showToast(error.message, true); }
}

async function onScan(text) {
  stopScan();
  if (isUuid(text)) await handleLotScan(text);
  else await handleBarcodeScan(text);
}

async function startScan() {
  els.scanModal.hidden = false;
  els.scanStatus.textContent = 'Starting camera…';
  try {
    scanner = new Html5Qrcode('qr-reader');
    const formats = [
      Html5QrcodeSupportedFormats.QR_CODE,
      Html5QrcodeSupportedFormats.EAN_13,
      Html5QrcodeSupportedFormats.EAN_8,
      Html5QrcodeSupportedFormats.UPC_A,
      Html5QrcodeSupportedFormats.UPC_E,
      Html5QrcodeSupportedFormats.CODE_128,
      Html5QrcodeSupportedFormats.CODE_39,
    ];
    await scanner.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 240, height: 240 }, formatsToSupport: formats },
      (text) => onScan(text),
      () => {},
    );
    els.scanStatus.textContent = 'Point the camera at a barcode or label QR.';
  } catch (error) {
    els.scanStatus.textContent = `Camera unavailable: ${error.message}`;
  }
}

function stopScan() {
  if (scanner) {
    scanner.stop().then(() => scanner.clear()).catch(() => {});
    scanner = null;
  }
  els.scanModal.hidden = true;
}

// ---- wiring --------------------------------------------------------------

els.addForm.addEventListener('submit', handleAdd);
els.refresh.addEventListener('click', loadInventory);
els.scanBtn.addEventListener('click', startScan);
els.scanInline.addEventListener('click', startScan);
els.scanClose.addEventListener('click', stopScan);
els.scanModal.addEventListener('click', (event) => {
  if (event.target === els.scanModal) stopScan();
});
els.inventory.addEventListener('click', (event) => {
  const expand = event.target.closest('[data-expand]');
  if (expand) { toggleProduct(expand.dataset.expand); return; }
  const action = event.target.closest('[data-act]');
  if (action) handleAction(action.dataset.act, action.dataset.id);
});
els.shopForm.addEventListener('submit', handleShopAdd);
els.shopping.addEventListener('click', (event) => {
  const btn = event.target.closest('.shop-done');
  if (btn) handleShopDone(btn.dataset.id);
});

loadInventory();
loadShopping();
