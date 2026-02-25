const bubbleText = document.getElementById("bubble-text");
const poolInfo   = document.getElementById("pool-info");

function typeWriter(element, text, delay = 28) {
  return new Promise((resolve) => {
    element.textContent = "";
    let i = 0;
    function tick() {
      if (i < text.length) {
        element.textContent += text[i];
        i++;
        setTimeout(tick, delay);
      } else {
        resolve();
      }
    }
    tick();
  });
}

let _updating = false;

async function updateBubbleWithText(text) {
  if (_updating) return;
  _updating = true;

  bubbleText.classList.add("fade-out");
  await new Promise((r) => setTimeout(r, 350));
  bubbleText.classList.remove("fade-out");
  await typeWriter(bubbleText, text);

  _updating = false;
}

// ── Server-Sent Events ──────────────────────────────────────────────────────
const es = new EventSource("/api/stream");

es.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (poolInfo) {
    poolInfo.textContent = `${data.pool_size} Antworten im Pool`;
  }
  updateBubbleWithText(data.answer);
};

es.onerror = () => {
  // SSE-Verbindung unterbrochen → Browser reconnectet automatisch.
  console.warn("[mascot] SSE-Verbindung unterbrochen, warte auf Reconnect…");
};

// ── Vollbild-Steuerung ──────────────────────────────────────────────────────
const _fsBtn = document.getElementById("fullscreen-btn");

function _updateFsBtn() {
  if (!_fsBtn) return;
  _fsBtn.textContent = document.fullscreenElement ? "⛶ Vollbild beenden" : "⛶ Vollbild";
}

if (_fsBtn) {
  _fsBtn.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(console.error);
    } else {
      document.exitFullscreen();
    }
  });
  document.addEventListener("fullscreenchange", _updateFsBtn);
}

// ── Cursor-Auto-Hide (Kiosk-Modus) ─────────────────────────────────────────
let _cursorTimer;

function _showCursor() {
  document.body.classList.remove("cursor-hidden");
  clearTimeout(_cursorTimer);
  _cursorTimer = setTimeout(() => document.body.classList.add("cursor-hidden"), 3000);
}

document.addEventListener("mousemove", _showCursor);
document.addEventListener("mousedown", _showCursor);
_cursorTimer = setTimeout(() => document.body.classList.add("cursor-hidden"), 3000);
