// Слайдтарды қорапқа сыйғызу: .fit ішіндегі 1280×720 парақ масштабталады
window.fitSlides = function (root) {
  (root || document).querySelectorAll('.fit').forEach(box => {
    const sl = box.firstElementChild; if (!sl) return;
    const w = box.clientWidth; if (!w) return;
    const k = w / 1280; sl.style.transform = 'scale(' + k + ')'; box.style.height = (720 * k) + 'px';
  });
};
window.addEventListener('resize', () => window.fitSlides());
