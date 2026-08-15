/* 表示文言。サーバーが返す state.lang で切り替える */
'use strict';

const STRINGS = {
  ja: {
    working: '稼働', idle: '待機', stalled: '滞留',
    live: 'LIVE', connecting: '接続中', down: '切断',
    legendWorking: '作業中（着席）', legendIdle: '待機中（歩行）', legendStalled: '滞留（15分以上応答なし）',
    legendHint: 'クリックで詳細',
    roomWork: '作業部屋', roomBreak: '休憩室',
    legendWork: '作業部屋にいる＝仕事中', legendBreak: '休憩室にいる＝手が空いている',
    cardBoss: 'あなた', cardStalled: '滞留アラート', cardProjects: '進行中の案件', cardTimeline: '業務ログ',
    here: '作業中', away: '離席中', lastOp: '最終操作',
    sessionRunning: 'セッション進行中',
    bubbleIdle: '待機中', bubbleAway: '離席中', bubbleWorking: '作業中', bubbleWaiting: '応答待ち',
    elapsed: '経過', noResponse: '応答なし', instructing: '指示出し中',
    noStalled: '滞留なし', noProjects: '案件なし', noTimeline: 'まだ記録がありません',
    noAgents: 'エージェントが見つかりません（.claude/agents/ が空です）',
    waitingRun: 'が応答待ち',
    dStatus: '状態', dTask: '現在の仕事', dProject: '案件', dElapsed: '経過', dQueue: '待ち行列',
    dRuns: '通算実行', dLast: '直近の成果', dRecent: '最近の仕事', dSession: 'セッション',
    dLastPrompt: '直近の指示', dYou: 'あなた', dMain: 'メイン会話',
    times: '回', avg: '平均', items: '件',
  },
  en: {
    working: 'Working', idle: 'Idle', stalled: 'Stalled',
    live: 'LIVE', connecting: 'connecting', down: 'offline',
    legendWorking: 'Working (at desk)', legendIdle: 'Idle (walking)', legendStalled: 'Stalled (15+ min)',
    legendHint: 'click for details',
    roomWork: 'Work room', roomBreak: 'Break room',
    legendWork: 'in the work room = busy', legendBreak: 'in the break room = free',
    cardBoss: 'You', cardStalled: 'Stalled', cardProjects: 'Projects', cardTimeline: 'Activity',
    here: 'Active', away: 'Away', lastOp: 'last seen',
    sessionRunning: 'session in progress',
    bubbleIdle: 'idle', bubbleAway: 'away', bubbleWorking: 'working', bubbleWaiting: 'no response',
    elapsed: 'elapsed', noResponse: 'no response', instructing: 'giving instructions',
    noStalled: 'Nothing stalled', noProjects: 'No projects', noTimeline: 'No activity yet',
    noAgents: 'No agents found (.claude/agents/ is empty)',
    waitingRun: 'is not responding',
    dStatus: 'Status', dTask: 'Current task', dProject: 'Project', dElapsed: 'Elapsed', dQueue: 'Queued',
    dRuns: 'Total runs', dLast: 'Last result', dRecent: 'Recent work', dSession: 'Session',
    dLastPrompt: 'Last prompt', dYou: 'You', dMain: 'main conversation',
    times: '', avg: 'avg', items: '',
  },
};

let LANG = 'en';
const t = (key) => (STRINGS[LANG] || STRINGS.en)[key];

function setLang(lang) {
  LANG = STRINGS[lang] ? lang : 'en';
  document.documentElement.lang = LANG;
  for (const el of document.querySelectorAll('[data-i18n]')) {
    const v = t(el.dataset.i18n);
    if (typeof v === 'string') el.textContent = v;
  }
}

/** 状態 → 表示名 */
const STATUS_LABEL = {
  ja: { working: '作業中', idle: '待機中', stalled: '滞留' },
  en: { working: 'working', idle: 'idle', stalled: 'stalled' },
};
const statusLabel = (s) => (STATUS_LABEL[LANG] || STATUS_LABEL.en)[s] || s;
