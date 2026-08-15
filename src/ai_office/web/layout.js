/* 間取りの自動生成。
 *
 * エージェント数だけを入力に、座席・通路(ウェイポイントのグラフ)・部屋の大きさを決める。
 * 画面にもテストにも同じものを使うため、DOMには一切触れない。
 */
'use strict';

// ------------------------------------------------------------ 間取りの定数

const MAX_COLS = 4;     // 1列に並べる机の最大数
const COL_STEP = 96;    // 机の間隔
const SIDE = 34;        // 左右の余白(通路になる)
const DESK_HALF = 30;   // 机の半幅
const BOSS_Y = 84;      // 社長席
const TOP_CORRIDOR = 138;
const ROW0 = 160;       // 最初の机の列
const ROW_STEP = 120;

// 休憩室。待機中の社員はここにいる。
// 「席にいる＝仕事中／休憩室にいる＝手が空いている」を場所で示すため、部屋を壁で分ける。
const WALL = 6;         // 仕切り壁の厚み
const BREAK_W = 176;    // 休憩室の幅
const MIN_H = 320;      // 休憩室の家具が入る最低の高さ
const DOOR_H = 30;      // 出入口の開口

/** エージェント数から、座席・通路グラフ・部屋の大きさを組み立てる */
function buildWorld(agents) {
  const n = Math.max(1, agents.length);
  const rows = Math.max(1, Math.ceil(n / MAX_COLS));
  const cols = Math.max(1, Math.ceil(n / rows));
  const W = Math.max(420, cols * COL_STEP + SIDE * 2);

  const seats = {};
  agents.forEach((a, i) => {
    const r = Math.floor(i / cols), c = i % cols;
    seats[a.id] = { x: SIDE + COL_STEP / 2 + c * COL_STEP, y: ROW0 + r * ROW_STEP, row: r };
  });

  const corridorY = [];
  for (let r = 0; r < rows; r++) corridorY.push(ROW0 + r * ROW_STEP + (r === rows - 1 ? 44 : 76));
  const workW = W;
  const H = Math.max(corridorY[corridorY.length - 1] + 18, MIN_H);

  // 縦に通れるのは机と机の隙間だけ。列の格子から隙間のXを出す
  const colX = [];
  for (let c = 0; c < cols; c++) colX.push(SIDE + COL_STEP / 2 + c * COL_STEP);
  const gapX = [colX[0] - COL_STEP / 2];
  for (let c = 0; c < cols - 1; c++) gapX.push((colX[c] + colX[c + 1]) / 2);
  gapX.push(colX[cols - 1] + COL_STEP / 2);

  const nodes = {}, edges = {};
  const add = (name, x, y) => { nodes[name] = { x, y }; };
  const link = (a, b) => {
    (edges[a] = edges[a] || []).push(b);
    (edges[b] = edges[b] || []).push(a);
  };

  gapX.forEach((x, i) => add('u' + i, x, TOP_CORRIDOR));
  for (let i = 0; i < gapX.length - 1; i++) link('u' + i, 'u' + (i + 1));

  corridorY.forEach((y, r) => {
    gapX.forEach((x, i) => add(`c${r}n${i}`, x, y));
    for (let i = 0; i < gapX.length - 1; i++) link(`c${r}n${i}`, `c${r}n${i + 1}`);
    gapX.forEach((x, i) => link(r === 0 ? 'u' + i : `c${r - 1}n${i}`, `c${r}n${i}`));
  });

  // ---- 休憩室
  const bx = workW + WALL;                 // 休憩室の左端
  const doorY = corridorY[0];              // 出入口は作業部屋の最初の通路に合わせる
  const laneX = bx + 20;

  const laneYs = [...new Set([116, 192, 268, doorY])].sort((a, b) => a - b)
    .filter((y) => y > 60 && y < H - 20);
  laneYs.forEach((y, i) => add('b' + i, laneX, y));
  for (let i = 0; i < laneYs.length - 1; i++) link('b' + i, 'b' + (i + 1));

  // 出入口: 作業部屋のいちばん右の通路 → 休憩室のレーン
  const doorNode = 'b' + laneYs.indexOf(doorY);
  link(`c0n${gapX.length - 1}`, doorNode);

  // 休憩中の居場所。ソファは座り、それ以外は立つ
  // 名札が重ならないよう、横は70px以上あける
  const spotDefs = [
    { x: bx + 54,  y: 112, sit: false }, { x: bx + 128, y: 112, sit: false },
    { x: bx + 54,  y: 176, sit: true },  { x: bx + 128, y: 176, sit: true },
    { x: bx + 54,  y: 258, sit: true },  { x: bx + 128, y: 258, sit: true },
    { x: bx + 54,  y: 306, sit: false }, { x: bx + 128, y: 306, sit: false },
  ].filter((sp) => sp.y < H - 20);

  const spots = [];
  spotDefs.forEach((sp, i) => {
    const name = 'spot' + i;
    add(name, sp.x, sp.y);
    // いちばん近いレーンにつなぐ
    let best = 0, bd = Infinity;
    laneYs.forEach((y, j) => { const d = Math.abs(y - sp.y); if (d < bd) { bd = d; best = j; } });
    link(name, 'b' + best);
    spots.push({ name, x: sp.x, y: sp.y, sit: sp.sit });
  });

  const roam = spots.map((s) => s.name);   // 待機中の行き先は休憩室の中だけ

  agents.forEach((a) => {
    const s = seats[a.id];
    const name = 'desk_' + a.id;
    add(name, s.x, s.y + 44);
    gapX.map((x, i) => ({ i, d: Math.abs(x - s.x) }))
        .sort((p, q) => p.d - q.d).slice(0, 2)
        .forEach((nb) => link(name, `c${s.row}n${nb.i}`));
  });

  return {
    W: workW + WALL + BREAK_W, H, rows, cols, seats, nodes, edges, roam, spots,
    work: { x0: 0, x1: workW },
    room: { bx, w: BREAK_W, laneX, doorY, doorH: DOOR_H, wallX: workW, wall: WALL },
    boss: { x: Math.round(workW / 2), y: BOSS_Y, boss: true },
  };
}

function bfsIn(world, from, to) {
  if (from === to) return [to];
  const prev = { [from]: null };
  const q = [from];
  while (q.length) {
    const cur = q.shift();
    for (const nx of world.edges[cur] || []) {
      if (nx in prev) continue;
      prev[nx] = cur;
      if (nx === to) {
        const path = [];
        for (let x = to; x; x = prev[x]) path.unshift(x);
        return path.slice(1);
      }
      q.push(nx);
    }
  }
  return [to];
}

if (typeof module !== 'undefined') module.exports = { buildWorld, bfsIn, COL_STEP, SIDE, DESK_HALF, ROW0, ROW_STEP, TOP_CORRIDOR, BOSS_Y, MAX_COLS, WALL, BREAK_W, DOOR_H };
