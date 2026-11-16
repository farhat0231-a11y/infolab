// Слайд редакторы: тізім, markdown өңдеу, алдын ала қарау, теориядан жасау, сақтау
(function () {
  const S = window.SL, t = S.t, data = S.slides, $ = s => document.querySelector(s);
  let cur = 0, dirty = false, timer = null;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const mark = () => { dirty = true; $('#savedAt').textContent = ''; };
  const title = s => (s.md.split('\n').find(l => l.trim()) || t.empty).replace(/^#+\s*/, '').slice(0, 48);

  function list() {
    $('#slist').innerHTML = data.length ? data.map((s, i) =>
      '<li><button type="button" class="' + (i === cur ? 'on' : '') + '" data-i="' + i + '"' + (i === cur ? ' aria-current="true"' : '') + '><b class="num">' + (i + 1) + '</b><span>' + esc(title(s)) + '</span><i class="ph ' + s.phase + '"></i></button></li>').join('')
      : '<li class="muted small">' + esc(t.none) + '</li>';
  }
  function load() {
    const s = data[cur];
    $('#sedit').hidden = !s; if (!s) return;
    $('#sMd').value = s.md; $('#sNotes').value = s.notes; $('#sPhase').value = s.phase; preview();
  }
  async function preview() {
    const s = data[cur]; if (!s) return;
    try {
      const r = await fetch(S.previewUrl, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({md: s.md})});
      $('#spreview .slide').innerHTML = (await r.json()).html; window.fitSlides($('#sedit'));
    } catch (_) {}
  }
  const sched = () => { clearTimeout(timer); timer = setTimeout(preview, 350); };
  $('#sMd').oninput = e => { data[cur].md = e.target.value; mark(); list(); sched(); };
  $('#sNotes').oninput = e => { data[cur].notes = e.target.value; mark(); };
  $('#sPhase').onchange = e => { data[cur].phase = e.target.value; mark(); list(); };
  $('#slist').onclick = e => { const b = e.target.closest('button[data-i]'); if (b) { cur = +b.dataset.i; list(); load(); } };
  $('#addSlide').onclick = () => { data.splice(cur + 1, 0, {phase: (data[cur] || {}).phase || 'middle', md: '## ', notes: ''}); cur = Math.min(cur + 1, data.length - 1); mark(); list(); load(); $('#sMd').focus(); };
  $('#sedit').onclick = e => {
    const b = e.target.closest('[data-sact]'); if (!b) return; const a = b.dataset.sact;
    if (a === 'del') { if (!confirm(t.del)) return; data.splice(cur, 1); cur = Math.max(0, Math.min(cur, data.length - 1)); }
    else { const n = cur + (a === 'up' ? -1 : 1); if (n < 0 || n >= data.length) return; [data[cur], data[n]] = [data[n], data[cur]]; cur = n; }
    mark(); list(); load();
  };
  if ($('#fromLib')) $('#fromLib').onclick = async () => {
    if (data.length && !confirm(t.confirm)) return;
    const r = await fetch(S.libUrl, {method: 'POST'}); if (!r.ok) return toast(t.fail);
    const j = await r.json(); data.length = 0; data.push(...j.slides); cur = 0; mark(); list(); load();
  };
  $('#fromTheory').onclick = async () => {
    if (data.length && !confirm(t.confirm)) return;
    const r = await fetch(S.theoryUrl, {method: 'POST'}); const j = await r.json();
    data.length = 0; data.push(...j.slides); cur = 0; mark(); list(); load();
  };
  // AI: ағымдағы слайдты нұсқаулық бойынша жақсарту; алдыңғы нұсқаны қайтаруға болады
  let undo = null;
  async function improve(body) {
    const s = data[cur]; if (!s) return;
    const btns = document.querySelectorAll('.aibar button'); btns.forEach(b => b.disabled = true);
    try {
      const r = await fetch(S.improveUrl, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.assign({md: s.md, notes: s.notes}, body))});
      const j = await r.json(); if (!r.ok) throw new Error(j.error || t.fail);
      undo = {i: cur, md: s.md, notes: s.notes}; s.md = j.md; s.notes = j.notes; mark(); list(); load(); $('#aiUndo').hidden = false;
    } catch (e) { toast(e.message || t.fail); }
    btns.forEach(b => b.disabled = false);
  }
  document.querySelectorAll('[data-ai]').forEach(b => b.onclick = () => improve({preset: b.dataset.ai}));
  if ($('#aiGo')) {
    $('#aiGo').onclick = () => { const v = $('#aiText').value.trim(); if (v) improve({instruction: v}); };
    $('#aiText').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); $('#aiGo').click(); } };
    $('#aiUndo').onclick = () => { if (!undo || !data[undo.i]) return; data[undo.i].md = undo.md; data[undo.i].notes = undo.notes; cur = undo.i; undo = null; $('#aiUndo').hidden = true; mark(); list(); load(); };
  }
  async function save() {
    try {
      const r = await fetch(S.saveUrl, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({slides: data})});
      if (!r.ok) throw 0; dirty = false; $('#savedAt').textContent = t.saved + ' · ' + new Date().toLocaleTimeString().slice(0, 5); toast(t.saved);
    } catch (_) { toast(t.fail); }
  }
  $('#saveBtn').onclick = save;
  document.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save(); } });
  window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
  list(); load();
})();
