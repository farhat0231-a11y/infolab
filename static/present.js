// Көрсету режимі: слайдтар, пернелер, проектор ↔ мұғалім синхроны, таймерлер
(function () {
  const P = window.PRES, T = window.PRES_T, teacher = document.body.dataset.mode === 'teacher';
  const $ = s => document.querySelector(s), n = P.slides.length;
  let i = 0, black = 0, started = 0, v = -1, skew = 0;
  const bc = 'BroadcastChannel' in window ? new BroadcastChannel('infolab-' + P.plan) : null;

  function fitFull() {
    const k = Math.min(innerWidth / 1280, innerHeight / 720), s = $('#slideMain');
    s.style.transform = 'scale(' + k + ')'; s.style.left = (innerWidth - 1280 * k) / 2 + 'px'; s.style.top = (innerHeight - 720 * k) / 2 + 'px';
  }
  const fmt = sec => { const a = Math.abs(Math.round(sec)), m = Math.floor(a / 60), s = a % 60; return (sec < 0 ? '+' : '') + m + ':' + String(s).padStart(2, '0'); };

  function draw() {
    $('#slideMain').innerHTML = P.slides[i].html;
    if (!teacher) { $('#black').hidden = !black; fitFull(); return; }
    $('#slideNext').innerHTML = i + 1 < n ? P.slides[i + 1].html : '<h2>' + T.end + '</h2>';
    $('#notes').textContent = P.slides[i].notes || T.noNotes;
    $('#counter').textContent = (i + 1) + ' / ' + n;
    $('#blackBtn').classList.toggle('on', !!black);
    $('#prev').disabled = i === 0; $('#next').disabled = i === n - 1;
    window.fitSlides(); tick();
  }
  // Күйді сервермен және басқа терезелермен үйлестіру
  function apply(s) { if (s.v <= v) return; v = s.v; i = Math.min(s.i, n - 1); black = s.black; started = s.started; skew = s.now - Date.now(); draw(); }
  async function push(extra) {
    const body = Object.assign({i, black}, extra || {});
    try { const r = await fetch(P.urls.state, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}); const s = await r.json(); apply(s); if (bc) bc.postMessage(s); } catch (_) {}
  }
  async function poll() { try { apply(await (await fetch(P.urls.state)).json()); } catch (_) {} }
  if (bc) bc.onmessage = e => apply(e.data);
  const go = k => { const t = Math.max(0, Math.min(k, n - 1)); if (t === i) return; i = t; draw(); push(); };

  // Таймерлер: кезеңнің аяқталу минуты жоспардан алынады; асып кетсе қызыл және «+»
  function tick() {
    if (!teacher) return;
    const tl = $('#tLesson'), tp = $('#tPhase');
    if (!started) { tl.textContent = tp.textContent = '--:--'; tl.classList.remove('late'); tp.classList.remove('late'); return; }
    const el = (Date.now() + skew - started) / 1000, ph = P.slides[i].phase;
    const leftL = P.total * 60 - el, leftP = (P.ends[ph] || P.total) * 60 - el;
    tl.textContent = fmt(leftL); tl.classList.toggle('late', leftL < 0);
    tp.textContent = fmt(leftP); tp.classList.toggle('late', leftP < 0);
    $('#phaseLbl').textContent = P.phaseNames[ph];
  }
  setInterval(tick, 500); setInterval(poll, 1000);

  function fullscreen() { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen(); }
  document.addEventListener('keydown', e => {
    if (e.target.closest && e.target.closest('input,textarea,select')) return;
    const k = e.key;
    if (k === 'ArrowRight' || k === ' ' || k === 'PageDown') { e.preventDefault(); go(i + 1); }
    else if (k === 'ArrowLeft' || k === 'PageUp') { e.preventDefault(); go(i - 1); }
    else if (k === 'Home') go(0); else if (k === 'End') go(n - 1);
    else if (k === 'f' || k === 'F') fullscreen();
    else if (k === 'b' || k === 'B') { black = black ? 0 : 1; draw(); push(); }
  });
  $('#fsBtn').onclick = fullscreen;
  window.addEventListener('resize', () => { if (!teacher) fitFull(); else window.fitSlides(); });

  if (teacher) {
    $('#prev').onclick = () => go(i - 1); $('#next').onclick = () => go(i + 1);
    $('#blackBtn').onclick = () => { black = black ? 0 : 1; draw(); push(); };
    $('#tStart').onclick = () => push({timer: 'start'}); $('#tReset').onclick = () => push({timer: 'reset'});
    $('#openScreen').onclick = () => window.open(P.urls.screen, 'infolab-screen', 'popup,width=1280,height=720');
    const ob = $('#openTasks');
    if (P.opened) { ob.disabled = true; $('#openLbl').textContent = T.opened; }
    ob.onclick = async () => { const r = await fetch(P.urls.open, {method: 'POST'}); if (r.ok) { ob.disabled = true; $('#openLbl').textContent = T.opened; } };
  }
  draw(); poll();
})();
