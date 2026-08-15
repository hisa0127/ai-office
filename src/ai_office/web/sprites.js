/* AI Office - キャラクタースプライト定義（24x32 / 4方向）
 *
 * バーチャルオフィス系（Gather / MetaLife）のアバターに寄せた作り。
 * レトロゲーム寄りだった前版から、次の4点を変えている:
 *   1. 頭を大きく（頭17行 : 体14行 ≒ 1.8頭身）
 *   2. 黒い輪郭をやめ、隣の色を暗くした「色つき輪郭」にする（縁が硬くならない）
 *   3. 目を 3x3 にして白のハイライトを入れる
 *   4. 3階調をやめてほぼフラットに塗る（影は最小限）
 *
 * 正面 / 側面 を手描きし、背面は正面から顔を消して生成する。左向きは右向きの反転。
 * 歩行は「立ち → 左足 → 立ち → 右足」の4コマ（脚の行だけ差し替える）。
 *
 * 記号は色ではなく役割を指す。実際の色は app.js の palFor() が割り当てる。
 *   H=髪  h=髪の影   S=肌  s=肌の影   P=瞳  W=瞳のハイライト/白  M=口
 *   B=服  b=服の影   A=襟・差し色     G=脚  g=脚の影  O=靴
 *   C=帽子  c=帽子の影   X=小物  x=小物の影
 *   1〜6 = 自動生成される色つき輪郭（隣接する色ごとに違う暗さになる）
 */
'use strict';

const SPRITE_W = 24;
const SPRITE_H = 32;

// ------------------------------------------------------------ 正面

const FRONT_BODY = [
  '.......HHHHHHHHHH.......',  //  0 髪
  '.....HHHHHHHHHHHHHH.....',  //  1
  '....HHHHHHHHHHHHHHHH....',  //  2
  '...HHHHHHHHHHHHHHHHHH...',  //  3
  '..HHHHHHHHHHHHHHHHHHHH..',  //  4
  '..HHHHSSSSSSSSSSSSHHHH..',  //  5 額
  '..HHHSSSSSSSSSSSSSSHHH..',  //  6
  '..HHSSSSSSSSSSSSSSSSHH..',  //  7
  '..HHSSWPPSSSSSSWPPSSHH..',  //  8 目（左上に白のハイライト）
  '..HHSSPPPSSSSSSPPPSSHH..',  //  9
  '..HHSSPPPSSSSSSPPPSSHH..',  // 10
  '..HHSSSSSSSSSSSSSSSSHH..',  // 11
  '..HHSSSSSSSMMSSSSSSSHH..',  // 12 口
  '..HHSSSSSSSSSSSSSSSSHH..',  // 13
  '...HSSSSSSSSSSSSSSSSH...',  // 14 あご
  '....HSSSSSSSSSSSSSSH....',  // 15
  '......ssssssssssss......',  // 16 あご下の影
  '.....BBBBBBBBBBBBBB.....',  // 17 肩
  '....BBBBBBBAABBBBBBB....',  // 18 襟
  '...BBBBBBBBAABBBBBBBB...',  // 19 腕
  '...BBBBBBBBAABBBBBBBB...',  // 20
  '...BBBBBBBBBBBBBBBBBB...',  // 21
  '...SSBBBBBBBBBBBBBBSS...',  // 22 手
  '...SSBBBBBBBBBBBBBBSS...',  // 23
  '.....bBBBBBBBBBBBBb.....',  // 24 裾
];

const FRONT_LEGS = {
  stand: [
    '.....GGGGGG..GGGGGG.....',
    '.....GGGGGG..GGGGGG.....',
    '.....GGGGGG..GGGGGG.....',
    '.....GGGGGG..GGGGGG.....',
    '.....OOOOOO..OOOOOO.....',
    '.....OOOOOO..OOOOOO.....',
  ],
  left: [   // 左足を前へ
    '....GGGGGG...GGGGGG.....',
    '...GGGGGG....GGGGGG.....',
    '...GGGGGG.....GGGGG.....',
    '...GGGGGG.....GGGGG.....',
    '...OOOOOO.....OOOOO.....',
    '...OOOOOO.....OOOOO.....',
  ],
  right: [  // 右足を前へ
    '.....GGGGGG...GGGGGG....',
    '.....GGGGGG....GGGGGG...',
    '.....GGGGG.....GGGGGG...',
    '.....GGGGG.....GGGGGG...',
    '.....OOOOO.....OOOOOO...',
    '.....OOOOO.....OOOOOO...',
  ],
};

// ------------------------------------------------------------ 側面（右向き。左向きは反転）

const SIDE_BODY = [
  '......HHHHHHHHHH........',  //  0
  '....HHHHHHHHHHHHH.......',  //  1
  '...HHHHHHHHHHHHHHH......',  //  2
  '..HHHHHHHHHHHHHHHHH.....',  //  3
  '..HHHHHHHHHHHHHHHHH.....',  //  4
  '..HHHHHHHHSSSSSSSSS.....',  //  5 額
  '..HHHHHHSSSSSSSSSSS.....',  //  6
  '..HHHHHSSSSSSSSSSSSS....',  //  7 鼻が前に出る
  '..HHHHHSSWPPSSSSSSSS....',  //  8 目は片方だけ
  '..HHHHHSSPPPSSSSSSSS....',  //  9
  '..HHHHHSSPPPSSSSSSSS....',  // 10
  '..HHHHHSSSSSSSSSSSSS....',  // 11
  '..HHHHHSSSSSSSSSMMSS....',  // 12 口も前寄り
  '..HHHHHSSSSSSSSSSSSS....',  // 13
  '...HHHHSSSSSSSSSSSS.....',  // 14
  '....HHHSSSSSSSSSSS......',  // 15
  '......ssssssssss........',  // 16
  '.....BBBBBBBBBBBB.......',  // 17 肩
  '....BBBBBBBBBBBBBB......',  // 18
  '....BBBBBBBBBBBBBB......',  // 19
  '....BBBBBBBBBBBBBB......',  // 20
  '....BBBBBBBBBBBBBB......',  // 21
  '....SSBBBBBBBBBBBB......',  // 22 手
  '....SSBBBBBBBBBBBB......',  // 23
  '.....bBBBBBBBBBBb.......',  // 24
];

const SIDE_LEGS = {
  stand: [
    '.....GGGGGGGGGGG........',
    '.....GGGGGGGGGGG........',
    '.....GGGGGGGGGGG........',
    '.....GGGGGGGGGGG........',
    '....OOOOOOOOOOOO........',
    '....OOOOOOOOOOOO........',
  ],
  left: [
    '....GGGGGGGGGGGG........',
    '...GGGGGGGGGGGGG........',
    '...GGGGG...GGGGG........',
    '...GGGGG...GGGGG........',
    '..OOOOO.....OOOOO.......',
    '..OOOOO.....OOOOO.......',
  ],
  right: [
    '.....GGGGGGGGGGGG.......',
    '.....GGGGGGGGGGGGG......',
    '.....GGGGG...GGGGG......',
    '.....GGGGG...GGGGG......',
    '....OOOOO.....OOOOO.....',
    '....OOOOO.....OOOOO.....',
  ],
};

const WALK_CYCLE = ['stand', 'left', 'stand', 'right'];

// ------------------------------------------------------------ 色つき輪郭
//
// 黒一色で囲むとレトロゲーム寄りの硬い印象になる。隣接する色を暗くした縁にすると、
// 輪郭を保ったまま柔らかく見える（今どきのアバターがやっている手法）。

const OUTLINE_KEY = {
  H: '1', h: '1', C: '5', c: '5',
  S: '2', s: '2', P: '2', W: '2', M: '2',
  B: '3', b: '3', A: '3',
  G: '4', g: '4', O: '4',
  X: '6', x: '6',
};

// ------------------------------------------------------------ 職業ごとの装い

const KITS = {
  long: {   // 長い髪
    head(rows, dir) {
      const cols = dir === 'side' ? [2, 3] : [2, 3, 20, 21];
      for (let r = 14; r <= 23; r++) for (const c of cols) setPx(rows, r, c, r > 20 ? 'h' : 'H');
    },
  },
  cap: {    // キャップ
    head(rows, dir) {
      for (let r = 0; r <= 4; r++) {
        for (let c = 0; c < SPRITE_W; c++) {
          if (rows[r][c] === 'H') setPx(rows, r, c, 'C');
          else if (rows[r][c] === 'h') setPx(rows, r, c, 'c');
        }
      }
      rows[5] = dir === 'side' ? '..CCCCCCCCCCCCCCCCc.....' : '..CCCCCCCCCCCCCCCCCCCC..';
      rows[6] = dir === 'side' ? '..ccccccccSSSSSSSSS.....' : '..ccccSSSSSSSSSSSScccc..';
    },
  },
  bun: {    // おだんご
    head(rows) {
      rows[0] = '........HHHHHH..........';
      rows[1] = '......HHHHHHHHHH........';
      rows[2] = '....HHHHHHHHHHHHHH......';
    },
  },
  ponytail: {
    head(rows, dir) {
      const c0 = dir === 'side' ? 1 : 21;
      for (let r = 6; r <= 22; r++) { setPx(rows, r, c0, 'H'); setPx(rows, r, c0 + 1, 'h'); }
    },
  },
  spiky: {  // ツンツン頭
    head(rows) {
      rows[0] = '......H.HH.HH.HH.H......';
      rows[1] = '....HHHHHHHHHHHHHH......';
      rows[2] = '....HHHHHHHHHHHHHHHH....';
    },
  },
  glasses: {  // メガネ（大きい目に合わせて枠も大きく）
    head(rows, dir) {
      if (dir === 'side') {
        rows[7] = '..HHHHH11111SSSSSSSS....';
        rows[8] = '..HHHHH1WPP1SSSSSSSS....';
        rows[9] = '..HHHHH1PPP1SSSSSSSS....';
        rows[10] = '..HHHHH11111SSSSSSSS....';
      } else {
        rows[7] = '..HHS11111SS11111SSHH...';
        rows[8] = '..HH11WPP111WPP11SSHH...';
        rows[9] = '..HH1PPP1111PPP11SSHH...';
        rows[10] = '..HH11111SS11111SSSHH...';
      }
    },
  },
  phones: {  // ヘッドホン
    head(rows, dir) {
      if (dir === 'side') {
        for (let r = 7; r <= 11; r++) { setPx(rows, r, 5, 'X'); setPx(rows, r, 6, 'X'); }
        for (let c = 4; c <= 14; c++) setPx(rows, 1, c, 'X');
      } else {
        for (let r = 7; r <= 11; r++) {
          setPx(rows, r, 1, 'X'); setPx(rows, r, 2, 'X');
          setPx(rows, r, 21, 'X'); setPx(rows, r, 22, 'X');
        }
        for (let c = 5; c <= 18; c++) setPx(rows, 0, c, 'X');
      }
    },
  },
  crown: {   // 王冠（社長）
    head(rows) {
      rows[0] = '.....X.X.XXXX.X.X.......';
      rows[1] = '.....XXXXXXXXXXXX.......';
      rows[2] = '....xXXXXXXXXXXXXx......';
      rows[3] = '...HHHHHHHHHHHHHHHHHH...';
    },
  },
  beard: {   // ヒゲ（社長）
    head(rows, dir) {
      const c0 = dir === 'side' ? 7 : 5;
      const c1 = dir === 'side' ? 18 : 18;
      for (let c = c0; c <= c1; c++) { setPx(rows, 13, c, 'h'); setPx(rows, 14, c, 'h'); }
      for (let c = c0 + 3; c <= c1 - 3; c++) setPx(rows, 15, c, 'h');
    },
  },
};

// 手に持つ小物。手は 正面: x3-4 / x19-20、側面: x4-5、いずれも y23-24。
const PROPS = {
  clipboard: {
    front: [{ x: 0, y: 21, w: 8, h: 10, k: 'W' }, { x: 2, y: 21, w: 4, h: 2, k: 'X' },
            { x: 2, y: 25, w: 4, h: 1, k: 'x' }, { x: 2, y: 27, w: 4, h: 1, k: 'x' }],
    side:  [{ x: 1, y: 21, w: 7, h: 10, k: 'W' }, { x: 3, y: 21, w: 3, h: 2, k: 'X' }],
  },
  binder: {
    front: [{ x: 16, y: 21, w: 8, h: 10, k: 'X' }, { x: 18, y: 24, w: 4, h: 4, k: 'W' }],
    side:  [{ x: 15, y: 21, w: 8, h: 10, k: 'X' }, { x: 17, y: 24, w: 4, h: 4, k: 'W' }],
  },
  papers: {
    front: [{ x: 0, y: 20, w: 9, h: 8, k: 'W' }, { x: 2, y: 23, w: 5, h: 1, k: 'x' },
            { x: 2, y: 25, w: 5, h: 1, k: 'x' }],
    side:  [{ x: 1, y: 20, w: 8, h: 8, k: 'W' }, { x: 3, y: 23, w: 4, h: 1, k: 'x' }],
  },
  palette: {
    front: [{ x: 16, y: 21, w: 8, h: 8, k: 'W' },
            { x: 17, y: 22, w: 2, h: 2, k: 'X' }, { x: 21, y: 22, w: 2, h: 2, k: 'A' },
            { x: 17, y: 26, w: 2, h: 2, k: 'A' }, { x: 21, y: 26, w: 2, h: 2, k: 'X' }],
    side:  [{ x: 15, y: 21, w: 8, h: 8, k: 'W' }, { x: 16, y: 22, w: 2, h: 2, k: 'X' },
            { x: 20, y: 22, w: 2, h: 2, k: 'A' }],
  },
  laptop: {
    front: [{ x: 15, y: 20, w: 9, h: 7, k: 'X' }, { x: 16, y: 21, w: 7, h: 5, k: 'W' },
            { x: 15, y: 27, w: 9, h: 3, k: 'x' }],
    side:  [{ x: 14, y: 20, w: 9, h: 7, k: 'X' }, { x: 15, y: 21, w: 7, h: 5, k: 'W' },
            { x: 14, y: 27, w: 9, h: 3, k: 'x' }],
  },
  loupe: {
    front: [{ x: 16, y: 18, w: 8, h: 8, k: 'X' }, { x: 18, y: 20, w: 4, h: 4, k: 'W' },
            { x: 19, y: 26, w: 2, h: 5, k: 'x' }],
    side:  [{ x: 15, y: 18, w: 8, h: 8, k: 'X' }, { x: 17, y: 20, w: 4, h: 4, k: 'W' },
            { x: 18, y: 26, w: 2, h: 5, k: 'x' }],
  },
  bag: {
    front: [{ x: 16, y: 23, w: 8, h: 8, k: 'X' }, { x: 16, y: 23, w: 8, h: 2, k: 'x' },
            { x: 19, y: 21, w: 2, h: 3, k: 'x' }],
    side:  [{ x: 15, y: 23, w: 8, h: 8, k: 'X' }, { x: 17, y: 21, w: 2, h: 3, k: 'x' }],
  },
  scepter: {
    front: [{ x: 1, y: 9, w: 3, h: 22, k: 'x' }, { x: 0, y: 5, w: 5, h: 5, k: 'X' }],
    side:  [{ x: 2, y: 9, w: 3, h: 22, k: 'x' }, { x: 1, y: 5, w: 5, h: 5, k: 'X' }],
  },
};

// ------------------------------------------------------------ 組み立て

function setPx(rows, r, c, ch) {
  if (r < 0 || r >= rows.length || c < 0 || c >= SPRITE_W) return;
  rows[r] = rows[r].slice(0, c) + ch + rows[r].slice(c + 1);
}

/**
 * シルエットの外側1pxを縁取る。
 * 縁の色は「隣にある色を暗くしたもの」にするので、黒縁のような硬さが出ない。
 */
function addOutline(rows) {
  const out = rows.slice();
  const at = (r, c) =>
    (r >= 0 && r < rows.length && c >= 0 && c < SPRITE_W) ? rows[r][c] : '.';
  for (let r = 0; r < rows.length; r++) {
    for (let c = 0; c < SPRITE_W; c++) {
      if (rows[r][c] !== '.') continue;
      const near = [at(r - 1, c), at(r + 1, c), at(r, c - 1), at(r, c + 1)].find((k) => k !== '.');
      if (near) setPx(out, r, c, OUTLINE_KEY[near] || '3');
    }
  }
  return out;
}

/** 背面は正面から顔（肌・目・口）を消して髪で覆う */
function toBack(rows) {
  for (let r = 4; r <= 16; r++) {
    for (let c = 0; c < SPRITE_W; c++) {
      const v = rows[r][c];
      if (v === 'S' || v === 'P' || v === 'M' || v === 'W') setPx(rows, r, c, 'H');
      else if (v === 's') setPx(rows, r, c, 'h');
    }
  }
  return rows;
}

/**
 * スプライトを1枚組み立てる。
 *   dir   : 'front' | 'back' | 'side'
 *   frame : 0-3（null なら立ち）
 *   kits  : KITS のキー配列
 */
function personSprite(dir, frame, kits) {
  const side = dir === 'side';
  const body = (side ? SIDE_BODY : FRONT_BODY).slice();
  const legs = (side ? SIDE_LEGS : FRONT_LEGS)[frame == null ? 'stand' : WALK_CYCLE[frame]];
  let rows = body.concat(legs);

  for (const name of kits || []) {
    const kit = KITS[name];
    if (kit && kit.head) kit.head(rows, side ? 'side' : 'front');
  }
  if (dir === 'back') rows = toBack(rows);

  rows = ['.'.repeat(SPRITE_W)].concat(rows);   // 頭の上に輪郭用の1行
  return addOutline(rows);
}

if (typeof module !== 'undefined') {
  module.exports = { personSprite, addOutline, PROPS, KITS, OUTLINE_KEY,
                     SPRITE_W, SPRITE_H, FRONT_BODY, SIDE_BODY, FRONT_LEGS, SIDE_LEGS };
}
