/* AI Office — ピクセルアートのオフィス描画と稼働状況の表示
 *
 * 座席・通路・部屋の大きさは、サーバーから届いたエージェント数から毎回組み立てる。
 * 何人の環境でも、設定なしでオフィスが成立するようにするため。
 */
'use strict';

const canvas = document.getElementById('scene');
const ctx = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

// ------------------------------------------------------------ 間取り
// 座席と通路の生成は layout.js（テスト対象）。ここでは現在の間取りを保持するだけ。

let world = null;
const bfs = (from, to) => bfsIn(world, from, to);

// ------------------------------------------------------------ 配色

const C = {
  wallTop:'#3b3552', wainscot:'#4a4262', wallLine:'#26223a',
  floorA:'#7a5c3f', floorB:'#6e5238', floorLine:'#5a422c',
  deskTop:'#c9a06a', deskEdge:'#a37c4c', deskFront:'#8a6740', deskDark:'#6d5133',
  monBody:'#2a2a38', monDark:'#1b1b26',
  screenOn:'#7de3ff', screenIdle:'#3a5a72', screenBad:'#ff7a6b',
  outline:'#1a1622', shadow:'rgba(0,0,0,.22)', chair:'#3a3346', chairHi:'#4b4359',
};
// 社長は王様（王冠＋ヒゲ＋杖）。誰の環境でも一目で「自分」と分かるように固定
const BOSS_LOOK = { kits:['crown', 'beard'], prop:'scepter', hair:'#8d8fa6', skin:'#f2c9a0',
                    shirt:'#4d5570', pants:'#39405a', accent:'#c8493f', propColor:'#e0b642' };
const FALLBACK_LOOK = { kits:[], prop:null, hair:'#4a4a5e', skin:'#eec49c',
                        shirt:'#5a5a72', pants:'#3a3a50', accent:'#ccc', propColor:'#c9a06a' };

// ------------------------------------------------------------ 描画ヘルパ

function P(x, y, w, h, c) { ctx.fillStyle = c; ctx.fillRect(x | 0, y | 0, w, h); }

function line(x0, y0, x1, y1, c) {
  x0 |= 0; y0 |= 0; x1 |= 0; y1 |= 0;
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    P(x0, y0, 1, 1, c);
    if (x0 === x1 && y0 === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}

function drawMap(map, x, y, pal) {
  for (let r = 0; r < map.length; r++) {
    for (let c = 0; c < map[r].length; c++) {
      const k = map[r][c];
      if (k === '.') continue;
      const col = pal[k];
      if (col) P(x + c, y + r, 1, 1, col);
    }
  }
}

function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const cl = (v) => Math.max(0, Math.min(255, v));
  const r = cl((n >> 16) + amt), g = cl(((n >> 8) & 255) + amt), b = cl((n & 255) + amt);
  return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);
}

function hash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}

// ------------------------------------------------------------ 背景

function drawRoom(t) {
  const { W, H } = world;
  P(0, 0, W, 46, C.wallTop);
  P(0, 34, W, 12, C.wainscot);
  P(0, 44, W, 2, C.wallLine);

  if (W >= 340) {
    drawWindow(24, 6, t);
    drawWindow(W - 94, 6, t);
  } else {
    drawWindow(Math.round((W - 70) / 2), 6, t);
  }
  if (W >= 300) {
    const bx = Math.round(W / 2 - 50);
    P(bx, 5, 100, 28, '#0f0f18');
    P(bx + 2, 7, 96, 24, '#eef2ee');
    for (let i = 0; i < 4; i++) {
      P(bx + 7, 11 + i * 5, 30 + ((i * 17) % 45), 1, i === 0 ? '#c04a4a' : '#5a6b8a');
    }
    P(bx + 80, 24, 12, 6, '#8ac47a');
    if (W >= 380) drawClock(Math.round(W / 2 + 72), 14);
  }

  for (let y = 46; y < H; y += 8) {
    for (let x = 0; x < W; x += 16) {
      P(x, y, 16, 8, (((x / 16) | 0) + ((y / 8) | 0)) % 2 ? C.floorA : C.floorB);
    }
  }
  for (let y = 46; y < H; y += 8) P(0, y, W, 1, C.floorLine);

  // 社長席のカーペット
  const bx = world.boss.x;
  P(bx - 40, 68, 80, 52, '#4b3f63');
  P(bx - 40, 68, 80, 1, '#5d5079');
  P(bx - 38, 70, 76, 48, '#54476e');

  // 備品は壁ぎわだけに置く(通路と重ならない)
  drawShelf(20, 50);
  drawPlant(60, 70);

  drawBreakRoom(t);
}

/** 休憩室。床の色と家具で作業部屋と区別する */
function drawBreakRoom(t) {
  const R = world.room, H = world.H, x0 = R.bx, bw = R.w;

  // 床(作業部屋の板張りとは変える)
  for (let y = 46; y < H; y += 8) {
    for (let x = x0; x < x0 + bw; x += 16) {
      P(x, y, 16, 8, (((x / 16) | 0) + ((y / 8) | 0)) % 2 ? '#5d4a66' : '#54425c');
    }
  }
  for (let y = 46; y < H; y += 8) P(x0, y, bw, 1, '#463650');

  // 仕切り壁と出入口
  const dTop = R.doorY - R.doorH / 2, dBot = R.doorY + R.doorH / 2;
  P(R.wallX, 44, R.wall, H - 44, '#3b3552');
  P(R.wallX, 44, 1, H - 44, '#26223a');
  P(R.wallX + R.wall - 1, 44, 1, H - 44, '#26223a');
  P(R.wallX, dTop, R.wall, R.doorH, '#54425c');            // 開口
  P(R.wallX - 2, dTop - 3, R.wall + 4, 3, '#2a2540');       // 上枠
  P(R.wallX - 2, dBot, R.wall + 4, 3, '#2a2540');           // 下枠

  drawCooler(x0 + 28, 74);
  drawVending(x0 + bw - 34, 60);

  // ソファ(背もたれ)。座面は人より手前に描くので z 順で別に出す
  for (const y of sofaRows()) {
    P(x0 + 34, y - 14, bw - 66, 14, '#4a6a8c');
    P(x0 + 34, y - 14, bw - 66, 2, '#5f82a6');
    P(x0 + 30, y - 12, 6, 20, '#3e5c7a');                   // 肘掛け
    P(x0 + bw - 36, y - 12, 6, 20, '#3e5c7a');
  }

  // ローテーブル
  const rows = sofaRows();
  const ty = Math.round((rows[0] + (rows[1] || rows[0] + 60)) / 2) + 6;
  P(x0 + 52, ty - 6, bw - 104, 14, '#8a6740');
  P(x0 + 52, ty - 6, bw - 104, 2, '#a37c4c');
  P(x0 + 56, ty + 8, 4, 5, '#6d5133');
  P(x0 + bw - 60, ty + 8, 4, 5, '#6d5133');
  P(x0 + 70, ty - 10, 6, 5, '#e5e5ee');                     // マグ
  P(x0 + 84, ty - 9, 5, 4, '#e5e5ee');
}

/** ソファのある y(座り位置から求める) */
function sofaRows() {
  const ys = [...new Set(world.spots.filter((s) => s.sit).map((s) => s.y))];
  return ys.sort((a, b) => a - b);
}

/** ソファの座面。人より手前に描く */
function drawSofaSeat(y) {
  const R = world.room, x0 = R.bx, bw = R.w;
  P(x0 + 34, y, bw - 66, 10, '#5578a0');
  P(x0 + 34, y, bw - 66, 1, '#6e8fb6');
  P(x0 + 34, y + 9, bw - 66, 2, '#3e5c7a');
}

function drawVending(x, y) {
  P(x - 12, y, 24, 40, '#3a3346');
  P(x - 10, y + 2, 20, 22, '#7de3ff');
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 2; j++) P(x - 8 + i * 6, y + 5 + j * 9, 4, 6, '#e8f4fb');
  }
  P(x - 8, y + 28, 16, 6, '#22202c');
  P(x - 6, y + 30, 6, 2, '#5fd97a');
}

function drawWindow(x, y, t) {
  P(x - 2, y - 2, 74, 32, '#1e1a2e');
  P(x, y, 70, 28, '#7fb7d9');
  P(x, y, 70, 10, '#9ccfe8');
  const drift = (t / 90) % 90;
  P(x + ((drift | 0) % 60), y + 5, 14, 3, '#e8f4fb');
  P(x + ((drift | 0) % 60) + 4, y + 3, 8, 2, '#e8f4fb');
  P(x + (((drift * 0.6) | 0) % 55) + 8, y + 14, 11, 3, '#dceefa');
  P(x + 6, y + 18, 12, 10, '#5f7f9e');
  P(x + 24, y + 14, 10, 14, '#54748f');
  P(x + 44, y + 20, 16, 8, '#5f7f9e');
  P(x + 34, y, 2, 28, '#1e1a2e');
  P(x, y + 13, 70, 2, '#1e1a2e');
}

function drawClock(cx, cy) {
  P(cx - 8, cy - 8, 16, 16, '#1a1622');
  P(cx - 7, cy - 7, 14, 14, '#f4f4ee');
  const d = new Date();
  const hA = ((d.getHours() % 12) + d.getMinutes() / 60) / 12 * Math.PI * 2 - Math.PI / 2;
  const mA = (d.getMinutes() / 60) * Math.PI * 2 - Math.PI / 2;
  line(cx, cy, cx + Math.cos(hA) * 4, cy + Math.sin(hA) * 4, '#1a1622');
  line(cx, cy, cx + Math.cos(mA) * 6, cy + Math.sin(mA) * 6, '#4a4a5e');
  P(cx, cy, 1, 1, '#c04a4a');
}

function drawPlant(x, y) {
  P(x - 5, y, 10, 9, '#a05a3c');
  P(x - 5, y, 10, 2, '#c07a56');
  P(x - 1, y - 6, 2, 7, '#3f6b3a');
  P(x - 7, y - 10, 6, 5, '#4d8046');
  P(x + 1, y - 12, 7, 6, '#57904e');
  P(x - 4, y - 15, 6, 5, '#4d8046');
  P(x + 2, y - 17, 4, 4, '#63a058');
}

function drawCooler(x, y) {
  P(x - 7, y, 14, 24, '#dfe6ee');
  P(x - 7, y, 14, 2, '#b8c2cc');
  P(x - 5, y - 12, 10, 13, '#8fd3ef');
  P(x - 5, y - 12, 10, 3, '#bfe9f8');
  P(x - 3, y + 10, 6, 4, '#5a6470');
}

function drawShelf(x, y) {
  P(x - 6, y, 24, 30, '#6b4f33');
  P(x - 6, y, 24, 2, '#8a6845');
  P(x - 6, y + 14, 24, 2, '#523c26');
  const books = ['#c05a4a', '#4a7fc0', '#d4a83f', '#5aa06a', '#8a5ac0'];
  for (let i = 0; i < 5; i++) P(x - 3 + i * 4, y + 4, 3, 9, books[i]);
  for (let i = 0; i < 4; i++) P(x - 2 + i * 5, y + 19, 4, 10, books[(i + 2) % 5]);
}

// ------------------------------------------------------------ キャラクター

function lookOf(agent) {
  if (agent.boss) return BOSS_LOOK;
  return Object.assign({}, FALLBACK_LOOK, agent.look || {});
}

function palFor(look) {
  const prop = look.propColor || '#c9a06a';
  const cap = look.cap || look.shirt;
  return {
    // フラット塗り。影は「少しだけ暗い同系色」に留める
    H: look.hair,  h: shade(look.hair, -18),
    S: look.skin,  s: shade(look.skin, -14),
    P: '#3a2f3d',  W: '#ffffff',  M: '#c4736b',
    B: look.shirt, b: shade(look.shirt, -16),
    A: look.accent,
    G: look.pants, g: shade(look.pants, -14),
    O: shade(look.pants, -34),
    C: cap,        c: shade(cap, -18),
    X: prop,       x: shade(prop, -22),
    // 色つき輪郭: 隣接する色を暗くしたもの。黒縁にしないことで硬さを消す
    1: shade(look.hair, -46),
    2: shade(look.skin, -42),
    3: shade(look.shirt, -46),
    4: shade(look.pants, -40),
    5: shade(cap, -46),
    6: shade(prop, -46),
  };
}

function emote(x, topY, status, t) {
  if (status === 'stalled') {
    const f = Math.floor(t / 400) % 2;
    P(x + 13, topY - 8 - f, 4, 7, '#ff6b6b');
    P(x + 13, topY, 4, 3, '#ff6b6b');
  } else if (status === 'working') {
    const n = Math.floor(t / 300) % 4;
    for (let i = 0; i < 3; i++) {
      P(x + 13 + i * 4, topY - 3, 3, 3, i < n ? '#ffd166' : 'rgba(255,209,102,.16)');
    }
  }
}

/** dir: 'front' | 'back' | 'side'、flip で左向き */
function drawPerson(agent, cx, footY, dir, flip, frame, t) {
  const look = lookOf(agent);
  const pal = palFor(look);
  const left = Math.round(cx) - SPRITE_W / 2;
  const top = Math.round(footY) - SPRITE_H;
  const kits = look.kits || [];

  if (flip) { ctx.save(); ctx.translate(Math.round(cx) * 2, 0); ctx.scale(-1, 1); }

  drawMap(personSprite(dir, frame, kits), left, top, pal);

  const prop = PROPS[look.prop];
  if (prop && dir !== 'back') {
    for (const r of (dir === 'side' ? prop.side : prop.front)) {
      P(left + r.x, top + r.y, r.w, r.h, pal[r.k]);
    }
  }
  if (flip) ctx.restore();

  emote(Math.round(cx), top, agent.status, t);
}

/** 進行方向から向きを決める */
function facingOf(p) {
  if (!p || !p.moving) return { dir: p && p.lastDir === 'back' ? 'back' : 'front', flip: false };
  const dx = p.vx || 0, dy = p.vy || 0;
  if (Math.abs(dx) >= Math.abs(dy)) return { dir: 'side', flip: dx < 0 };
  return { dir: dy < 0 ? 'back' : 'front', flip: false };
}

function drawSeated(agent, seat, t) {
  P(seat.x - 13, seat.y - 7, 26, 13, C.chair);
  P(seat.x - 13, seat.y - 7, 26, 2, C.chairHi);
  const tap = agent.status === 'working' && Math.floor(t / 120) % 2 ? 1 : 0;
  drawPerson(agent, seat.x, seat.y + 11 + tap, 'front', false, null, t);
}

function drawResting(agent, p, t) {
  drawPerson(agent, p.x, p.y + 6, 'front', false, null, t);
}

function drawStanding(agent, p, t) {
  P(Math.round(p.x) - 8, Math.round(p.y) - 2, 17, 3, 'rgba(0,0,0,.26)');
  const f = facingOf(p);
  drawPerson(agent, p.x, p.y, f.dir, f.flip, p.moving ? Math.floor(t / 160) % 4 : null, t);
}

// ------------------------------------------------------------ デスク

function drawDesk(agent, seat, t, occupied) {
  const x = seat.x, y = seat.y;
  const wide = seat.boss ? 38 : DESK_HALF;
  const status = agent ? agent.status : 'idle';

  P(x - wide - 1, y + 17, wide * 2 + 2, 3, C.shadow);
  P(x - wide, y, wide * 2, 5, C.deskTop);
  P(x - wide, y, wide * 2, 1, shade(C.deskTop, 20));
  P(x - wide, y + 5, wide * 2, 2, C.deskEdge);
  P(x - wide + 2, y + 7, wide * 2 - 4, 11, C.deskFront);
  P(x - wide + 2, y + 16, wide * 2 - 4, 2, C.deskDark);
  P(x - wide + 1, y + 7, 2, 11, C.deskDark);
  P(x + wide - 3, y + 7, 2, 11, C.deskDark);

  const mx = x + (seat.boss ? 18 : 15);
  const on = occupied && status === 'working';
  let screen = on ? C.screenOn : C.screenIdle;
  if (occupied && status === 'stalled') screen = C.screenBad;
  P(mx - 9, y - 15, 18, 14, C.monBody);
  P(mx - 8, y - 14, 16, 12, C.monDark);
  P(mx - 7, y - 13, 14, 10, screen);
  if (on) {
    for (let i = 0; i < 4; i++) {
      const w = 3 + ((Math.floor(t / 260) + i * 3 + mx) % 9);
      P(mx - 6, y - 12 + i * 2, Math.min(w, 12), 1, 'rgba(255,255,255,.55)');
    }
  } else if (occupied && status === 'stalled') {
    P(mx - 3, y - 11, 2, 5, '#7c1d1d');
    P(mx - 3, y - 5, 2, 2, '#7c1d1d');
  }
  P(mx - 2, y - 1, 4, 2, C.monBody);
  P(mx - 5, y + 1, 10, 1, C.monBody);

  P(x - 9, y + 1, 18, 4, '#e0e0e8');
  P(x - 9, y + 1, 18, 1, '#f4f4fa');
  for (let i = 0; i < 5; i++) P(x - 7 + i * 3, y + 3, 2, 1, '#9a9aae');

  P(x - wide + 4, y - 4, 5, 5, '#e5e5ee');
  P(x - wide + 4, y - 4, 5, 1, '#c8c8d6');
  P(x - wide + 9, y - 3, 1, 3, '#c8c8d6');
  if (on && Math.floor(t / 500) % 2) P(x - wide + 6, y - 7, 1, 2, 'rgba(255,255,255,.35)');

  const stacks = seat.boss ? 3 : (hash(agent ? agent.id : 'x') % 2) + 1;
  for (let i = 0; i < stacks; i++) {
    P(x - wide + 12 + i * 6, y - 2, 5, 3, '#f2eddc');
    P(x - wide + 12 + i * 6, y - 2, 5, 1, '#fffaf0');
  }

  if (!occupied) {
    P(x - 8, y - 7, 16, 9, C.chair);
    P(x - 8, y - 7, 16, 1, C.chairHi);
  }
}

// ------------------------------------------------------------ 人の動き

const SPEED = 20;             // px/秒
const people = new Map();
const claimed = new Map();    // ノード名 -> 誰が向かっているか(立ち位置の重なりを避ける)

/** 他の人が向かっていない行き先を選ぶ */
function pickRoamTarget(p) {
  const pool = world.roam;
  for (let i = 0; i < 6; i++) {
    const name = pool[Math.floor(Math.random() * pool.length)];
    const owner = claimed.get(name);
    if (!owner || owner === p.id) return name;
  }
  return pool[Math.floor(Math.random() * pool.length)];
}

function claim(p, name) {
  for (const [k, v] of claimed) if (v === p.id) claimed.delete(k);
  claimed.set(name, p.id);
}

function spotByName(name) {
  return world.spots.find((s) => s.name === name);
}

function initPerson(id, seat, working) {
  const deskNode = 'desk_' + id;
  const start = working ? deskNode : world.roam[hash(id) % world.roam.length];
  const pos = world.nodes[start] || world.nodes[world.roam[0]];
  return {
    id, deskNode, x: pos.x, y: pos.y,
    node: start, queue: [], moving: false, facing: 0,
    mode: working ? 'seated' : 'wait',
    goal: working ? 'desk' : 'roam',
    wait: 1 + Math.random() * 3, sit: 0,
  };
}

function pathTo(p, target) {
  const from = p.queue.length ? p.queue[0].name : p.node;
  p.queue = bfs(from, target)
    .filter((n) => world.nodes[n])
    .map((n) => ({ name: n, x: world.nodes[n].x, y: world.nodes[n].y }));
  const last = p.queue[p.queue.length - 1];
  if (last && target !== p.deskNode) {
    last.x += (hash(p.id + target) % 21) - 10;
    last.y += (hash(target + p.id) % 9) - 4;
  }
}

function updatePeople(dt) {
  for (const { agent, seat } of seatMap) {
    if (agent.boss) continue;
    let p = people.get(agent.id);
    if (!p || !world.nodes[p.deskNode]) {
      p = initPerson(agent.id, seat, agent.status !== 'idle');
      people.set(agent.id, p);
    }

    const wantDesk = agent.status === 'working' || agent.status === 'stalled';
    if (wantDesk && p.goal !== 'desk') {
      p.goal = 'desk';
      if (p.mode !== 'seated') { p.mode = 'walk'; pathTo(p, p.deskNode); }
    } else if (!wantDesk && p.goal !== 'roam') {
      p.goal = 'roam';   // = 休憩室へ戻る
      if (p.mode === 'seated' || p.mode === 'sit') {
        p.mode = 'stand'; p.x = seat.x; p.y = seat.y + 8; p.sit = 0;
      }
    }

    switch (p.mode) {
      case 'seated':
        p.moving = false;
        break;

      case 'sit': {
        p.sit += dt / 0.35;
        const dn = world.nodes[p.deskNode];
        p.y = dn.y + (seat.y + 6 - dn.y) * Math.min(1, p.sit);
        p.x = seat.x; p.moving = false;
        if (p.sit >= 1) { p.mode = 'seated'; p.node = p.deskNode; }
        break;
      }

      case 'stand': {
        p.sit += dt / 0.35;
        const dn = world.nodes[p.deskNode];
        p.y = seat.y + 8 + (dn.y - seat.y - 8) * Math.min(1, p.sit);
        p.x = seat.x; p.moving = true;
        if (p.sit >= 1) {
          p.mode = 'wait'; p.node = p.deskNode; p.wait = 0.3; p.x = dn.x; p.y = dn.y;
        }
        break;
      }

      case 'rest':          // ソファで休憩。たまに席を移る
        p.moving = false;
        p.wait -= dt;
        if (p.wait <= 0 || p.goal === 'desk') {
          const target = p.goal === 'desk' ? p.deskNode : pickRoamTarget(p);
          claim(p, target);
          p.mode = 'walk';
          pathTo(p, target);
        }
        break;

      case 'wait':
        p.moving = false;
        p.wait -= dt;
        if (p.wait <= 0) {
          const target = p.goal === 'desk' ? p.deskNode : pickRoamTarget(p);
          claim(p, target);
          p.mode = 'walk';
          pathTo(p, target);
        }
        break;

      case 'walk': {
        const next = p.queue[0];
        if (!next) { p.mode = 'wait'; p.moving = false; p.wait = 1.5 + Math.random() * 4; break; }
        const dx = next.x - p.x, dy = next.y - p.y;
        const dist = Math.hypot(dx, dy);
        const step = SPEED * dt;
        p.moving = true;
        if (Math.abs(dx) > 1) p.facing = dx > 0 ? 1 : -1;
        if (dist <= step) {
          p.x = next.x; p.y = next.y; p.node = next.name;
          p.queue.shift();
          if (!p.queue.length) {
            const spot = spotByName(p.node);
            p.moving = false;
            if (p.goal === 'desk' && p.node === p.deskNode) { p.mode = 'sit'; p.sit = 0; }
            else if (spot && spot.sit) { p.mode = 'rest'; p.wait = 18 + Math.random() * 25; }
            else if (spot) { p.mode = 'wait'; p.wait = 8 + Math.random() * 16; }
            else {
              // 休憩室の居場所でも自席でもない場所には留まらない。
              // 待機中の社員が作業部屋に立っていると「場所＝状態」が崩れるため。
              p.mode = 'wait'; p.wait = 0.15;
            }
          }
        } else {
          p.vx = dx / dist; p.vy = dy / dist;
          if (Math.abs(p.vy) > Math.abs(p.vx)) p.lastDir = p.vy < 0 ? 'back' : 'front';
          p.x += p.vx * step;
          p.y += p.vy * step;
        }
        break;
      }
    }

    if (p.mode === 'seated') {
      p.anchorX = seat.x; p.anchorY = seat.y - 22; p.plateY = seat.y + 26;
    } else if (p.mode === 'rest') {
      p.anchorX = p.x; p.anchorY = p.y - 30; p.plateY = p.y + 14;
    } else {
      p.anchorX = p.x; p.anchorY = p.y - 36; p.plateY = p.y + 4;
    }
  }
}

// ------------------------------------------------------------ シーン

let state = null;
let seatMap = [];
let rosterKey = '';

function layout() {
  seatMap = [];
  if (!state) return;
  const key = state.agents.map((a) => a.id).join('|');
  if (key !== rosterKey || !world) {
    rosterKey = key;
    world = buildWorld(state.agents);
    people.clear();
    claimed.clear();
    canvas.width = world.W;
    canvas.height = world.H;
    document.getElementById('stage').style.setProperty('--aspect', world.W / world.H);
    ctx.imageSmoothingEnabled = false;
    renderRoomLabels();
  }
  for (const a of state.agents) seatMap.push({ agent: a, seat: world.seats[a.id] });
  seatMap.push({
    agent: { id: '__boss__', role: t('dYou'), boss: true,
             status: state.boss.status === 'active' ? 'working' : 'idle' },
    seat: world.boss,
  });
}

let lastT = 0;
function render(t) {
  requestAnimationFrame(render);
  if (t - lastT < 50) return;
  const dt = Math.min(0.2, (t - lastT) / 1000);
  lastT = t;
  if (!state || !world) return;

  updatePeople(dt);
  drawRoom(t);

  const items = [];
  for (const { agent, seat } of seatMap) {
    if (!seat) continue;
    if (agent.boss) {
      const here = state.boss.status === 'active';
      if (here) items.push({ z: seat.y - 1, draw: () => drawSeated(agent, seat, t) });
      items.push({ z: seat.y + 18, draw: () => drawDesk(agent, seat, t, here) });
      continue;
    }
    const p = people.get(agent.id);
    const seated = p && p.mode === 'seated';
    const resting = p && p.mode === 'rest';
    items.push({
      z: seated ? seat.y - 1 : (p ? p.y : seat.y),
      draw: () => (seated ? drawSeated(agent, seat, t)
                 : resting ? drawResting(agent, p, t)
                 : drawStanding(agent, p, t)),
    });
    items.push({ z: seat.y + 18, draw: () => drawDesk(agent, seat, t, seated) });
  }
  for (const y of sofaRows()) items.push({ z: y + 10, draw: () => drawSofaSeat(y) });
  items.sort((a, b) => a.z - b.z);
  for (const it of items) it.draw();

  positionOverlay();
}

/** 部屋名の札。どちらの部屋にいるかが状態そのものなので、部屋名を出す */
function renderRoomLabels() {
  for (const el of overlay.querySelectorAll('.roomlabel')) el.remove();
  const mk = (text, x, y) => {
    const el = document.createElement('div');
    el.className = 'roomlabel';
    el.textContent = text;
    el.style.left = (x / world.W) * 100 + '%';
    el.style.top = (y / world.H) * 100 + '%';
    overlay.appendChild(el);
  };
  mk(t('roomWork'), 86, 54);
  mk(t('roomBreak'), world.room.bx + world.room.w / 2, 52);
}

// ------------------------------------------------------------ 名札と吹き出し

const overlay = document.getElementById('overlay');
const els = new Map();
const pctX = (x) => (x / world.W) * 100 + '%';
const pctY = (y) => (y / world.H) * 100 + '%';

function fmtDur(ms) {
  if (ms == null) return '';
  const s = Math.floor(ms / 1000);
  if (s < 60) return LANG === 'ja' ? `${s}秒` : `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return LANG === 'ja' ? `${m}分${s % 60}秒` : `${m}m ${s % 60}s`;
  return LANG === 'ja' ? `${Math.floor(m / 60)}時間${m % 60}分` : `${Math.floor(m / 60)}h ${m % 60}m`;
}
function fmtClock(ts) {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g,
    (c) => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
}

function bubbleFor(a) {
  // 待機中は吹き出しを出さない。休憩室にいること自体が「手が空いている」の表示になる
  if (a.boss) {
    if (a.status !== 'working') return null;
    const p = state.boss.lastPrompt ? state.boss.lastPrompt.slice(0, 44) + '…' : t('instructing');
    return { cls: '', text: p, meta: state.boss.sessionTitle || t('here') };
  }
  if (a.status === 'working') {
    return { cls: '', text: a.task || t('bubbleWorking'),
             meta: `${a.project ? a.project.slice(0, 16) + ' / ' : ''}` +
                   `${fmtDur(Date.now() - a.since)}${LANG === 'ja' ? '経過' : ''}` +
                   `${a.background ? ' (BG)' : ''}` };
  }
  if (a.status === 'stalled') {
    return { cls: 'bubble--stalled', text: a.task || t('bubbleWaiting'),
             meta: `${fmtDur(Date.now() - a.since)} ${t('noResponse')}` };
  }
  return null;
}

function syncOverlay() {
  if (!state) return;
  const seen = new Set();
  for (const { agent } of seatMap) {
    seen.add(agent.id);
    let e = els.get(agent.id);
    if (!e) {
      const bubble = document.createElement('div');
      const plate = document.createElement('div');
      plate.className = 'nameplate';
      bubble.onclick = plate.onclick = () => showDetail(agentById(agent.id));
      overlay.appendChild(bubble);
      overlay.appendChild(plate);
      e = { bubble, plate, key: '', pkey: '' };
      els.set(agent.id, e);
    }
    const b = bubbleFor(agent);
    const key = b ? b.cls + '|' + b.text + '|' + b.meta : '';
    if (key !== e.key) {
      e.key = key;
      e.bubble.hidden = !b;
      if (b) {
        e.bubble.className = 'bubble ' + b.cls;
        e.bubble.innerHTML = esc(b.text) +
          (b.meta ? `<span class="bubble__meta">${esc(b.meta)}</span>` : '');
      }
    }
    const pkey = agent.status + '|' + agent.role;
    if (pkey !== e.pkey) {
      e.pkey = pkey;
      e.plate.className = 'nameplate nameplate--' + agent.status;
      e.plate.innerHTML =
        `<span class="nameplate__box"><i class="dot dot--${agent.status}"></i>` +
        `<span class="nameplate__role">${esc(agent.role)}</span></span>`;
    }
  }
  for (const [id, e] of els) {
    if (seen.has(id)) continue;
    e.bubble.remove(); e.plate.remove(); els.delete(id);
  }
}

function positionOverlay() {
  for (const { agent, seat } of seatMap) {
    const e = els.get(agent.id);
    if (!e || !seat) continue;
    let ax, ay, py;
    if (agent.boss) {
      ax = seat.x; ay = seat.y - 24; py = seat.y + 26;
    } else {
      const p = people.get(agent.id);
      if (!p) continue;
      ax = p.anchorX; ay = p.anchorY; py = p.plateY;
    }
    e.bubble.style.left = pctX(ax);
    e.bubble.style.top = pctY(ay);
    e.plate.style.left = pctX(ax);
    e.plate.style.top = pctY(py);
  }
}

function agentById(id) {
  if (id === '__boss__') return { id, boss: true };
  return state.agents.find((a) => a.id === id) || { id, role: id, status: 'idle', runs: 0, queued: 0 };
}

// ------------------------------------------------------------ 詳細

const detail = document.getElementById('detail');
const detailBody = document.getElementById('detail-body');
document.getElementById('detail-close').onclick = () => (detail.hidden = true);
detail.onclick = (e) => { if (e.target === detail) detail.hidden = true; };
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') detail.hidden = true; });

function showDetail(a) {
  if (a.boss) {
    detailBody.innerHTML =
      `<h3>${esc(t('dYou'))}</h3><p class="d-role">${esc(t('dMain'))}</p><dl>` +
      `<dt>${t('dStatus')}</dt><dd>${state.boss.status === 'active' ? t('here') : t('away')}</dd>` +
      `<dt>${t('dSession')}</dt><dd>${esc(state.boss.sessionTitle || '—')}</dd>` +
      `<dt>${t('lastOp')}</dt><dd>${state.boss.lastActivity ? fmtClock(state.boss.lastActivity) : '—'}</dd>` +
      `<dt>${t('dLastPrompt')}</dt><dd>${esc(state.boss.lastPrompt || '—')}</dd></dl>`;
  } else {
    const runs = state.timeline.filter((x) => x.agentId === a.id).slice(0, 6);
    detailBody.innerHTML =
      `<h3>${esc(a.role)}</h3><p class="d-role">${esc(a.id)}</p><dl>` +
      `<dt>${t('dStatus')}</dt><dd>${statusLabel(a.status)}</dd>` +
      `<dt>${t('dTask')}</dt><dd>${esc(a.task || '—')}</dd>` +
      `<dt>${t('dProject')}</dt><dd>${esc(a.project || '—')}</dd>` +
      `<dt>${t('dElapsed')}</dt><dd>${a.since ? fmtDur(Date.now() - a.since) : '—'}</dd>` +
      `<dt>${t('dQueue')}</dt><dd>${a.queued}${t('items')}</dd>` +
      `<dt>${t('dRuns')}</dt><dd>${a.runs}${t('times')} / ${t('avg')} ${fmtDur(a.avgMs)}</dd>` +
      `<dt>${t('dLast')}</dt><dd>${esc(a.lastDone ? a.lastDone.summary || a.lastDone.description : '—')}</dd>` +
      `</dl>` +
      (runs.length
        ? `<h4 class="detail__sub">${t('dRecent')}</h4><ul class="list">` +
          runs.map((r) => `<li><span class="list__title">${esc(r.description)}</span>` +
            `<span class="list__meta"> ${fmtClock(r.at)} / ${fmtDur(r.durationMs)}</span></li>`).join('') +
          `</ul>`
        : '');
  }
  detail.hidden = false;
}

// ------------------------------------------------------------ サイドパネル

function renderPanel() {
  document.getElementById('app-title').textContent = state.title || 'AI Office';
  document.title = state.title || 'AI Office';
  document.getElementById('ws-name').textContent = state.workspaceName || '';
  document.querySelector('#stat-working b').textContent = state.summary.working;
  document.querySelector('#stat-idle b').textContent = state.summary.idle;
  document.querySelector('#stat-stalled b').textContent = state.summary.stalled;


  const empty = document.getElementById('stage-empty');
  empty.hidden = state.agents.length > 0;
  if (!state.agents.length) empty.textContent = t('noAgents');

  const bs = document.getElementById('boss-status');
  bs.dataset.state = state.boss.status;
  bs.textContent = state.boss.status === 'active'
    ? `${t('here')} — ${state.boss.sessionTitle || t('sessionRunning')}`
    : `${t('away')} — ${t('lastOp')} ${state.boss.lastActivity ? fmtClock(state.boss.lastActivity) : '—'}`;
  document.getElementById('boss-prompt').textContent = state.boss.lastPrompt || '';

  const sc = document.getElementById('stalled-count');
  sc.textContent = state.stalled.length;
  sc.dataset.zero = state.stalled.length ? '0' : '1';
  document.getElementById('stalled-list').innerHTML = state.stalled.length
    ? state.stalled.map((s) =>
        `<li class="list__alert"><span class="list__title">${esc(s.label)} ${s.kind === 'run' ? t('waitingRun') : ''}</span>` +
        `<span class="list__meta"><br>${esc(s.detail)} — ${fmtDur(s.ageMs)}</span></li>`).join('')
    : `<li class="empty">${t('noStalled')}</li>`;

  const pcard = document.getElementById('card-projects');
  pcard.hidden = !state.projects.length;
  if (state.projects.length) {
    document.getElementById('project-list').innerHTML = state.projects.map((p) =>
      `<li><span class="list__title">${esc(p.name)}</span>` +
      `<span class="list__meta"><br>${esc(p.phase || '—')}` +
      `${p.lastUpdated ? ' / ' + esc(p.lastUpdated) : ''}` +
      `${p.nextAction ? '<br>▶ ' + esc(p.nextAction.slice(0, 90)) : ''}</span></li>`).join('');
  }

  document.getElementById('timeline').innerHTML = state.timeline.length
    ? state.timeline.map((r) =>
        `<li><span class="tl-time">${fmtClock(r.at)}</span>` +
        `<span class="tl-role">${esc(r.role)}</span>` +
        `<span class="tl-body">${esc(r.description)}` +
        `<span class="tl-dur"> (${fmtDur(r.durationMs)})</span></span></li>`).join('')
    : `<li class="empty">${t('noTimeline')}</li>`;
}

// ------------------------------------------------------------ 接続

const conn = document.getElementById('conn');

function apply(next) {
  const langChanged = !state || state.lang !== next.lang;
  state = next;
  if (langChanged) setLang(state.lang);
  layout();
  syncOverlay();
  renderPanel();
}

function connect() {
  const es = new EventSource('/api/events');
  es.onopen = () => { conn.dataset.state = 'live'; conn.textContent = t('live'); };
  es.onmessage = (e) => { try { apply(JSON.parse(e.data)); } catch (_) {} };
  es.onerror = () => {
    conn.dataset.state = 'down';
    conn.textContent = t('down');
    es.close();
    setTimeout(connect, 3000);
  };
}

setInterval(() => {
  const d = new Date();
  document.getElementById('clock').textContent =
    [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':');
  if (state) syncOverlay();
}, 1000);

setLang('ja');
connect();
requestAnimationFrame(render);
