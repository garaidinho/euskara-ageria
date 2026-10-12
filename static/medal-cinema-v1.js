/* Euskara Ageria — medal cinema V1. Visual only: never changes points or medals. */
(function () {
  'use strict';

  const scene = document.getElementById('medalCinema');
  if (!scene || scene.dataset.initialized === '1') return;
  scene.dataset.initialized = '1';

  const medal = Number(scene.dataset.medal);
  if (!Number.isInteger(medal) || medal < 2 || medal > 5) return;
  const original = document.querySelector('.medal-item[data-medal="' + medal + '"] .badge-shell');
  const hero = scene.querySelector('.cinema-medal');
  const particleLayer = scene.querySelector('.cinema-particles');
  const next = document.querySelector('.medal-item[data-medal="' + (medal + 1) + '"]');
  if (!original || !hero || !particleLayer) return;

  const reducedMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion) {
    if (next) next.classList.add('focus');
    scene.classList.add('is-done');
    return;
  }

  const body = document.body;
  body.classList.add('ea-medal-preparing');

  // A layer in BODY (not in the scaled profile) allows an accurate spotlight.
  function positionSpotlight() {
    const box = original.getBoundingClientRect();
    const width = window.innerWidth || document.documentElement.clientWidth;
    const height = window.innerHeight || document.documentElement.clientHeight;
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const captionY = y > height * .53
      ? Math.max(62, y - 112)
      : Math.min(height - 65, y + 132);

    scene.style.setProperty('--cx', Math.max(10, Math.min(width - 10, x)) + 'px');
    scene.style.setProperty('--cy', Math.max(10, Math.min(height - 10, y)) + 'px');
    scene.style.setProperty('--caption-y', captionY + 'px');
    scene.style.setProperty('--medal-size', Math.max(32, box.width) + 'px');
  }

  function prepareParticles() {
    const fragment = document.createDocumentFragment();
    // Fixed, repeatable patterns produce a fuller shower than random noise.
    // Every particle animates independently using transform and opacity.
    for (let i = 0; i < 78; i++) {
      const particle = document.createElement('i');
      const kind = i % 7 === 0 ? 'trail' : (i % 3 === 0 ? 'diamond' : 'star');
      particle.className = 'cinema-particle ' + kind;
      const angle = i * 2.399963229728653 + (i % 5) * .16;
      const distance = 68 + ((i * 59) % 165);
      const dx = Math.cos(angle) * distance;
      const dy = Math.sin(angle) * distance * .9;
      const size = 3 + ((i * 7) % 10);
      particle.style.setProperty('--dx', dx.toFixed(1) + 'px');
      particle.style.setProperty('--dy', dy.toFixed(1) + 'px');
      particle.style.setProperty('--ps', size + 'px');
      particle.style.setProperty('--plen', (23 + ((i * 11) % 44)) + 'px');
      particle.style.setProperty('--pdur', (780 + ((i * 113) % 800)) + 'ms');
      particle.style.setProperty('--pdelay', ((i * 47) % 260) + 'ms');
      particle.style.setProperty('--turn', (60 + ((i * 37) % 360)) + 'deg');
      if (i % 8 === 0) particle.style.backgroundColor = '#ffe39a';
      fragment.appendChild(particle);
    }
    particleLayer.appendChild(fragment);
  }

  prepareParticles();
  positionSpotlight();

  const timers = [];
  function later(delay, action) {
    timers.push(window.setTimeout(action, delay));
  }

  function startScene() {
    if (!document.body.contains(scene)) return;
    positionSpotlight();
    body.classList.add('ea-medal-playing');
    scene.classList.add('is-active');
    later(650, function () {
      scene.classList.add('is-charging');
    });
    later(1475, function () {
      scene.classList.remove('is-charging');
      hero.classList.remove('locked');
      hero.classList.add('unlocked');
      scene.classList.add('is-revealed');
    });
    later(3260, function () {
      scene.classList.add('is-settling');
    });
    later(3870, function () {
      // Fade back into the real, already-unlocked medal in the profile.
      body.classList.remove('ea-medal-preparing');
      body.classList.remove('ea-medal-playing');
      scene.classList.add('is-fading');
      if (next) next.classList.add('focus');
    });
    later(4550, function () {
      scene.classList.add('is-done');
      scene.classList.remove('is-active');
    });
  }

  // The standard portal intro stays untouched (1.65 s).
  // Wait for it before darkening the profile.
  later(1850, startScene);

  window.addEventListener('resize', positionSpotlight, { passive: true });
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', positionSpotlight, { passive: true });
  }
  window.addEventListener('pagehide', function () {
    for (const timer of timers) window.clearTimeout(timer);
  }, { once: true });
})();
