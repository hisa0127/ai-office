/* 間取り生成の検証。
 *
 * 買った人の人数は分からないので、1人〜16人のすべてで
 *   1. 通路が机を突き抜けない（歩いたら机の中を通る辺が無い）
 *   2. どの席からどの通路へも行ける（グラフが連結）
 * を確かめる。ここが壊れると「歩いてるけど机の中を通る」になる。
 *
 *   node tests/test_layout.js
 */
'use strict';

const path = require('path');
const L = require(path.join(__dirname, '..', 'src', 'ai_office', 'web', 'layout.js'));

// 画面用JSの構文チェック。app.js が壊れると画面が真っ白になるが
// レイアウトの計算テストだけでは気づけないため、ここで一緒に見る。
const { execFileSync } = require('child_process');
const WEB = path.join(__dirname, '..', 'src', 'ai_office', 'web');
for (const f of ['app.js', 'layout.js', 'sprites.js', 'i18n.js']) {
  try {
    execFileSync(process.execPath, ['--check', path.join(WEB, f)], { stdio: 'pipe' });
  } catch (e) {
    console.error(`  ✗ ${f}: 構文エラー\n${e.stderr.toString().split('\n').slice(0, 3).join('\n')}`);
    process.exitCode = 1;
  }
}

const CHAR_HALF = 12;     // キャラクターの半幅
const DESK_H = 20;        // 机の高さ

let failures = 0;
const fail = (msg) => { failures++; console.error('  ✗ ' + msg); };

/** 線分と矩形が交わるか(矩形を少しずつ切って判定する簡易版) */
function segmentHitsRect(x1, y1, x2, y2, rx1, ry1, rx2, ry2) {
  const steps = Math.max(2, Math.ceil(Math.hypot(x2 - x1, y2 - y1)));
  for (let i = 0; i <= steps; i++) {
    const x = x1 + ((x2 - x1) * i) / steps;
    const y = y1 + ((y2 - y1) * i) / steps;
    if (x > rx1 && x < rx2 && y > ry1 && y < ry2) return true;
  }
  return false;
}

function check(n) {
  const agents = Array.from({ length: n }, (_, i) => ({ id: 'agent-' + i }));
  const w = L.buildWorld(agents);
  const label = `${n}人`;

  // --- 1. 机を突き抜ける辺が無いこと
  const desks = Object.values(w.seats).map((s) => ({
    x1: s.x - L.DESK_HALF - CHAR_HALF, x2: s.x + L.DESK_HALF + CHAR_HALF,
    y1: s.y, y2: s.y + DESK_H,
  }));

  for (const [a, list] of Object.entries(w.edges)) {
    for (const b of list) {
      const A = w.nodes[a], B = w.nodes[b];
      if (!A || !B) { fail(`${label}: 未定義のノード ${a}→${b}`); continue; }
      for (const d of desks) {
        if (segmentHitsRect(A.x, A.y, B.x, B.y, d.x1, d.y1, d.x2, d.y2)) {
          fail(`${label}: 通路 ${a}→${b} が机(${d.x1}-${d.x2}, ${d.y1})を突き抜ける`);
        }
      }
    }
  }

  // --- 2. どのノードからも全ノードへ行けること
  const names = Object.keys(w.nodes);
  const seen = new Set([names[0]]);
  const queue = [names[0]];
  while (queue.length) {
    for (const nx of w.edges[queue.shift()] || []) {
      if (!seen.has(nx)) { seen.add(nx); queue.push(nx); }
    }
  }
  if (seen.size !== names.length) {
    fail(`${label}: 孤立したノードがある (${names.length - seen.size}個: ` +
         names.filter((x) => !seen.has(x)).slice(0, 3).join(', ') + ')');
  }

  // --- 3. 全員に席とデスク前ノードがあること
  for (const a of agents) {
    if (!w.seats[a.id]) fail(`${label}: ${a.id} の席が無い`);
    if (!w.nodes['desk_' + a.id]) fail(`${label}: ${a.id} のデスク前ノードが無い`);
  }

  // --- 4. 席が作業部屋の中に収まっていること（休憩室にはみ出さない）
  for (const [id, s] of Object.entries(w.seats)) {
    if (s.x - L.DESK_HALF < 0 || s.x + L.DESK_HALF > w.work.x1) {
      fail(`${label}: ${id} の机が作業部屋からはみ出す`);
    }
    if (s.y + DESK_H > w.H) fail(`${label}: ${id} の机が縦にはみ出す`);
  }

  // --- 6. 休憩室まわり: 待機の行き先は全部休憩室の中にあること
  for (const name of w.roam) {
    const n = w.nodes[name];
    if (!n) { fail(`${label}: 待機先 ${name} のノードが無い`); continue; }
    if (n.x <= w.room.bx) fail(`${label}: 待機先 ${name} が休憩室の外(x=${n.x})`);
    if (n.x > w.W - 12 || n.y > w.H - 12) fail(`${label}: 待機先 ${name} が画面外`);
  }

  // --- 7. 壁を通り抜ける通路が無いこと（出入口以外で壁をまたがない）
  const wallX = w.room.wallX, doorTop = w.room.doorY - w.room.doorH / 2;
  const doorBottom = w.room.doorY + w.room.doorH / 2;
  for (const [a, list] of Object.entries(w.edges)) {
    for (const b of list) {
      const A = w.nodes[a], B = w.nodes[b];
      if (!A || !B) continue;
      const crosses = (A.x - wallX) * (B.x - wallX) < 0;
      if (!crosses) continue;
      // 壁を横切る辺は、開口の高さの中に収まっていること
      const yAtWall = A.y + ((B.y - A.y) * (wallX - A.x)) / (B.x - A.x);
      if (yAtWall < doorTop || yAtWall > doorBottom) {
        fail(`${label}: 通路 ${a}→${b} が壁を突き抜ける(y=${Math.round(yAtWall)}, 開口 ${doorTop}〜${doorBottom})`);
      }
    }
  }

  // --- 8. 休憩室から全員の席へ行けること（出社できること）
  for (const a of agents) {
    const path = L.bfsIn(w, w.roam[0], 'desk_' + a.id);
    if (!path.length || path[path.length - 1] !== 'desk_' + a.id) {
      fail(`${label}: 休憩室から ${a.id} の席へ行けない`);
    }
  }

  // --- 5. 席同士が重ならないこと
  const seats = Object.values(w.seats);
  for (let i = 0; i < seats.length; i++) {
    for (let j = i + 1; j < seats.length; j++) {
      if (Math.abs(seats[i].x - seats[j].x) < L.DESK_HALF * 2 &&
          Math.abs(seats[i].y - seats[j].y) < DESK_H) {
        fail(`${label}: 机が重なっている`);
      }
    }
  }

  return w;
}

console.log('間取り生成の検証');
for (let n = 1; n <= 16; n++) {
  const w = check(n);
  console.log(`  ${String(n).padStart(2)}人 → ${w.W}x${w.H}  ${w.rows}列×${w.cols}席  ` +
              `休憩${w.spots.length}席  ノード${Object.keys(w.nodes).length}`);
}

// 経路探索が席まで到達できること
const w = L.buildWorld(Array.from({ length: 7 }, (_, i) => ({ id: 'a' + i })));
const from = w.roam[0];
for (const id of Object.keys(w.seats)) {
  const p = L.bfsIn(w, from, 'desk_' + id);
  if (!p.length || p[p.length - 1] !== 'desk_' + id) fail(`経路探索が ${id} の席に届かない`);
}

console.log(failures === 0 ? '\n✓ すべて通過' : `\n✗ ${failures}件の問題`);
process.exit(failures === 0 ? 0 : 1);
