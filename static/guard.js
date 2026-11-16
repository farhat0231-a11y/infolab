// Оқушы үшін тапсырмаларды көшіруді қиындату: мәтінді белгілеу/көшіру, оған қою және су белгісі.
// Ескерту: бұл тек тосқауыл — экран суретін (скриншот) браузер арқылы бөгеуге болмайды; су белгісі оны таратуды тежейді.
(function(){
  const box = document.getElementById('tasks'); if(!box) return;
  const st = document.createElement('style');
  st.textContent = '#tasks{-webkit-user-select:none;user-select:none}' +
    '#tasks input,#tasks textarea{-webkit-user-select:text;user-select:text}' +
    '@media print{#tasks{display:none!important}}' +
    '.wm{position:fixed;inset:0;z-index:9999;pointer-events:none;opacity:.08}';
  document.head.appendChild(st);
  const inTasks = n => n && box.contains(n.nodeType === 3 ? n.parentNode : n);
  const editable = n => n && n.closest && n.closest('input,textarea');
  ['copy', 'cut', 'dragstart'].forEach(ev => document.addEventListener(ev, e => {
    const sel = window.getSelection();
    if(inTasks(e.target) && !editable(e.target) || (sel && !sel.isCollapsed && inTasks(sel.anchorNode) && !editable(document.activeElement))) e.preventDefault();
  }));
  document.addEventListener('contextmenu', e => { if(inTasks(e.target) && !editable(e.target)) e.preventDefault(); });
  // Жауап және код өрістеріне қоюға тыйым: ЖИ жазған кодты көшіріп қою мүмкін емес (кіріс деректеріне рұқсат)
  document.addEventListener('paste', e => {
    const el = editable(e.target); if(!el || !box.contains(el)) return;
    const m = /^(in|code)(\d+)$/.exec(el.id || ''); const t = m && (window.TASKS || []).find(x => x.id === +m[2]);
    if(t && ['short', 'open', 'code'].includes(t.type)){
      e.preventDefault(); if(window.toast) toast(T('Жауапты өзіңіз жазыңыз, қоюға болмайды'));
      if(window.GUARD_LESSON) fetch('/api/paste/' + window.GUARD_LESSON, {method: 'POST', keepalive: true}).catch(() => {});
    }
  }, true);
  document.addEventListener('drop', e => { if(editable(e.target) && /^(in|code)\d+$/.test(e.target.id || '')) e.preventDefault(); }, true);
  // Беттен шығу (басқа терезе, ЖИ панелі, Lens): 2 секундтан ұзақ болса мұғалімге белгі жіберіледі
  let awayAt = null;
  const leave = () => { if(awayAt === null) awayAt = Date.now(); };
  const back = () => {
    if(awayAt === null) return;
    const secs = Math.round((Date.now() - awayAt) / 1000); awayAt = null;
    if(secs < 2 || !window.GUARD_LESSON) return;
    if(window.toast) toast(T('Сабақ бетінен шыққаныңыз мұғалімге көрінеді'));
    fetch('/api/away/' + window.GUARD_LESSON, {method: 'POST', keepalive: true,
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({secs})}).catch(() => {});
  };
  // Сабақ режимі: мұғалім оқушының қай тапсырмада тұрғанын және бетте ме екенін көреді (20 секунд сайын)
  let taskNo = 0, pingT = null;
  box.addEventListener('focusin', e => {
    const card = e.target.closest && e.target.closest('.task'); if(!card) return;
    const n = [...box.querySelectorAll('.task')].indexOf(card) + 1;
    if(n && n !== taskNo){ taskNo = n; ping(); }
  });
  const ping = () => {
    clearTimeout(pingT); pingT = setTimeout(ping, 20000);
    if(!window.GUARD_LESSON) return;
    fetch('/api/ping/' + window.GUARD_LESSON, {method: 'POST', keepalive: true,
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({task: taskNo, hidden: document.hidden || awayAt !== null})}).catch(() => {});
  };
  window.addEventListener('blur', () => { leave(); ping(); });
  window.addEventListener('focus', () => { back(); ping(); });
  document.addEventListener('visibilitychange', () => { document.hidden ? leave() : back(); ping(); });
  ping();
  // Су белгісі: оқушының аты экран суретінде көрінеді
  const name = (window.GUARD_NAME || '').replace(/[<>&"]/g, '');
  if(name){
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><text x="20" y="100" transform="rotate(-24 160 90)" font-family="sans-serif" font-size="20" fill="#000">${name} · ${new Date().toLocaleDateString()}</text></svg>`;
    const d = document.createElement('div'); d.className = 'wm';
    d.style.background = `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
    document.body.appendChild(d);
  }
})();
