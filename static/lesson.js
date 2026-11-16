const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const inline = s => esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/\n/g,'<br>');
const fmt = x => (x == null ? '—' : (Number.isInteger(+x) ? String(+x) : (+x).toFixed(1)));
const LETTERS = 'ABCDEFGH';
const ic = n => `<svg class="ic" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const CLOSED = !!(window.DL && window.DL.late && window.DL.pct === 0);   // мерзім өтті, тапсыру жабық
const box = document.getElementById('tasks');
const STUDENT = window.ROLE === 'student';

// Байланыс үзілсе (Wi-Fi, мұғалім компьютері ұйықтап қалса) — жауапты бірнеше рет қайта жібереміз
async function send(url, opts){
  let r;
  for(let k = 0; ; k++){
    try{ r = await fetch(url, opts); break; }
    catch(e){
      if(k >= 5) throw new Error(T('Сервермен байланыс жоқ. Жауабыңыз өшкен жоқ — сәлден соң қайта жіберіңіз'));
      toast(T('Байланыс үзілді, қайта жіберілуде...'));
      await new Promise(ok => setTimeout(ok, 2000 * (k + 1)));
    }
  }
  if(r.redirected && new URL(r.url).pathname === '/login')
    throw new Error(T('Жүйеден шығып кеттіңіз. Жауапты көшіріп алып, бетті жаңартып, қайта кіріңіз'));
  const j = await r.json().catch(()=>({error:T('Сервер қатесі')}));
  if(!r.ok) throw new Error(j.error || T('Қате'));
  return j;
}

const post = (url, body) => send(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});

function upload(url, file){
  const fd = new FormData(); fd.append('file', file);
  return send(url, {method:'POST', body: fd});
}

function stateBadge(t){
  const s = t.sub;
  if(!s) return `<span class="badge state">${t.points} ${T('балл')}</span>`;
  if(s.status === 'pending') return `<span class="badge warn state">${T('Тексерілуде')}</span>`;
  const cls = s.full ? 'ok' : s.score > 0 ? 'warn' : 'bad';
  const late = s.late_pct < 100 ? ` ${ic('clock')}×${s.late_pct}%` : '';
  return `<span class="badge ${cls} state">${fmt(s.score)} / ${t.points} ${T('балл')}${late}</span>`;
}

function taskState(t){
  const s = t.sub;
  if(!s) return 'is-todo';
  if(s.status === 'pending') return 'is-wait';
  return s.full ? 'done is-ok' : s.score > 0 ? 'is-part' : 'is-bad';
}

function locked(t){
  return ['quiz','multi','short'].includes(t.type) && t.sub && (t.sub.attempts >= window.ATTEMPTS || t.sub.full);
}

function renderTask(t, i, extra){
  const el = document.getElementById('task-'+t.id) || Object.assign(document.createElement('div'), {className:'task', id:'task-'+t.id});
  const s = t.sub, lock = locked(t) || !STUDENT || CLOSED;
  let body = '';
  if(t.type === 'quiz' || t.type === 'multi'){
    const inputType = t.type === 'quiz' ? 'radio' : 'checkbox';
    const chosen = s ? [].concat(s.answer ?? []) .map(String) : [];
    const sol = t.solution != null ? [].concat(t.solution).map(String) : null;
    body = t.options.map((o, k) => {
      let cls = '';
      if(sol){ if(sol.includes(String(k))) cls = 'right'; else if(chosen.includes(String(k))) cls = 'wrong'; }
      return `<label class="opt ${cls}"><input type="${inputType}" name="t${t.id}" value="${k}" ${chosen.includes(String(k))?'checked':''} ${lock?'disabled':''}><span><b>${LETTERS[k]}</b><span>${inline(o)}</span></span></label>`;
    }).join('');
    if(t.type === 'multi') body = `<div class="muted small">${T('Бірнеше дұрыс жауап болуы мүмкін')}</div>` + body;
    if(!lock) body += `<button class="btn primary" data-act="submit">${T('Жауап беру')}</button>`;
  }
  if(t.type === 'short'){
    body = `<div class="row"><input type="text" id="in${t.id}" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" value="${esc(s ? s.answer : '')}" placeholder="${esc(t.placeholder || T('Жауабыңыз'))}" ${lock?'disabled':''} style="max-width:320px">
            ${lock ? '' : `<button class="btn primary" data-act="submit">${T('Жіберу')}</button>`}</div>`;
    if(t.solution) body += `<div class="explain"><b>${T('Дұрыс жауап:')}</b> ${esc([].concat(t.solution)[0])}</div>`;
  }
  if(t.type === 'open'){
    body = `<textarea id="in${t.id}" autocomplete="off" autocorrect="off" autocapitalize="off" placeholder="${T('Жауабыңызды осында жазыңыз...')}" ${!STUDENT||CLOSED?'disabled':''}>${esc(s ? s.answer : '')}</textarea>`;
    if(STUDENT && !CLOSED) body += `<div class="row" style="margin-top:8px"><button class="btn primary" data-act="submit">${s ? T('Қайта жіберу') : T('Жіберу')}</button><span class="muted small">${T('Мұғалім тексеріп, баға қояды')}</span></div>`;
    if(s && s.feedback) body += `<div class="explain"><b>${T('Мұғалім пікірі:')}</b> ${esc(s.feedback)}</div>`;
  }
  if(t.type === 'file'){
    const f = s && s.answer && s.answer.file ? s.answer : null;
    if(f) body = `<div class="explain">${ic('file')}<a href="/files/${encodeURIComponent(f.file)}" target="_blank"><b>${esc(f.name)}</b></a></div>`;
    if(STUDENT && !CLOSED) body += `<div class="row" style="margin-top:8px"><input type="file" id="file${t.id}" ${t.accept ? `accept="${esc(t.accept)}"` : ''} style="max-width:320px">
      <button class="btn primary" data-act="submit">${f ? T('Қайта жүктеу') : T('Жүктеу')}</button><span class="muted small">${t.autocheck ? T('Файл автоматты тексеріледі') : T('Мұғалім тексеріп, баға қояды')}</span></div>
      ${t.accept ? `<div class="muted small">${T('Файл түрі:')} ${esc(t.accept)}</div>` : ''}`;
    if(s && s.feedback) body += s.auto
      ? `<div class="explain" style="white-space:pre-line">${esc(s.feedback)}</div>`
      : `<div class="explain"><b>${T('Мұғалім пікірі:')}</b> ${esc(s.feedback)}</div>`;
  }
  if(t.type === 'code'){
    const code = s && s.answer != null ? s.answer : (t.starter || '');
    const ex = (t.examples||[]).map((e,k)=>`<div><b>${T('Мысал')} ${k+1}</b><div class="muted small">${T('Енгізу:')}</div><pre>${esc(e.input)||' '}</pre><div class="muted small">${T('Шығару:')}</div><pre>${esc(e.output)}</pre></div>`).join('');
    body = (ex ? `<div class="examples">${ex}</div>` : '') + `
      <div class="code-box"><div class="bar2"><span>main.py · Python 3</span><span>${T('Ctrl+Enter — іске қосу')}</span></div>
      <textarea class="code" id="code${t.id}" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">${esc(code)}</textarea></div>
      <div class="io"><div><label style="margin-top:0">${T('Енгізу (input)')}</label><textarea id="stdin${t.id}" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" placeholder="${T('Әр мән жаңа жолдан')}">${esc((t.examples||[])[0]?.input || '')}</textarea></div>
      <div><label style="margin-top:0">${T('Нәтиже')}</label><pre class="out" id="out${t.id}"></pre></div></div>
      <div class="row" style="margin-top:10px"><button class="btn" data-act="run">${ic('play')}${T('Іске қосу')}</button>
      ${STUDENT && !CLOSED ? `<button class="btn primary" data-act="submit">${ic('check')}${T('Тексеруге жіберу')} (${t.ntests} ${T('тест')})</button>` : ''}</div>
      <div class="tests" id="tests${t.id}"></div>`;
  }
  if(t.criteria && (t.type === 'open' || t.type === 'file')){
    const got = s && s.rubric;
    body += `<div class="explain"><b>${T('Бағалау критерийлері')}:</b><ul style="margin:6px 0 0 18px">` +
      t.criteria.map((c,k) => `<li>${inline(c.text)} — ${got ? `<b>${fmt(got[k])} / ${fmt(c.points)}</b>` : `${fmt(c.points)} ${T('балл')}`}</li>`).join('') + '</ul></div>';
  }
  let result = '';
  if(s && s.status === 'pending') result = `<div class="result wait">${ic('clock')}${T('Жауабыңыз мұғалімге жіберілді')}</div>`;
  else if(s && ['quiz','multi','short'].includes(t.type)){
    if(s.full) result = `<div class="result ok">${T('Дұрыс!')} +${fmt(s.score)} ${T('балл')}</div>`;
    else if(lock) result = `<div class="result bad">${T('Әрекеттер аяқталды. Жиналған балл:')} ${fmt(s.score)}</div>`;
    else result = `<div class="result bad">${T('Қате. Қалған әрекет:')} ${window.ATTEMPTS - s.attempts}</div>`;
  }
  if(s && s.late_pct < 100) result += `<div class="muted small" style="margin-top:8px">${ic('clock')}${T('Кеш тапсырылды')}: ×${s.late_pct}%</div>`;
  if(CLOSED && STUDENT && !(s && s.full)) result += `<div class="result bad">${ic('lock')}${T('Мерзім өтті, тапсыру жабық')}</div>`;
  if(t.explain) result += `<div class="explain with-ic">${ic('info')}<div>${t.explain}</div></div>`;
  el.className = 'task ' + taskState(t);
  el.innerHTML = `<div class="hd"><span class="num">${i+1}${T('-тапсырма')} · ${T(({quiz:'Тест',multi:'Тест',short:'Қысқа жауап',code:'Python код',open:'Ашық жауап',file:'Практикалық жұмыс'})[t.type])}</span>${stateBadge(t)}</div>
    <div class="prompt">${t.html}</div>${body}<div class="res">${result}</div>`;
  if(!el.parentNode) box.appendChild(el);
  if(t.type === 'code'){
    const ta = el.querySelector('textarea.code');
    enhanceCodeArea(ta, () => runCode(t));
    ta.style.height = Math.max(200, Math.min(520, ta.scrollHeight + 10)) + 'px';
    if(extra && extra.detail) showTests(t, extra.detail);
  }
  el.querySelectorAll('[data-act]').forEach(b => b.onclick = () => b.dataset.act === 'run' ? runCode(t) : submit(t, i, b));
}

function showTests(t, d){
  const box = document.getElementById('tests'+t.id);
  box.innerHTML = `<div class="result ${d.passed === d.total ? 'ok' : 'bad'}">${d.passed}/${d.total} ${T('тест өтті')}</div>` +
    d.results.map(r => `<div class="t ${r.ok?'ok':'bad'}">${r.ok ? ic('check') : ic('x')} ${T('Тест')} ${r.n}${r.hidden?' '+T('(жасырын)'):''}
      ${!r.ok && !r.hidden && r.expected != null ? `<div class="grid g3" style="gap:6px"><div><span class="muted small">${T('Енгізу')}</span><pre>${esc(r.input)||' '}</pre></div><div><span class="muted small">${T('Күтілген')}</span><pre>${esc(r.expected)}</pre></div><div><span class="muted small">${T('Сіздің нәтиже')}</span><pre>${esc(r.got)||' '}</pre></div></div>` : ''}
      ${!r.ok && r.error ? `<pre>${esc(r.error)}</pre>` : ''}</div>`).join('');
}

async function runCode(t){
  const out = document.getElementById('out'+t.id);
  out.textContent = T('Орындалуда...');
  try{
    const r = await post('/api/run', {code: document.getElementById('code'+t.id).value, stdin: document.getElementById('stdin'+t.id).value});
    out.innerHTML = esc(r.stdout) + (r.stderr ? `<span class="err">${esc(r.stderr)}</span>` : '') || `<span class="muted">${T('(бос)')}</span>`;
    if(!r.stdout && !r.stderr) out.innerHTML = `<span style="opacity:.6">${T('(программа ештеңе шығарған жоқ)')}</span>`;
  }catch(e){ out.innerHTML = `<span class="err">${esc(e.message)}</span>`; }
}

async function submit(t, i, btn){
  let answer;
  if(t.type === 'quiz'){ const c = document.querySelector(`input[name=t${t.id}]:checked`); if(!c) return toast(T('Жауапты таңдаңыз')); answer = +c.value; }
  if(t.type === 'multi'){ answer = [...document.querySelectorAll(`input[name=t${t.id}]:checked`)].map(x=>+x.value); if(!answer.length) return toast(T('Кемінде бір жауапты таңдаңыз')); }
  if(t.type === 'short' || t.type === 'open'){ answer = document.getElementById('in'+t.id).value.trim(); if(!answer) return toast(T('Жауап жазыңыз')); }
  if(t.type === 'code') answer = document.getElementById('code'+t.id).value;
  let file;
  if(t.type === 'file'){ file = document.getElementById('file'+t.id).files[0]; if(!file) return toast(T('Файлды таңдаңыз')); if(file.size > 20*1024*1024) return toast(T('Файл тым үлкен (20 МБ-тан аспауы керек)')); }
  btn.disabled = true; btn.setAttribute('aria-busy', 'true'); const old = btn.innerHTML; btn.textContent = T('Тексерілуде...');
  try{
    const r = file ? await upload('/api/submit/'+t.id, file) : await post('/api/submit/'+t.id, {answer});
    const nt = Object.assign(t, r.task);
    window.TASKS[i] = nt;
    renderTask(nt, i, r);
    if(r.xp > 0) toast(`+${r.xp} XP`);
    document.getElementById('lessonScore').textContent = `${fmt(r.lesson.score)} / ${fmt(r.lesson.max)} ${T('балл')}`;
    document.getElementById('lessonMark').textContent = `${T('Баға')}: ${r.mark ?? '—'}`;
    const nx = document.getElementById('nav-xp'); if(nx){ const nb = nx.querySelector('b'); if(nb) nb.textContent = r.total_xp; }
    toc();
  }catch(e){ toast(e.message); btn.disabled = false; btn.removeAttribute('aria-busy'); btn.innerHTML = old; }
}

// Тапсырма ұяшығының күйі: түс + сан + белгі (түске ғана сүйенбейміз)
function cellOf(t, i, firstTodo){
  const s = t.sub, p = fmt(t.points);
  if(!s) return {cls: i === firstTodo ? 'cur' : 'todo', val: `–/${p}`, html: `–/${p}`, style: '', text: `${p} ${T('балл')}`};
  if(s.status === 'pending') return {cls: 'wait', val: '…', html: ic('clock'), style: '', text: T('Тексерілуде')};
  const v = `${fmt(s.score)}/${p}`;
  if(s.full) return {cls: 'ok', val: v, html: v, style: '', text: `${T('Дұрыс!')} ${v}`};
  if(s.score > 0) return {cls: 'part', val: v, html: v, style: ` style="--fill:${Math.round(s.score * 100 / t.points)}%"`, text: v};
  return {cls: 'bad', val: v, html: v, style: '', text: v};
}

function toc(){
  const firstTodo = window.TASKS.findIndex(t => !t.sub);
  const strip = document.getElementById('strip');
  if(strip) strip.innerHTML = window.TASKS.map((t,i) => {
    const c = cellOf(t, i, firstTodo);
    return `<a class="cell ${c.cls}" href="#task-${t.id}"${c.style} aria-label="${i+1}${T('-тапсырма')}: ${esc(c.text)}" title="${esc(c.text)}">${i+1}<b>${c.html}</b></a>`;
  }).join('');
  const ul = document.getElementById('toc'); if(!ul) return;
  ul.innerHTML = window.TASKS.map((t,i) => {
    const c = cellOf(t, i, firstTodo);
    return `<li><span class="cell mini ${c.cls}"${c.style} aria-hidden="true">${i+1}</span><a class="grow" href="#task-${t.id}">${esc(t.prompt.replace(/[`*#>]/g,'').slice(0,60))}</a><span class="num">${c.val}</span></li>`;
  }).join('');
}

window.TASKS.forEach((t,i)=>renderTask(t,i));
toc();
