(() => {
  'use strict';
  const main = document.getElementById('detailMain');
  const toast = document.getElementById('toast');
  const scoreForm = document.getElementById('detailScoreForm');
  const absenceButton = document.getElementById('detailAbsence');
  let timer = null;
  let serial = 0;

  const undoUrl = (id) => (main.dataset.undoTemplate || '').replace('999999', String(id));
  const vibrate = (ms = 12) => { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (_) {} };

  function showToast(message, undoAction = null, duration = null) {
    clearTimeout(timer);
    const current = ++serial;
    toast.innerHTML = '';
    const row = document.createElement('div');
    row.className = 'toast-row';
    const text = document.createElement('div');
    text.className = 'toast-message';
    text.textContent = message;
    row.appendChild(text);
    toast.appendChild(row);

    const ms = duration || (undoAction ? 15000 : 1900);
    if (undoAction) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'undo-btn';
      button.textContent = 'DESEGIN';
      button.addEventListener('click', async (event) => {
        event.preventDefault();
        event.stopPropagation();
        button.disabled = true;
        clearTimeout(timer);
        text.textContent = 'Aldaketa desegiten…';
        try { await undoAction(); } finally { if (current === serial) button.disabled = false; }
      });
      row.appendChild(button);
      const progress = document.createElement('div');
      progress.className = 'toast-progress';
      const bar = document.createElement('i');
      bar.style.animationDuration = `${ms}ms`;
      progress.appendChild(bar);
      toast.appendChild(progress);
    }

    toast.classList.add('show');
    timer = setTimeout(() => { if (current === serial) toast.classList.remove('show'); }, ms);
  }

  async function post(url, data = {}) {
    const body = new URLSearchParams();
    Object.entries(data).forEach(([k,v]) => body.set(k, String(v)));
    const response = await fetch(url, {method:'POST', body, headers:{'X-Requested-With':'XMLHttpRequest'}, credentials:'same-origin', cache:'no-store'});
    let payload = null;
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return payload || {};
  }

  function render(data) {
    document.getElementById('detailPoints').textContent = data.puntuak;
    const week = document.getElementById('detailWeek');
    const net = Number(data.asteko_net || 0);
    week.textContent = `Astean ${net > 0 ? '+' : ''}${net}`;
    week.classList.remove('positive','negative');
    if (net > 0) week.classList.add('positive');
    if (net < 0) week.classList.add('negative');
    document.getElementById('detailBreakPlus').textContent = `+${Number(data.asteko_plus || 0)}`;
    document.getElementById('detailBreakMinus').textContent = `−${Number(data.asteko_minus || 0)}`;
  }

  async function undo(historiaId) {
    scoreForm.style.pointerEvents = 'none';
    try {
      const data = await post(undoUrl(historiaId));
      render(data);
      vibrate(18);
      showToast('Aldaketa deseginda');
    } catch (error) {
      console.error(error);
      showToast('Ezin izan da desegin. Baliteke ondoren beste aldaketa bat egin izana.', null, 4200);
    } finally {
      scoreForm.style.pointerEvents = '';
    }
  }

  scoreForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    if (!submitter) return;
    scoreForm.style.pointerEvents = 'none';
    try {
      const data = await post(main.dataset.scoreUrl, {delta:Number(submitter.value)});
      render(data);
      vibrate();
      showToast(data.medaila_berria ? '🏅 Medaila desblokeatuta!' : 'Puntuazioa eguneratua', data.historia_id ? () => undo(data.historia_id) : null);
    } catch (error) {
      console.error(error);
      showToast('Ezin izan da eguneratu. Saiatu berriz.', null, 3200);
    } finally {
      scoreForm.style.pointerEvents = '';
    }
  });

  absenceButton?.addEventListener('click', async () => {
    absenceButton.disabled = true;
    try {
      const data = await post(main.dataset.absenceUrl);
      const active = Boolean(data.absentzia);
      absenceButton.classList.toggle('active', active);
      absenceButton.setAttribute('aria-pressed', active ? 'true' : 'false');
      absenceButton.textContent = active ? '✓ Absentzia aste honetan' : 'Absentzia aste honetan';
      vibrate(10);
      showToast(active ? 'Absentzia markatua' : 'Absentzia kendua');
    } catch (error) {
      console.error(error);
      showToast('Ezin izan da absentzia eguneratu.', null, 3200);
    } finally {
      absenceButton.disabled = false;
    }
  });
})();
