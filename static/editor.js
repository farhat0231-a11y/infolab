const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let tasks = Array.isArray(window.TASKS_INIT) ? window.TASKS_INIT : [];
const ed = document.getElementById('tasksEd');
const ic = n => `<svg class="ic" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const RU = window.EDIT_LANG === 'ru';
const critEd = (d) => `<label>Бағалау критерийлері (рубрика) <span class="muted">— оқушыға көрінеді; тапсырма балы критерийлер қосындысына тең болады${RU ? '. Орысша нұсқада тек мәтінін аударыңыз' : ''}</span></label>
  <div class="crit-ed">${(d.criteria||[]).map((c,k)=>`<div class="row" style="gap:6px;margin-bottom:6px"><input type="text" class="ctext" data-k="${k}" value="${esc(c.text)}" placeholder="Критерий, мысалы: шекаралар қойылған" style="flex:1"><input type="number" class="cpts" data-k="${k}" value="${c.points}" min="0.5" step="0.5" style="width:80px" ${RU?'readonly':''}>${RU?'':`<button type="button" class="btn sm danger delcrit" aria-label="Өшіру" data-k="${k}">${ic('x')}</button>`}</div>`).join('')}</div>
  ${RU?'':'<button type="button" class="btn sm addcrit">+ критерий</button>'}
  <label>Ескертпе (тек мұғалімге көрінеді)</label><input type="text" class="rubric" value="${esc(d.rubric)}">`;

function blank(type){
  const d = {quiz:{options:['','','',''],answer:0,explain:''}, multi:{options:['','','',''],answer:[],explain:''},
    short:{answer:[''],explain:''}, code:{starter:'',tests:[{input:'',output:''}]}, open:{criteria:[{text:'',points:1},{text:'',points:1}], rubric:''}, file:{criteria:[{text:'',points:1},{text:'',points:1},{text:'',points:1}], rubric:'', accept:''}}[type];
  return {type, prompt:'', points: type==='code'||type==='file'?3: type==='open'||type==='multi'?2:1, data: d};
}

function render(){
  ed.innerHTML = tasks.length ? '' : '<div class="empty">Тапсырма жоқ. Жоғарыдағы батырмалармен қосыңыз.</div>';
  tasks.forEach((t,i)=>{
    const c = document.createElement('div'); c.className='tcard';
    const d = t.data = t.data || {};
    let extra = '';
    if(t.type==='quiz' || t.type==='multi'){
      const ans = [].concat(d.answer ?? []).map(Number);
      extra = `<label>Жауап нұсқалары <span class="muted">(дұрысын белгілеңіз)</span></label><div class="opts">` +
        (d.options||[]).map((o,k)=>`<div class="o"><input type="${t.type==='quiz'?'radio':'checkbox'}" name="ans${i}" data-k="${k}" ${ans.includes(k)?'checked':''} class="ansm">
          <input type="text" value="${esc(o)}" data-k="${k}" class="opt"><button type="button" class="btn sm danger delopt" aria-label="Өшіру" data-k="${k}">${ic('x')}</button></div>`).join('') +
        `</div><button type="button" class="btn sm addopt" style="margin-top:6px">+ нұсқа</button>
        <label>Түсіндірме (жауаптан кейін көрсетіледі)</label><input type="text" class="explain" value="${esc(d.explain)}">`;
    }
    if(t.type==='short'){
      extra = `<label>Дұрыс жауап(тар) <span class="muted">— бірнеше нұсқаны | арқылы бөліңіз, мысалы: 1024|1024 байт</span></label>
        <input type="text" class="sans" value="${esc([].concat(d.answer||[]).join('|'))}">
        <label>Түсіндірме / шешуі</label><input type="text" class="explain" value="${esc(d.explain)}">`;
    }
    if(t.type==='open'){
      extra = critEd(d);
    }
    if(t.type==='file'){
      extra = `<div class="muted small" style="margin-top:6px">Шартқа не істеу керегін қадамдап жазыңыз. Оқушы жұмысты Excel/Word т.б. бағдарламада орындап, файлды жүктейді; сіз «Тексеру» бетінде баға қоясыз.</div>
        <label>Қабылданатын файлдар <span class="muted">— мысалы: .xlsx,.xls немесе .docx,.pdf,.png (бос болса — кез келгені)</span></label><input type="text" class="accept" value="${esc(d.accept)}">
        ` + critEd(d);
    }
    const hasCrit = (t.type==='open' || t.type==='file') && (d.criteria||[]).length > 0;
    if(t.type==='code'){
      extra = `<label>Бастапқы код (оқушыға көрсетіледі)</label><textarea class="code starter" style="min-height:90px;border-radius:10px">${esc(d.starter)}</textarea>
        <label>Тесттер <span class="muted">— енгізу және күтілетін дәл шығару. «Жасырын» тест оқушыға көрінбейді</span></label>
        <div class="tests-ed">${(d.tests||[]).map((x,k)=>`<div class="trow"><textarea class="tin" data-k="${k}" placeholder="енгізу">${esc(x.input)}</textarea>
          <textarea class="tout" data-k="${k}" placeholder="күтілетін шығару">${esc(x.output)}</textarea>
          <label class="small" style="margin:6px 0"><input type="checkbox" class="thid" data-k="${k}" ${x.hidden?'checked':''}> жасырын</label>
          <button type="button" class="btn sm danger deltest" aria-label="Өшіру" data-k="${k}">${ic('x')}</button></div>`).join('')}</div>
        <div class="row" style="margin-top:6px"><button type="button" class="btn sm addtest">+ тест</button>
        <span class="muted small">Тесттерді тексеру үшін дұрыс шешімді жазыңыз:</span></div>
        <textarea class="code sol" style="min-height:80px;border-radius:10px;margin-top:6px" placeholder="# дұрыс шешім (сақталмайды, тек тексеру үшін)"></textarea>
        <button type="button" class="btn sm checksol" style="margin-top:6px">${ic('play')}Шешімді тесттермен тексеру</button><span class="small solres" style="margin-left:8px"></span>`;
    }
    c.innerHTML = `<div class="spread"><b>${i+1}. ${window.TYPES[t.type]}</b>
      <div class="row"><span class="small muted">Балл</span><input type="number" class="pts" min="1" max="30" value="${t.points}" style="width:70px" ${hasCrit?'readonly title="Критерийлер қосындысы"':''}>
      <button type="button" class="btn sm up" aria-label="Жоғары" ${i?'':'disabled'}>${ic('arrow-up')}</button><button type="button" class="btn sm down" aria-label="Төмен" ${i<tasks.length-1?'':'disabled'}>${ic('arrow-down')}</button>
      <button type="button" class="btn sm danger del">Өшіру</button></div></div>
      <label>Сұрақ / тапсырма мәтіні <span class="muted">(Markdown, &lt;code&gt;)</span></label><textarea class="prompt" style="min-height:70px">${esc(t.prompt)}</textarea>${extra}`;
    ed.appendChild(c);
    const $ = s => c.querySelector(s), $$ = s => c.querySelectorAll(s);
    $('.prompt').oninput = e => t.prompt = e.target.value;
    $('.pts').oninput = e => t.points = +e.target.value || 1;
    $('.del').onclick = () => { if(confirm('Тапсырманы өшіру керек пе?')){ tasks.splice(i,1); render(); } };
    $('.up').onclick = () => { [tasks[i-1],tasks[i]]=[tasks[i],tasks[i-1]]; render(); };
    $('.down').onclick = () => { [tasks[i+1],tasks[i]]=[tasks[i],tasks[i+1]]; render(); };
    if($('.explain')) $('.explain').oninput = e => d.explain = e.target.value;
    if($('.rubric')) $('.rubric').oninput = e => d.rubric = e.target.value;
    if($('.accept')) $('.accept').oninput = e => d.accept = e.target.value;
    const sumPts = () => { if((d.criteria||[]).length) t.points = d.criteria.reduce((a,c) => a + (+c.points || 0), 0); };
    $$('.ctext').forEach(x => x.oninput = e => d.criteria[+x.dataset.k].text = e.target.value);
    $$('.cpts').forEach(x => x.oninput = e => { d.criteria[+x.dataset.k].points = +e.target.value || 0; sumPts(); const p = $('.pts'); if(p) p.value = t.points; });
    $$('.delcrit').forEach(x => x.onclick = () => { d.criteria.splice(+x.dataset.k, 1); sumPts(); render(); });
    if($('.addcrit')) $('.addcrit').onclick = () => { (d.criteria = d.criteria || []).push({text:'',points:1}); sumPts(); render(); };
    if($('.sans')) $('.sans').oninput = e => d.answer = e.target.value.split('|').map(s=>s.trim()).filter(Boolean);
    $$('.opt').forEach(x => x.oninput = e => d.options[+x.dataset.k] = e.target.value);
    $$('.ansm').forEach(x => x.onchange = () => {
      if(t.type==='quiz') d.answer = +x.dataset.k;
      else d.answer = [...$$('.ansm')].filter(y=>y.checked).map(y=>+y.dataset.k);
    });
    $$('.delopt').forEach(x => x.onclick = () => { const k=+x.dataset.k; d.options.splice(k,1);
      if(t.type==='quiz'){ if(d.answer===k) d.answer=0; else if(d.answer>k) d.answer--; }
      else d.answer = d.answer.filter(a=>a!==k).map(a=>a>k?a-1:a); render(); });
    if($('.addopt')) $('.addopt').onclick = () => { d.options.push(''); render(); };
    if(t.type==='code'){
      enhanceCodeArea($('.starter')); enhanceCodeArea($('.sol'));
      $('.starter').oninput = e => d.starter = e.target.value;
      $$('.tin').forEach(x => x.oninput = e => d.tests[+x.dataset.k].input = e.target.value);
      $$('.tout').forEach(x => x.oninput = e => d.tests[+x.dataset.k].output = e.target.value);
      $$('.thid').forEach(x => x.onchange = e => d.tests[+x.dataset.k].hidden = e.target.checked);
      $$('.deltest').forEach(x => x.onclick = () => { d.tests.splice(+x.dataset.k,1); render(); });
      $('.addtest').onclick = () => { d.tests.push({input:'',output:''}); render(); };
      $('.checksol').onclick = async () => {
        const r = await fetch('/teacher/test-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('.sol').value,tests:d.tests})}).then(r=>r.json());
        $('.solres').innerHTML = (r.passed===r.total ? ic('check') : ic('x')) + ' ' + `${r.passed}/${r.total} тест өтті` +
          r.results.filter(x=>!x.ok).map(x=>` · тест ${x.n}: ${esc((x.error||'').split('\n').pop()) || 'нәтиже сәйкес емес'}`).join('');
      };
    }
  });
}

document.getElementById('addBtns').innerHTML = Object.entries(window.TYPES).map(([k,v])=>`<button type="button" class="btn sm" data-t="${k}">+ ${v}</button>`).join('');
document.querySelectorAll('#addBtns button').forEach(b => b.onclick = () => { tasks.push(blank(b.dataset.t)); render(); ed.lastElementChild?.scrollIntoView({behavior:'smooth',block:'center'}); });
document.getElementById('form').onsubmit = () => { document.getElementById('tasks_json').value = JSON.stringify(tasks); };
render();

// Теорияның алдын ала көрінісі
const th = document.getElementById('theory'), pv = document.getElementById('preview');
let pt;
async function preview(){
  if(!th || !pv) return;
  const r = await fetch('/teacher/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({md:th.value})});
  pv.innerHTML = (await r.json()).html || '<div class="empty">Алдын ала көрініс</div>';
}
if(th) th.oninput = () => { clearTimeout(pt); pt = setTimeout(preview, 350); };
preview();

async function aiGen(what){
  const st = document.getElementById('aiStatus');
  if(what!=='theory' && tasks.length && !confirm('Қазіргі тапсырмалар AI жасағандарымен ауыстырылады. Жалғастыру керек пе?')) return;
  st.innerHTML = ic('clock') + ' AI жасап жатыр (30–60 секунд)...';
  try{
    const r = await fetch(`/teacher/lesson/${window.LID}/ai`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({source:document.getElementById('aiSource').value, what})}).then(r=>r.json());
    if(r.error) throw new Error(r.error);
    if(th && r.theory && what!=='tasks'){ th.value = r.theory; preview(); }
    if(r.tasks && r.tasks.length && what!=='theory'){ tasks = r.tasks; render(); }
    st.innerHTML = ic('check') + ' Дайын! Тексеріп, «Сақтау» басыңыз.';
  }catch(e){ st.innerHTML = ic('x') + ' ' + esc(e.message); }
}

function importJson(){
  const st = document.getElementById('impStatus');
  try{
    let txt = document.getElementById('jsonImport').value.trim().replace(/^```(json)?/,'').replace(/```$/,'');
    const j = JSON.parse(txt);
    if(th && typeof j.theory === 'string' && j.theory){ th.value = j.theory; preview(); }
    if(Array.isArray(j.tasks)){ tasks = j.tasks; render(); }
    st.innerHTML = ic('check') + ` ${(j.tasks||[]).length} тапсырма қосылды. Тексеріп, «Сақтау» басыңыз.`;
  }catch(e){ st.innerHTML = ic('x') + ' JSON қате: ' + esc(e.message); }
}
