(() => {
  'use strict';

  const main = document.getElementById('teacherMain');
  const toast = document.getElementById('toast');
  const searchInput = document.getElementById('studentSearch');
  const sortSelect = document.getElementById('studentSort');
  const emptySearch = document.getElementById('emptySearch');
  const compactToggle = document.getElementById('compactToggle');
  const undoTemplate = main?.dataset.undoTemplate || '';

  let toastTimer = null;
  let toastSerial = 0;

  function vibrate(ms = 14) {
    try { if (navigator.vibrate) navigator.vibrate(ms); } catch (_) {}
  }

  function showToast(message, {special = false, undoAction = null, duration = null} = {}) {
    if (!toast) return;
    clearTimeout(toastTimer);
    const serial = ++toastSerial;
    const undoDuration = duration || 15000;
    toast.innerHTML = '';
    toast.style.background = special ? '#116149' : '#1d1d20';

    const row = document.createElement('div');
    row.className = 'toast-row';
    const text = document.createElement('div');
    text.className = 'toast-message';
    text.textContent = message;
    row.appendChild(text);

    if (undoAction) {
      const undo = document.createElement('button');
      undo.type = 'button';
      undo.className = 'undo-btn';
      undo.textContent = 'DESEGIN';
      undo.addEventListener('click', async (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (undo.disabled) return;
        undo.disabled = true;
        clearTimeout(toastTimer);
        text.textContent = 'Aldaketa desegiten…';
        try {
          await undoAction();
        } finally {
          if (serial === toastSerial) undo.disabled = false;
        }
      });
      row.appendChild(undo);

      const progress = document.createElement('div');
      progress.className = 'toast-progress';
      const bar = document.createElement('i');
      bar.style.animationDuration = `${undoDuration}ms`;
      progress.appendChild(bar);
      toast.appendChild(row);
      toast.appendChild(progress);
      toast.classList.add('show');
      toastTimer = setTimeout(() => {
        if (serial === toastSerial) toast.classList.remove('show');
      }, undoDuration);
      return;
    }

    toast.appendChild(row);
    toast.classList.add('show');
    const ms = duration || (special ? 3000 : 1900);
    toastTimer = setTimeout(() => {
      if (serial === toastSerial) toast.classList.remove('show');
    }, ms);
  }

  async function postData(url, data = {}) {
    const body = new URLSearchParams();
    Object.entries(data).forEach(([key, value]) => body.set(key, String(value)));
    const response = await fetch(url, {
      method: 'POST',
      body,
      headers: {'X-Requested-With': 'XMLHttpRequest'},
      credentials: 'same-origin',
      cache: 'no-store'
    });
    let payload = null;
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.payload = payload;
      throw error;
    }
    return payload || {};
  }

  function setBusy(card, busy) {
    card.classList.toggle('busy', busy);
    card.querySelectorAll('.score-btn, .js-absence-btn').forEach((button) => {
      button.disabled = busy;
    });
  }

  function renderWeek(card, data) {
    const pill = card.querySelector('.js-week-pill');
    const netNode = card.querySelector('.js-week-net');
    const breakdown = card.querySelector('.js-week-breakdown');
    if (!pill || !netNode || !breakdown) return;

    const net = Number(data.asteko_net || 0);
    pill.classList.remove('positive', 'negative');
    if (net > 0) pill.classList.add('positive');
    if (net < 0) pill.classList.add('negative');
    netNode.textContent = `${net > 0 ? '+' : ''}${net}`;

    const plus = Number(data.asteko_plus || 0);
    const minus = Number(data.asteko_minus || 0);
    breakdown.innerHTML = plus || minus
      ? `<span class="break-plus">+${plus}</span> · <span class="break-minus">−${minus}</span>`
      : '';

    card.dataset.weekNet = String(net);
  }

  function updateSummary(card, data) {
    const oldPlus = Number(card.dataset.weekPlus || 0);
    const oldMinus = Number(card.dataset.weekMinus || 0);
    const newPlus = Number(data.asteko_plus || 0);
    const newMinus = Number(data.asteko_minus || 0);
    const plusNode = document.getElementById('summaryPlus');
    const minusNode = document.getElementById('summaryMinus');

    if (plusNode) {
      const current = Number((plusNode.textContent || '0').replace(/[^0-9]/g, '')) || 0;
      plusNode.textContent = `+${Math.max(0, current + newPlus - oldPlus)}`;
    }
    if (minusNode) {
      const current = Number((minusNode.textContent || '0').replace(/[^0-9]/g, '')) || 0;
      minusNode.textContent = `−${Math.max(0, current + newMinus - oldMinus)}`;
    }

    card.dataset.weekPlus = String(newPlus);
    card.dataset.weekMinus = String(newMinus);
  }

  const normalize = (value) => (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();

  function compareCards(a, b, mode) {
    const nameA = normalize(a.dataset.studentName);
    const nameB = normalize(b.dataset.studentName);
    const scoreA = Number(a.dataset.score || 0);
    const scoreB = Number(b.dataset.score || 0);
    const weekA = Number(a.dataset.weekNet || 0);
    const weekB = Number(b.dataset.weekNet || 0);
    const minusA = Number(a.dataset.weekMinus || 0);
    const minusB = Number(b.dataset.weekMinus || 0);
    const absentA = Number(a.dataset.absence || 0);
    const absentB = Number(b.dataset.absence || 0);

    if (mode === 'score-asc') return scoreA - scoreB || nameA.localeCompare(nameB);
    if (mode === 'score-desc') return scoreB - scoreA || nameA.localeCompare(nameB);
    if (mode === 'week-asc') return weekA - weekB || nameA.localeCompare(nameB);
    if (mode === 'minus-desc') return minusB - minusA || nameA.localeCompare(nameB);
    if (mode === 'absence-desc') return absentB - absentA || nameA.localeCompare(nameB);
    return nameA.localeCompare(nameB);
  }

  let filterFrame = 0;
  function applyFilterAndSort() {
    cancelAnimationFrame(filterFrame);
    filterFrame = requestAnimationFrame(() => {
      const query = normalize(searchInput?.value || '');
      const mode = sortSelect?.value || 'name';
      let visibleTotal = 0;

      document.querySelectorAll('[data-section]').forEach((section) => {
        const grid = section.querySelector('.student-grid');
        if (!grid) return;
        const cards = Array.from(grid.querySelectorAll('.student-card'));
        cards.sort((a, b) => compareCards(a, b, mode)).forEach((card) => grid.appendChild(card));

        let visible = 0;
        cards.forEach((card) => {
          const show = !query || normalize(card.dataset.studentName).includes(query);
          card.hidden = !show;
          if (show) visible += 1;
        });

        visibleTotal += visible;
        section.hidden = visible === 0;
        const count = section.querySelector('.section-count');
        if (count) count.textContent = `${visible} ikasle`;
      });

      emptySearch?.classList.toggle('hidden', visibleTotal !== 0);
    });
  }

  function undoUrl(id) {
    return undoTemplate.replace('999999', String(id));
  }

  async function undoDelta(card, historiaId) {
    setBusy(card, true);
    try {
      const data = await postData(undoUrl(historiaId), {});
      card.querySelector('.js-total-points').textContent = data.puntuak;
      card.dataset.score = String(data.puntuak);
      updateSummary(card, data);
      renderWeek(card, data);
      applyFilterAndSort();
      vibrate(18);
      showToast('Aldaketa deseginda', {duration: 1900});
    } catch (error) {
      console.error(error);
      showToast('Ezin izan da desegin. Baliteke ondoren beste aldaketa bat egin izana.', {duration: 4200});
    } finally {
      setBusy(card, false);
    }
  }

  async function applyDelta(card, delta) {
    setBusy(card, true);
    try {
      const data = await postData(card.dataset.scoreUrl, {delta});
      card.querySelector('.js-total-points').textContent = data.puntuak;
      card.dataset.score = String(data.puntuak);
      updateSummary(card, data);
      renderWeek(card, data);
      applyFilterAndSort();
      vibrate(12);

      const message = data.medaila_berria ? '🏅 Medaila desblokeatuta!' : 'Puntuazioa eguneratua';
      const undoAction = data.historia_id ? () => undoDelta(card, data.historia_id) : null;
      showToast(message, {special: Boolean(data.medaila_berria), undoAction, duration: 15000});
    } catch (error) {
      console.error(error);
      showToast('Ezin izan da eguneratu. Saiatu berriz.', {duration: 3200});
    } finally {
      setBusy(card, false);
    }
  }

  document.querySelectorAll('.js-score-form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const submitter = event.submitter;
      if (!submitter) return;
      applyDelta(form.closest('.student-card'), Number(submitter.value));
    });
  });

  const dialog = document.getElementById('deltaDialog');
  const amount = document.getElementById('customAmount');
  const dialogTitle = document.getElementById('dialogTitle');
  const dialogEyebrow = document.getElementById('dialogEyebrow');
  let customCard = null;
  let customSign = 1;

  function openCustom(card, sign) {
    customCard = card;
    customSign = sign;
    amount.value = 2;
    dialogEyebrow.textContent = sign > 0 ? 'Puntuak gehitu' : 'Puntuak kendu';
    dialogEyebrow.style.color = sign > 0 ? '#08795c' : '#c31243';
    dialogTitle.textContent = card.dataset.studentName;
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
      setTimeout(() => amount.focus(), 50);
    } else {
      const raw = prompt(sign > 0 ? 'Zenbat puntu gehitu?' : 'Zenbat puntu kendu?', '2');
      const n = Number(raw);
      if (Number.isInteger(n) && n > 0 && n <= 20) applyDelta(card, sign * n);
    }
  }

  document.querySelectorAll('.js-custom').forEach((button) => {
    button.addEventListener('click', () => openCustom(button.closest('.student-card'), Number(button.dataset.sign)));
  });
  document.querySelectorAll('.js-preset').forEach((button) => {
    button.addEventListener('click', () => { amount.value = button.dataset.value; });
  });
  document.getElementById('dialogClose')?.addEventListener('click', () => dialog.close());
  document.getElementById('dialogConfirm')?.addEventListener('click', () => {
    const n = Math.min(20, Math.max(1, parseInt(amount.value, 10) || 0));
    if (!customCard || !n) return;
    dialog.close();
    applyDelta(customCard, customSign * n);
  });

  document.querySelectorAll('.js-absence-form').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const card = form.closest('.student-card');
      const button = form.querySelector('.js-absence-btn');
      button.disabled = true;
      try {
        const data = await postData(form.action, {});
        const wasActive = card.dataset.absence === '1';
        const isActive = Boolean(data.absentzia);
        card.dataset.absence = isActive ? '1' : '0';
        button.classList.toggle('absence-active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        card.querySelector('.js-absence-badge')?.classList.toggle('hidden', !isActive);

        const count = document.getElementById('absenceCount');
        if (count) {
          count.textContent = String(Math.max(0, Number(count.textContent || 0) + (isActive && !wasActive ? 1 : !isActive && wasActive ? -1 : 0)));
        }
        if (sortSelect?.value === 'absence-desc') applyFilterAndSort();
        vibrate(10);
        showToast(isActive ? 'Absentzia markatua' : 'Absentzia kendua');
      } catch (error) {
        console.error(error);
        showToast('Ezin izan da absentzia eguneratu.', {duration: 3200});
      } finally {
        button.disabled = false;
      }
    });
  });

  searchInput?.addEventListener('input', applyFilterAndSort, {passive: true});
  sortSelect?.addEventListener('change', applyFilterAndSort);

  function syncCompactLabel() {
    const compact = document.documentElement.classList.contains('compact-view');
    if (!compactToggle) return;
    compactToggle.textContent = compact ? 'Ikuspegia: Trinkoa' : 'Ikuspegia: Osoa';
    compactToggle.setAttribute('aria-pressed', compact ? 'true' : 'false');
  }

  compactToggle?.addEventListener('click', () => {
    const compact = document.documentElement.classList.toggle('compact-view');
    try { localStorage.setItem('ea-compact-view', compact ? '1' : '0'); } catch (_) {}
    syncCompactLabel();
  });

  syncCompactLabel();
  applyFilterAndSort();
})();
