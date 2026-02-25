/* Admin-Dashboard — Client-Logik */

// ── Toast-Meldungen ────────────────────────────────────────────────────────
let _toastTimer;
function showToast(msg, type = "info") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  el.hidden = false;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

// ── API-Hilfsfunktion ──────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  };
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
  return data;
}

// ── Pool laden und rendern ─────────────────────────────────────────────────
async function loadPool() {
  try {
    const data = await api("GET", "/admin/api/pool");
    document.getElementById("status-count").textContent = data.count;
    document.getElementById("status-updated").textContent =
      data.last_updated ? new Date(data.last_updated).toLocaleString("de-DE") : "–";

    const list = document.getElementById("pool-list");
    list.innerHTML = "";

    if (data.answers.length === 0) {
      list.innerHTML = '<li class="adm-pool-item adm-muted">Pool ist leer.</li>';
      return;
    }

    data.answers.forEach((text, idx) => {
      const li = document.createElement("li");
      li.className = "adm-pool-item";
      li.innerHTML = `
        <span class="adm-pool-item__idx">${idx + 1}</span>
        <span class="adm-pool-item__text">${escHtml(text)}</span>
        <button class="adm-pool-item__del" title="Löschen" onclick="deleteAnswer(${idx})">✕</button>
      `;
      list.appendChild(li);
    });
  } catch (e) {
    showToast(`Fehler beim Laden: ${e.message}`, "error");
  }
}

// ── Antwort löschen ────────────────────────────────────────────────────────
async function deleteAnswer(index) {
  try {
    await api("DELETE", `/admin/api/pool/${index}`);
    await loadPool();
  } catch (e) {
    showToast(`Löschen fehlgeschlagen: ${e.message}`, "error");
  }
}

// ── Generieren ─────────────────────────────────────────────────────────────
async function generateAnswers() {
  showToast("Generiere neue Antworten…");
  try {
    const data = await api("POST", "/admin/api/generate");
    showToast(`${data.generated} neue Antworten generiert. Pool: ${data.total}`, "success");
    await loadPool();
  } catch (e) {
    showToast(`Fehler: ${e.message}`, "error");
  }
}

// ── Rotieren ───────────────────────────────────────────────────────────────
async function rotatePool() {
  showToast("Pool wird rotiert…");
  try {
    const data = await api("POST", "/admin/api/rotate");
    showToast(`${data.removed} entfernt, ${data.added} hinzugefügt. Pool: ${data.total}`, "success");
    await loadPool();
  } catch (e) {
    showToast(`Fehler: ${e.message}`, "error");
  }
}

// ── Provider wechseln ──────────────────────────────────────────────────────
async function switchProvider() {
  const name = document.getElementById("provider-select").value;
  try {
    await api("POST", "/admin/api/provider", { provider: name });
    showToast(`Provider gewechselt zu: ${name}`, "success");
  } catch (e) {
    showToast(`Fehler: ${e.message}`, "error");
  }
}

// ── Fallback-Provider setzen ───────────────────────────────────────────────
async function switchFallback() {
  const name = document.getElementById("fallback-select").value;
  try {
    await api("POST", "/admin/api/fallback", { provider: name });
    showToast(name ? `Fallback gesetzt: ${name}` : "Fallback deaktiviert", "success");
  } catch (e) {
    showToast(`Fehler: ${e.message}`, "error");
  }
}

// ── API-Key speichern ──────────────────────────────────────────────────────
async function saveKey(envVar) {
  const input = document.getElementById(`key-${envVar}`);
  const value = input.value.trim();
  if (!value) {
    showToast("Bitte einen API-Key eingeben.", "error");
    return;
  }
  try {
    await api("POST", "/admin/api/keys", { env_var: envVar, value });
    input.value = "";
    input.placeholder = `${envVar} (gespeichert ✓)`;
    showToast(`${envVar} gespeichert.`, "success");
  } catch (e) {
    showToast(`Fehler: ${e.message}`, "error");
  }
}

// ── Config neu laden ───────────────────────────────────────────────────────
async function reloadConfig() {
  try {
    const data = await api("POST", "/admin/api/reload");
    showToast(`Config neu geladen. Provider: ${data.provider}`, "success");
  } catch (e) {
    showToast(`Fehler: ${e.message}`, "error");
  }
}

// ── Server-Log ─────────────────────────────────────────────────────────────
let _logTimer = null;

async function loadLogs() {
  try {
    const data = await api("GET", "/admin/api/logs");
    const el = document.getElementById("log-output");
    if (!data.logs.length) {
      el.textContent = "(noch keine Einträge)";
      return;
    }
    el.innerHTML = [...data.logs].reverse().map(l =>
      `<div class="adm-log-line adm-log-line--${l.level.toLowerCase()}">` +
      `<span class="adm-log-time">${escHtml(l.time)}</span>` +
      `<span class="adm-log-level">${l.level}</span>` +
      `<span>${escHtml(l.message)}</span>` +
      `</div>`
    ).join("");
  } catch (_) { /* still show old entries on network error */ }
}

document.addEventListener("DOMContentLoaded", () => {
  const cb = document.getElementById("log-auto");
  if (!cb) return;
  const start = () => { _logTimer = setInterval(loadLogs, 5000); };
  const stop  = () => { clearInterval(_logTimer); _logTimer = null; };
  cb.addEventListener("change", () => cb.checked ? start() : stop());
  start();
});

// ── Prompt laden und speichern ─────────────────────────────────────────────
async function loadPrompt() {
  try {
    const data = await api("GET", "/admin/api/prompt");
    document.getElementById("prompt-text").value = data.prompt;
  } catch (e) {
    showToast(`Prompt laden fehlgeschlagen: ${e.message}`, "error");
  }
}

async function savePrompt() {
  const text = document.getElementById("prompt-text").value;
  try {
    await api("POST", "/admin/api/prompt", { prompt: text });
    showToast("Prompt gespeichert.", "success");
  } catch (e) {
    showToast(`Fehler: ${e.message}`, "error");
  }
}

// ── Speech/Pool-Konfiguration ──────────────────────────────────────────────
async function loadSpeechConfig() {
  try {
    const d = await api("GET", "/admin/api/config");
    document.getElementById("cfg-refresh").value = d.auto_refresh_seconds;
    document.getElementById("cfg-rotate").value  = d.auto_rotate_hours;
    document.getElementById("cfg-pmin").value    = d.pool.min_size;
    document.getElementById("cfg-pmax").value    = d.pool.max_size;
    document.getElementById("cfg-apr").value     = d.pool.answers_per_request;
  } catch (e) {
    showToast(`Konfiguration laden fehlgeschlagen: ${e.message}`, "error");
  }
}

async function saveSpeechConfig() {
  try {
    await api("POST", "/admin/api/config", {
      auto_refresh_seconds:     parseInt(document.getElementById("cfg-refresh").value, 10),
      auto_rotate_hours:        parseInt(document.getElementById("cfg-rotate").value,  10),
      pool_min_size:            parseInt(document.getElementById("cfg-pmin").value,    10),
      pool_max_size:            parseInt(document.getElementById("cfg-pmax").value,    10),
      pool_answers_per_request: parseInt(document.getElementById("cfg-apr").value,     10),
    });
    showToast("Konfiguration gespeichert.", "success");
  } catch (e) {
    showToast(`Fehler: ${e.message}`, "error");
  }
}

// ── HTML escapen ───────────────────────────────────────────────────────────
function escHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
