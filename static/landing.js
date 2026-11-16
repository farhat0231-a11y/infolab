// Басты бет: «қазір» жарығы және тірі тексеру (нәтиже сақталмайды)
(function(){
  const grid = document.querySelector('.grid'), lamp = document.querySelector('.lamp');
  const now = document.querySelector('.plate[data-now]');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  function place(el, instant){
    if(!el || !lamp || getComputedStyle(el).display === 'none') return;
    const g = grid.getBoundingClientRect(), r = el.getBoundingClientRect();
    lamp.style.transition = instant ? 'none' : '';
    lamp.style.width = r.width + 'px'; lamp.style.height = r.height + 'px';
    lamp.style.transform = `translate(${r.left - g.left}px, ${r.top - g.top}px)`;
  }
  if(now && lamp){
    // жарық бірінші тақтайшадан басталып, бүгінгі сабаққа жылжиды
    const first = grid.querySelector('.col .plate');
    place(reduce ? now : first, true);
    lamp.classList.add('on'); grid.classList.add('lit');
    lamp.getBoundingClientRect();  // бастапқы орынды бекіту, содан кейін жылжыту
    setTimeout(() => place(now, reduce), 120);
    const settle = () => place(now, true);
    if(document.fonts) document.fonts.ready.then(() => setTimeout(settle, 1100));
    addEventListener('resize', settle);
  }

  const run = document.getElementById('demo-run'), code = document.getElementById('demo-code');
  const tests = [...document.querySelectorAll('#demo-tests .plate.t')], score = document.getElementById('demo-score');
  const L = window.L10N || {};
  const ICON = {ok: '<svg class="ic" aria-hidden="true"><use href="#i-check"/></svg>', bad: '<svg class="ic" aria-hidden="true"><use href="#i-x"/></svg>',
                wait: '<svg class="ic" aria-hidden="true"><use href="#i-clock"/></svg>', part: '<b>½</b>', todo: ''};
  const stamp = (el, k) => { const s = el.querySelector('.stamp'); if(s){ s.className = 'stamp ' + k + (s.classList.contains('big') ? ' big' : ''); s.innerHTML = ICON[k]; } };
  code.addEventListener('keydown', e => {
    if(e.key === 'Tab' && !e.shiftKey){ e.preventDefault(); code.setRangeText('    ', code.selectionStart, code.selectionEnd, 'end'); }
    if(e.key === 'Enter' && (e.ctrlKey || e.metaKey)){ e.preventDefault(); run.click(); }
  });
  run.addEventListener('click', async () => {
    run.disabled = true;
    tests.forEach(t => { t.className = 'plate t wait'; stamp(t, 'wait'); t.querySelector('.st').textContent = L.wait; const e = t.querySelector('.err'); if(e) e.remove(); });
    score.classList.remove('full', 'part'); stamp(score, 'wait');
    try{
      const r = await fetch('/api/demo', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code: code.value})});
      const d = await r.json();
      if(!r.ok) throw new Error(d.error || L.fail);
      d.results.forEach((res, i) => {
        const t = tests[i]; if(!t) return;
        t.className = 'plate t ' + (res.ok ? 'ok' : 'bad'); stamp(t, res.ok ? 'ok' : 'bad');
        t.querySelector('.st').textContent = res.ok ? L.ok : L.bad + (res.got != null && !res.error ? ': ' + String(res.got).trim().slice(0, 20) : '');
        if(res.error){ const p = document.createElement('p'); p.className = 'err'; p.textContent = res.error.split('\n').filter(Boolean).pop(); t.append(p); }
      });
      score.querySelector('.num').textContent = `${d.passed}/${d.total}`;
      const k = d.passed === d.total ? 'ok' : d.passed > 0 ? 'part' : 'bad';
      score.classList.add(k === 'ok' ? 'full' : k === 'part' ? 'part' : 'x'); stamp(score, k);
    }catch(e){
      tests.forEach(t => { t.className = 'plate t'; stamp(t, 'todo'); t.querySelector('.st').textContent = e.message || L.fail; });
      stamp(score, 'todo');
    }finally{ run.disabled = false; }
  });
})();
