// «Сабаққа дайындық»: ҚМЖ редакторы (кезеңдер, уақыт сызбасы, сүйреу, сақтау)
(function () {
  const P = window.PLAN, t = P.t;
  const data = P.stages;
  const $ = (s, r) => (r || document).querySelector(s);
  const ic = n => '<svg class="ic" aria-hidden="true"><use href="#i-' + n + '"/></svg>';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  let dirty = false, uid = 0;

  function mark() { dirty = true; $('#savedAt').textContent = ''; }
  const sum = ph => ph.steps.reduce((a, s) => a + (+s.minutes || 0), 0);
  const total = () => data.phases.reduce((a, p) => a + sum(p), 0);

  // Уақыт сызбасы: 40 минуттық жолақ және қосынды ескертуі
  function timeline() {
    const tot = total(), scale = Math.max(tot, P.total);
    $('#timeline').innerHTML = data.phases.map(ph => ph.steps.filter(s => +s.minutes > 0).map(s =>
      '<span class="seg-s ' + ph.key + '" style="flex:' + (+s.minutes) + ' 0 0" title="' + esc(s.title) + '">' + (+s.minutes) + ' ' + esc(t.min) + '</span>').join('')).join('')
      + (tot < P.total ? '<span style="flex:' + (P.total - tot) + ' 0 0"></span>' : '');
    const el = $('#tlSum'), diff = tot - P.total;
    el.className = 'tl-sum num ' + (diff === 0 ? 'ok' : diff > 0 ? 'bad' : 'warn');
    el.textContent = tot + ' / ' + P.total + ' ' + t.min + ' · ' + (diff === 0 ? t.ok : diff > 0 ? t.over + ' ' + diff : t.under + ' ' + (-diff));
    document.querySelectorAll('.ptime').forEach(e => { e.textContent = sum(data.phases[+e.dataset.p]) + ' ' + t.min; });
  }

  function stepHtml(s, pi, si) {
    const id = 'st' + (uid++);
    const tasks = P.tasks.length ? '<div class="wide"><label>' + esc(t.tasks) + '</label><div class="taskpick">' + P.tasks.map(k =>
      '<label><input type="checkbox" data-f="task" value="' + k.id + '"' + ((s.tasks || []).includes(k.id) ? ' checked' : '') + '>' + esc(k.label) + '</label>').join('') + '</div></div>' : '';
    const ta = (f, label, wide) => '<div' + (wide ? ' class="wide"' : '') + '><label for="' + id + f + '">' + esc(label) + '</label><textarea id="' + id + f + '" data-f="' + f + '">' + esc(s[f]) + '</textarea></div>';
    return '<div class="step" draggable="false" data-p="' + pi + '" data-s="' + si + '">'
      + '<div class="step-top"><button type="button" class="btn sm handle" data-act="drag" aria-label="' + esc(t.drag) + '" title="' + esc(t.drag) + '">⠿</button>'
      + '<div class="grow"><label for="' + id + 't">' + esc(t.title) + '</label><input type="text" id="' + id + 't" data-f="title" value="' + esc(s.title) + '"></div>'
      + '<div class="mins"><label for="' + id + 'm">' + esc(t.min) + '</label><input type="number" id="' + id + 'm" data-f="minutes" min="0" max="240" value="' + (+s.minutes || 0) + '"></div>'
      + '<button type="button" class="btn sm" data-act="up" aria-label="' + esc(t.up) + '">' + ic('arrow-up') + '</button>'
      + '<button type="button" class="btn sm" data-act="down" aria-label="' + esc(t.down) + '">' + ic('arrow-down') + '</button>'
      + '<button type="button" class="btn sm danger" data-act="del" aria-label="' + esc(t.del) + '">' + ic('trash') + '</button></div>'
      + '<div class="step-body">' + ta('teacher', t.teacher) + ta('student', t.student) + ta('assess', t.assess) + ta('resources', t.res) + tasks + '</div></div>';
  }

  function render() {
    uid = 0;
    $('#phases').innerHTML = data.phases.map((ph, pi) =>
      '<section class="card phase" data-p="' + pi + '"><h2>' + esc(P.uiNames[ph.key]) + '<span class="ptime num" data-p="' + pi + '"></span></h2>'
      + '<div class="steps" data-p="' + pi + '">' + (ph.steps.map((s, si) => stepHtml(s, pi, si)).join('') || '<p class="muted small">' + esc(t.empty) + '</p>') + '</div>'
      + '<button type="button" class="btn addstep" data-act="add" data-p="' + pi + '">' + ic('plus') + esc(t.addStep) + '</button></section>').join('');
    timeline();
  }

  // Өрістерді деректерге жазу
  document.addEventListener('input', e => {
    const f = e.target.dataset && e.target.dataset.f; if (!f) return;
    const box = e.target.closest('.step'); if (!box) return;
    const s = data.phases[+box.dataset.p].steps[+box.dataset.s];
    if (f === 'task') s.tasks = [...box.querySelectorAll('[data-f=task]:checked')].map(c => +c.value);
    else s[f] = f === 'minutes' ? Math.max(0, +e.target.value || 0) : e.target.value;
    if (f === 'minutes') timeline();
    mark();
  });
  ['f-date', 'f-absent', 'f-obj', 'f-aim'].forEach(id => $('#' + id).addEventListener('input', () => {
    if (id === 'f-absent') $('#f-present').value = Math.max(0, P.students - (+$('#f-absent').value || 0));
    mark();
  }));

  // Қадамды қосу, өшіру, жылжыту (кезең шекарасынан өтуі мүмкін)
  function move(pi, si, dir) {
    const flat = [];
    data.phases.forEach((ph, i) => ph.steps.forEach((s, j) => flat.push([i, j])));
    const k = flat.findIndex(x => x[0] === pi && x[1] === si), n = k + dir;
    if (n < 0 || n >= flat.length) return;
    const [a, b] = flat[k], [c, d] = flat[n];
    if (a === c) { const arr = data.phases[a].steps; [arr[b], arr[d]] = [arr[d], arr[b]]; }
    else { const s = data.phases[a].steps.splice(b, 1)[0]; data.phases[c].steps.splice(dir > 0 ? 0 : data.phases[c].steps.length, 0, s); }
  }
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-act]'); if (!b) return;
    const act = b.dataset.act, box = b.closest('.step');
    if (act === 'add') { data.phases[+b.dataset.p].steps.push({title: '', minutes: 0, teacher: '', student: '', assess: '', resources: '', tasks: []}); }
    else if (box) {
      const pi = +box.dataset.p, si = +box.dataset.s;
      if (act === 'del') { if (!confirm(t.confirmDel)) return; data.phases[pi].steps.splice(si, 1); }
      else if (act === 'up') move(pi, si, -1); else if (act === 'down') move(pi, si, 1);
      else return;
    } else return;
    mark(); render();
  });

  // Сүйреп ретін ауыстыру (тұтқадан ғана)
  let drag = null;
  document.addEventListener('pointerdown', e => {
    const h = e.target.closest('.handle'); if (!h) return;
    h.closest('.step').draggable = true;
  });
  document.addEventListener('pointerup', () => document.querySelectorAll('.step[draggable=true]').forEach(s => s.draggable = false));
  document.addEventListener('dragstart', e => {
    const s = e.target.closest && e.target.closest('.step'); if (!s) return;
    drag = {p: +s.dataset.p, s: +s.dataset.s}; s.classList.add('drag'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', 'step');
  });
  document.addEventListener('dragover', e => {
    if (!drag) return;
    const tgt = e.target.closest('.step') || e.target.closest('.steps'); if (!tgt) return;
    e.preventDefault(); document.querySelectorAll('.over').forEach(x => x.classList.remove('over')); tgt.classList.add('over');
  });
  document.addEventListener('drop', e => {
    if (!drag) return;
    const step = e.target.closest('.step'), list = e.target.closest('.steps');
    if (!step && !list) return;
    e.preventDefault();
    const tp = +(step || list).dataset.p, ts = step ? +step.dataset.s : data.phases[tp].steps.length;
    const item = data.phases[drag.p].steps.splice(drag.s, 1)[0];
    const idx = (tp === drag.p && ts > drag.s) ? ts - 1 : ts;
    data.phases[tp].steps.splice(idx, 0, item);
    drag = null; mark(); render();
  });
  document.addEventListener('dragend', () => { drag = null; document.querySelectorAll('.drag,.over').forEach(x => x.classList.remove('drag', 'over')); });

  // Сақтау
  async function save() {
    const body = {date: $('#f-date').value, absent: +$('#f-absent').value || 0, objectives: $('#f-obj').value, aim: $('#f-aim').value, stages: data};
    try {
      const r = await fetch(P.saveUrl, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      if (!r.ok) throw 0;
      dirty = false; $('#savedAt').textContent = t.saved + ' · ' + new Date().toLocaleTimeString().slice(0, 5);
      toast(t.saved);
    } catch (_) { toast(t.fail); }
  }
  $('#saveBtn').onclick = save;
  // AI: толық ҚМЖ + слайд + сөз; нәтиже редакторда ашылады және түзетуге болады
  const aiBtn = $('#aiBtn');
  if (aiBtn) aiBtn.onclick = async () => {
    if (!confirm(t.aiConfirm)) return;
    const lbl = $('#aiLbl'), old = lbl.textContent; lbl.textContent = t.aiBusy; aiBtn.disabled = true;
    try {
      const r = await fetch(P.aiUrl, {method: 'POST'}); const j = await r.json();
      if (!r.ok) throw new Error(j.error || t.fail);
      data.phases = j.stages.phases; $('#f-aim').value = j.aim; render(); mark();
      await save();
      await fetch(P.slidesSaveUrl, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({slides: j.slides})});
      toast(t.aiDone);
    } catch (e) { toast(e.message || t.fail); }
    lbl.textContent = old; aiBtn.disabled = false;
  };
  document.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save(); } });
  window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
  render();
})();
