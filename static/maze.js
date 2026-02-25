/* ============================================================
   Maze: Zufallsgenerierung + A* vs BFS vs DFS vs Greedy
   ============================================================ */

// Polyfill für ctx.roundRect (fehlt in älteren Firefox-Versionen)
if (typeof CanvasRenderingContext2D !== "undefined" && !CanvasRenderingContext2D.prototype.roundRect) {
  CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h, r) {
    const radius = Array.isArray(r) ? r[0] : (r || 0);
    this.beginPath();
    this.moveTo(x + radius, y);
    this.lineTo(x + w - radius, y);
    this.arcTo(x + w, y, x + w, y + radius, radius);
    this.lineTo(x + w, y + h - radius);
    this.arcTo(x + w, y + h, x + w - radius, y + h, radius);
    this.lineTo(x + radius, y + h);
    this.arcTo(x, y + h, x, y + h - radius, radius);
    this.lineTo(x, y + radius);
    this.arcTo(x, y, x + radius, y, radius);
    this.closePath();
    return this;
  };
}

const COLS = 79;
const ROWS = 51;
const CELL = 10; // px pro Zelle
const CANVAS_W = COLS * CELL;
const CANVAS_H = ROWS * CELL;
const SHORTCUT_RATE = 0.10; // 10% zufällige Wandentfernungen → mehrere Lösungswege

// Farben (UKM-Design)
const COLOR = {
  wall:       "#003866",
  floor:      "#f4f6f8",
  start:      "#27ae60",
  end:        "#c0392b",
  astarOpen:  "rgba(0, 109, 176, 0.25)",
  astarPath:  "#006db0",
  bfsOpen:    "rgba(230, 126, 34, 0.25)",
  bfsPath:    "#e67e22",
  dfsOpen:    "rgba(39, 174, 96, 0.22)",
  dfsPath:    "#27ae60",
  greedyOpen: "rgba(142, 68, 173, 0.22)",
  greedyPath: "#8e44ad",
};

// Geschwindigkeit (ms pro Frame) — vom Slider gesteuert
let STEP_DELAY = 55;

// ── Maze-Generierung (Recursive Backtracking + zufällige Abkürzungen) ─────
function buildMaze(cols, rows) {
  // 0 = Wand, 1 = Pfad
  const grid = Array.from({ length: rows }, () => new Array(cols).fill(0));

  // Iterativ statt rekursiv (kein Stack-Overflow bei großen Labyrinthen)
  const stack = [[1, 1]];
  grid[1][1] = 1;
  while (stack.length > 0) {
    const [x, y] = stack[stack.length - 1];
    const dirs = [[0,-2],[0,2],[-2,0],[2,0]].sort(() => Math.random() - 0.5);
    let moved = false;
    for (const [dx, dy] of dirs) {
      const nx = x + dx, ny = y + dy;
      if (ny > 0 && ny < rows - 1 && nx > 0 && nx < cols - 1 && grid[ny][nx] === 0) {
        grid[y + Math.floor(dy / 2)][x + Math.floor(dx / 2)] = 1;
        grid[ny][nx] = 1;
        stack.push([nx, ny]);
        moved = true;
        break;
      }
    }
    if (!moved) stack.pop();
  }

  // Zufällige Wände entfernen → Schleifen / mehrere Lösungswege
  for (let y = 2; y < rows - 2; y++) {
    for (let x = 2; x < cols - 2; x++) {
      if (grid[y][x] === 0 && Math.random() < SHORTCUT_RATE) {
        const adj = [[0,1],[0,-1],[1,0],[-1,0]].filter(([dx,dy]) => grid[y+dy][x+dx] === 1);
        if (adj.length >= 2) grid[y][x] = 1;
      }
    }
  }

  grid[1][1] = 1;
  grid[rows - 2][cols - 2] = 1;
  return grid;
}

// ── Hilfsfunktionen ────────────────────────────────────────
const key = (x, y) => `${x},${y}`;
const neighbors = (x, y, grid) => {
  return [[0,1],[1,0],[0,-1],[-1,0]]
    .map(([dx, dy]) => [x+dx, y+dy])
    .filter(([nx, ny]) => ny >= 0 && ny < grid.length && nx >= 0 && nx < grid[0].length && grid[ny][nx] === 1);
};

function reconstructPath(cameFrom, current) {
  const path = [];
  let cur = current;
  while (cur) { path.push(cur); cur = cameFrom.get(key(...cur)); }
  return path.reverse();
}

// ── A* ────────────────────────────────────────────────────
function createAstar(grid, start, end) {
  const heuristic = ([x, y]) => Math.abs(x - end[0]) + Math.abs(y - end[1]);
  const open = [{ node: start, f: heuristic(start), g: 0 }];
  const cameFrom = new Map();
  const gScore = new Map([[key(...start), 0]]);
  const visited = new Set();
  let path = null;
  let done = false;

  function step() {
    if (done || open.length === 0) { done = true; return; }
    open.sort((a, b) => a.f - b.f);
    const { node, g } = open.shift();
    const k = key(...node);
    if (visited.has(k)) return;
    visited.add(k);
    if (node[0] === end[0] && node[1] === end[1]) {
      path = reconstructPath(cameFrom, node);
      done = true;
      return;
    }
    for (const nb of neighbors(...node, grid)) {
      const nk = key(...nb);
      const ng = g + 1;
      if (!gScore.has(nk) || ng < gScore.get(nk)) {
        gScore.set(nk, ng);
        cameFrom.set(nk, node);
        open.push({ node: nb, f: ng + heuristic(nb), g: ng });
      }
    }
  }

  return { step, get visited() { return visited; }, get path() { return path; }, get done() { return done; } };
}

// ── BFS ───────────────────────────────────────────────────
function createBfs(grid, start, end) {
  const queue = [start];
  const cameFrom = new Map([[key(...start), null]]);
  const visited = new Set([key(...start)]);
  let path = null;
  let done = false;

  function step() {
    if (done || queue.length === 0) { done = true; return; }
    const node = queue.shift();
    if (node[0] === end[0] && node[1] === end[1]) {
      path = reconstructPath(cameFrom, node);
      done = true;
      return;
    }
    for (const nb of neighbors(...node, grid)) {
      const nk = key(...nb);
      if (!visited.has(nk)) {
        visited.add(nk);
        cameFrom.set(nk, node);
        queue.push(nb);
      }
    }
  }

  return { step, get visited() { return visited; }, get path() { return path; }, get done() { return done; } };
}

// ── Greedy Best-First ──────────────────────────────────────
function createGreedy(grid, start, end) {
  const heuristic = ([x, y]) => Math.abs(x - end[0]) + Math.abs(y - end[1]);
  const open = [{ node: start, h: heuristic(start) }];
  const cameFrom = new Map([[key(...start), null]]);
  const visited = new Set([key(...start)]);
  let path = null;
  let done = false;

  function step() {
    if (done || open.length === 0) { done = true; return; }
    open.sort((a, b) => a.h - b.h);
    const { node } = open.shift();
    if (node[0] === end[0] && node[1] === end[1]) {
      path = reconstructPath(cameFrom, node);
      done = true;
      return;
    }
    for (const nb of neighbors(...node, grid)) {
      const nk = key(...nb);
      if (!visited.has(nk)) {
        visited.add(nk);
        cameFrom.set(nk, node);
        open.push({ node: nb, h: heuristic(nb) });
      }
    }
  }

  return { step, get visited() { return visited; }, get path() { return path; }, get done() { return done; } };
}

// ── DFS ───────────────────────────────────────────────────
function createDfs(grid, start, end) {
  const stack = [start];
  const cameFrom = new Map([[key(...start), null]]);
  const visited = new Set([key(...start)]);
  let path = null;
  let done = false;

  function step() {
    if (done || stack.length === 0) { done = true; return; }
    const node = stack.pop();
    if (node[0] === end[0] && node[1] === end[1]) {
      path = reconstructPath(cameFrom, node);
      done = true;
      return;
    }
    for (const nb of neighbors(...node, grid)) {
      const nk = key(...nb);
      if (!visited.has(nk)) {
        visited.add(nk);
        cameFrom.set(nk, node);
        stack.push(nb);
      }
    }
  }

  return { step, get visited() { return visited; }, get path() { return path; }, get done() { return done; } };
}

// ── Zeichnen ───────────────────────────────────────────────
function draw(ctx, grid, astar, bfs, dfs, greedy, start, end) {
  const rows = grid.length, cols = grid[0].length;

  ctx.fillStyle = COLOR.wall;
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const px = x * CELL, py = y * CELL;
      if (grid[y][x] === 0) continue;

      ctx.fillStyle = COLOR.floor;
      ctx.fillRect(px, py, CELL, CELL);

      const k = key(x, y);
      if (dfs.visited.has(k)) {
        ctx.fillStyle = COLOR.dfsOpen;
        ctx.fillRect(px, py, CELL, CELL);
      }
      if (bfs.visited.has(k)) {
        ctx.fillStyle = COLOR.bfsOpen;
        ctx.fillRect(px, py, CELL, CELL);
      }
      if (greedy.visited.has(k)) {
        ctx.fillStyle = COLOR.greedyOpen;
        ctx.fillRect(px, py, CELL, CELL);
      }
      if (astar.visited.has(k)) {
        ctx.fillStyle = COLOR.astarOpen;
        ctx.fillRect(px, py, CELL, CELL);
      }
    }
  }

  // DFS-Pfad
  if (dfs.path) {
    ctx.fillStyle = COLOR.dfsPath;
    for (const [x, y] of dfs.path) {
      ctx.fillRect(x * CELL + 3, y * CELL + 3, CELL - 6, CELL - 6);
    }
  }

  // BFS-Pfad
  if (bfs.path) {
    ctx.fillStyle = COLOR.bfsPath;
    for (const [x, y] of bfs.path) {
      ctx.fillRect(x * CELL + 3, y * CELL + 3, CELL - 6, CELL - 6);
    }
  }

  // Greedy-Pfad
  if (greedy.path) {
    ctx.fillStyle = COLOR.greedyPath;
    for (const [x, y] of greedy.path) {
      ctx.fillRect(x * CELL + 3, y * CELL + 3, CELL - 6, CELL - 6);
    }
  }

  // A*-Pfad (oben drauf)
  if (astar.path) {
    ctx.fillStyle = COLOR.astarPath;
    for (const [x, y] of astar.path) {
      ctx.fillRect(x * CELL + 3, y * CELL + 3, CELL - 6, CELL - 6);
    }
  }

  // Start & Ziel
  ctx.fillStyle = COLOR.start;
  ctx.fillRect(start[0] * CELL + 2, start[1] * CELL + 2, CELL - 4, CELL - 4);
  ctx.fillStyle = COLOR.end;
  ctx.fillRect(end[0] * CELL + 2, end[1] * CELL + 2, CELL - 4, CELL - 4);
}

// ── Gewinner-Banner ────────────────────────────────────────
let winnerShown = false;

function drawWinnerBanner(ctx, winner) {
  if (winnerShown) return;
  winnerShown = true;

  const labels = {
    astar:   { text: "A* gewinnt! 🏆",     color: COLOR.astarPath },
    bfs:     { text: "BFS gewinnt! 🏆",    color: COLOR.bfsPath },
    dfs:     { text: "DFS gewinnt! 🏆",    color: COLOR.dfsPath },
    greedy:  { text: "Greedy gewinnt! 🏆", color: COLOR.greedyPath },
    draw:    { text: "Unentschieden! 🤝",  color: "#888" },
  };
  const { text, color } = labels[winner];

  const bw = 260, bh = 44;
  const bx = (CANVAS_W - bw) / 2;
  const by = (CANVAS_H - bh) / 2;

  ctx.fillStyle = "rgba(255,255,255,0.93)";
  ctx.beginPath();
  ctx.roundRect(bx, by, bw, bh, 8);
  ctx.fill();

  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.roundRect(bx, by, bw, bh, 8);
  ctx.stroke();

  ctx.fillStyle = color;
  ctx.font = "bold 18px 'Open Sans', Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, CANVAS_W / 2, CANVAS_H / 2);
}

// ── Legende ────────────────────────────────────────────────
function updateLegend(astar, bfs, dfs, greedy) {
  const el = document.getElementById("maze-legend");
  if (!el) return;

  function status(algo) {
    if (algo.done) {
      return algo.path
        ? `✓ ${algo.path.length} | ${algo.visited.size} erkundet`
        : "Kein Weg";
    }
    return `${algo.visited.size} erkundet`;
  }

  el.innerHTML =
    `<span class="legend-astar">A* — ${status(astar)}</span>` +
    `<span class="legend-bfs">BFS — ${status(bfs)}</span>` +
    `<span class="legend-dfs">DFS — ${status(dfs)}</span>` +
    `<span class="legend-greedy">Greedy — ${status(greedy)}</span>`;
}

// ── Slider-Init ────────────────────────────────────────────
function initSpeedSlider() {
  const slider = document.getElementById("maze-speed");
  if (!slider) return;
  slider.addEventListener("input", () => {
    // slider value 1 (langsam) … 10 (schnell): 1 → 118ms, 10 → 10ms
    STEP_DELAY = Math.round(130 - slider.value * 12);
  });
}

// ── Hauptschleife ──────────────────────────────────────────
function runMaze(canvas) {
  const ctx = canvas.getContext("2d");
  canvas.width  = CANVAS_W;
  canvas.height = CANVAS_H;

  initSpeedSlider();

  function startNew() {
    const grid   = buildMaze(COLS, ROWS);
    const start  = [1, 1];
    const end    = [COLS - 2, ROWS - 2];
    const astar  = createAstar(grid, start, end);
    const bfs    = createBfs(grid, start, end);
    const dfs    = createDfs(grid, start, end);
    const greedy = createGreedy(grid, start, end);
    winnerShown = false;
    let winnerDeclared = false;

    let lastTime = 0;
    function frame(ts) {
      if (ts - lastTime >= STEP_DELAY) {
        lastTime = ts;
        if (!astar.done)  astar.step();
        if (!bfs.done)    bfs.step();
        if (!dfs.done)    dfs.step();
        if (!greedy.done) greedy.step();
        draw(ctx, grid, astar, bfs, dfs, greedy, start, end);
        updateLegend(astar, bfs, dfs, greedy);

        // Gewinner ermitteln sobald einer fertig ist
        if (!winnerDeclared && (astar.done || bfs.done || dfs.done || greedy.done)) {
          const finished = [
            astar.done  && astar.path  ? "astar"  : null,
            bfs.done    && bfs.path    ? "bfs"    : null,
            dfs.done    && dfs.path    ? "dfs"    : null,
            greedy.done && greedy.path ? "greedy" : null,
          ].filter(Boolean);

          if (finished.length === 1) {
            winnerDeclared = true;
            drawWinnerBanner(ctx, finished[0]);
          } else if (finished.length > 1) {
            winnerDeclared = true;
            drawWinnerBanner(ctx, "draw");
          }
        }
      }

      if (astar.done && bfs.done && dfs.done && greedy.done) {
        draw(ctx, grid, astar, bfs, dfs, greedy, start, end);
        updateLegend(astar, bfs, dfs, greedy);
        // Banner nochmal sicherstellen
        const finished = [
          astar.path  ? "astar"  : null,
          bfs.path    ? "bfs"    : null,
          dfs.path    ? "dfs"    : null,
          greedy.path ? "greedy" : null,
        ].filter(Boolean);
        if (finished.length === 1) drawWinnerBanner(ctx, finished[0]);
        else if (finished.length > 1) drawWinnerBanner(ctx, "draw");

        setTimeout(startNew, 3000);
        return;
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  startNew();
}

// ── Init ───────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("maze-canvas");
  if (canvas) runMaze(canvas);
});
