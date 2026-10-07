import {label, ui, displayStatus, systemLabel, translateMarked} from './i18n.js';
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let releasePreviousImages = () => {};

// Reads are bound to the launching project and dialog session. A late response
// may not replace a different dialog, and no OCR value is approved by this UI.
export async function openOCR(ctx, fileId, {drafts = new Map()} = {}) {
  releasePreviousImages();
  const projectBase = ctx.projectPath('');
  const path = suffix => projectBase + suffix;
  const footer = `<button type="button" class="button" data-action="close-modal">${label('Close')}</button>`;
  ctx.openModal('Scanned page review', `<p role="status">${label('Loading scanned pages…')}</p>`, footer);
  let session = ctx.captureDialogSession?.();
  const current = () => !ctx.isDialogCurrent || ctx.isDialogCurrent(session);
  let data, caps;
  try {
    [data, caps] = await Promise.all([
      ctx.request(path(`/files/${encodeURIComponent(fileId)}/ocr`)), ctx.request('/ocr'),
    ]);
  } catch(error) {
    if(current()) {
      ctx.openModal('Scanned page review', `<p>${label('Loading scanned pages failed. Close this dialog and try again.')}</p>`, footer);
      ctx.error(error);
    }
    return;
  }
  if(!current()) return;
  const editable = ['engineer', 'reviewer'].includes(ctx.role), reviewer = ctx.role === 'reviewer';
  const canExtract = editable && caps.enabled && caps.available;
  ctx.openModal('Scanned page review', `<p>${label('OCR text is unverified until a reviewer checks the page image, every number, unit and table column.')}</p><p>${label('Optional local OCR')}: ${esc(caps.provider || ui('Unavailable'))} · ${label(caps.enabled ? 'Enabled' : 'Disabled')}</p>${editable ? `<form method="post" id="ocr-extract-form" class="form-stack"><label>${label('PDF page')}<input name="page" type="number" min="1" max="200" required value="1"></label><button type="submit" class="button" ${canExtract ? '' : 'disabled'}>${label('Recognize selected page')}</button></form>${canExtract ? '' : `<p class="field-note">${label('OCR is disabled or unavailable. Existing pages can still be reviewed.')}</p>`}` : ''}<div>${data.items.map(r => `<article class="list-card" data-ocr-record="${esc(r.id)}"><h3>${label('PDF page')} ${r.page} · <span data-i18n-status="${esc(r.state)}">${esc(displayStatus(r.state))}</span></h3><img class="ocr-image" data-ocr-image="${esc(r.image_file_id)}" alt="${esc(ui('Original page image'))}" data-i18n-alt="Original page image"><p class="field-note" data-ocr-image-status role="status">${label('Loading page image…')}</p><button type="button" class="button small" data-ocr-retry hidden>${label('Retry page image')}</button><details class="raw-details"><summary>${label('Recognition text and line positions')}</summary><pre class="code-block">${esc(JSON.stringify(r.lines, null, 2))}</pre></details>${r.state === 'PENDING_REVIEW' && reviewer ? `<form method="post" class="ocr-confirm-form form-stack" data-ocr="${esc(r.id)}"><label>${label('Corrected transcription')}<textarea name="text" rows="8" required maxlength="200000">${esc(drafts.get(r.id)?.text ?? r.text)}</textarea></label><label>${label('Review reason')}<textarea name="reason" rows="2" required maxlength="1000">${esc(drafts.get(r.id)?.reason ?? '')}</textarea></label><label class="checkbox-label"><input name="confirmed" type="checkbox" required disabled>${label('I checked decimals, minus signs, units and table column relationships against the image.')}</label><button type="submit" class="button primary" disabled>${label('Confirm page transcription')}</button></form>` : `<pre class="code-block">${esc(r.confirmed_text || r.text)}</pre><p>${label('Confirmed by')}: ${esc(r.confirmed_by || '—')}</p>`}</article>`).join('')}</div>`, footer);
  session = ctx.captureDialogSession?.();
  const modal = document.getElementById('modal');
  let mutationPending = false, frozenControls = new Map();
  const pages = [...modal.querySelectorAll('[data-ocr-record]')].map(article => ({
    article, image:article.querySelector('[data-ocr-image]'), status:article.querySelector('[data-ocr-image-status]'),
    retry:article.querySelector('[data-ocr-retry]'), form:article.querySelector('.ocr-confirm-form'),
    ready:false, loading:false, request:0,
  }));
  const urls = new Set();
  let cleanupTimer;
  const cleanup = () => {
    for(const url of urls) URL.revokeObjectURL(url);
    urls.clear(); clearTimeout(cleanupTimer); modal.removeEventListener('close', onClose);
    if(releasePreviousImages === cleanup) releasePreviousImages = () => {};
  };
  const onClose = () => { if(!modal.open) cleanup(); };
  modal.addEventListener('close', onClose);
  releasePreviousImages = cleanup;
  cleanupTimer = setTimeout(cleanup, 300000);
  cleanupTimer.unref?.();
  const syncConfirmation = page => {
    if(!page.form || !current()) return;
    page.form.querySelector('[name="confirmed"]').disabled = !page.ready || mutationPending;
    page.form.querySelector('[type="submit"]').disabled = !page.ready || mutationPending;
  };
  const setPending = value => {
    mutationPending = value;
    ctx.setDialogPending?.(value);
    if(value) {
      frozenControls = new Map([...modal.querySelectorAll('form input, form textarea, form select, form button')].map(el => [el, el.disabled]));
      for(const el of frozenControls.keys()) el.disabled = true;
    } else {
      for(const [el, wasDisabled] of frozenControls) if(el.isConnected) el.disabled = wasDisabled;
      frozenControls.clear();
      for(const page of pages) syncConfirmation(page);
    }
  };
  const rememberDrafts = () => new Map(pages.filter(page => page.form).map(page => [page.form.dataset.ocr, {
    text:page.form.elements.namedItem('text').value,
    reason:page.form.elements.namedItem('reason').value,
  }]));
  const mutate = async (url, body) => {
    if(!current() || mutationPending) return;
    const savedDrafts = rememberDrafts();
    setPending(true);
    try {
      await ctx.request(url, {method:'POST', body});
      if(!current()) return;
      await ctx.refresh();
      if(current()) await openOCR(ctx, fileId, {drafts:savedDrafts});
    } catch(error) { if(current()) ctx.error(error); }
    finally { if(current()) setPending(false); }
  };

  // Bind all form handlers before starting any page-image request. Failed or
  // slow images must never leave a native POST form in the dialog.
  const extract = modal.querySelector('#ocr-extract-form');
  extract?.addEventListener('submit', event => {
    event.preventDefault();
    if(!canExtract || !current() || mutationPending) return;
    const page = Number(extract.elements.namedItem('page').value);
    void mutate(path(`/files/${encodeURIComponent(fileId)}/ocr`), {page});
  });
  for(const page of pages) {
    page.form?.addEventListener('submit', event => {
      event.preventDefault();
      if(!current() || mutationPending) return;
      if(!page.ready) { ctx.error(new Error('Load and inspect the page image before confirming numbers, units and columns.')); return; }
      const form = page.form;
      if(!form.elements.namedItem('confirmed').checked) { ctx.error(new Error('Please complete this field.')); return; }
      void mutate(path(`/ocr/${encodeURIComponent(form.dataset.ocr)}/confirm`), {
        text:form.elements.namedItem('text').value,
        reason:form.elements.namedItem('reason').value,
        numbers_units_columns_checked:true,
      });
    });
  }
  const loadImage = async page => {
    if(!current() || page.loading) return;
    const generation = ++page.request;
    page.ready = false; page.loading = true; page.retry.hidden = true;
    if(page.form) page.form.elements.namedItem('confirmed').checked = false;
    page.status.innerHTML = label('Loading page image…');
    syncConfirmation(page);
    let url;
    try {
      const response = await ctx.request(path(`/files/${encodeURIComponent(page.image.dataset.ocrImage)}/content`), {raw:true});
      const bytes = await response.arrayBuffer();
      if(!current() || generation !== page.request) return;
      url = URL.createObjectURL(new Blob([bytes], {type:'image/png'})); urls.add(url);
      if(typeof page.image.decode === 'function') {
        page.image.src = url;
        await page.image.decode();
      } else {
        await new Promise((resolve, reject) => {
          const loaded = () => { page.image.removeEventListener('error', failed); resolve(); };
          const failed = () => { page.image.removeEventListener('load', loaded); reject(new Error('Page image could not be loaded. Retry before confirming the transcription.')); };
          page.image.addEventListener('load', loaded, {once:true});
          page.image.addEventListener('error', failed, {once:true}); page.image.src = url;
        });
      }
      if(!current() || generation !== page.request) { URL.revokeObjectURL(url); urls.delete(url); return; }
      if(!page.image.naturalWidth || !page.image.isConnected) throw new Error('Page image could not be loaded. Retry before confirming the transcription.');
      page.ready = true;
      page.status.innerHTML = label('Page image loaded. Review the transcription against this image.');
    } catch(error) {
      if(url) { URL.revokeObjectURL(url); urls.delete(url); }
      if(!current() || generation !== page.request) return;
      page.retry.hidden = false;
      page.status.innerHTML = `${label('Page image could not be loaded. Retry before confirming the transcription.')}<br>${systemLabel(error.message)}`;
    } finally {
      if(current() && generation === page.request) {
        page.loading = false; translateMarked(page.status); syncConfirmation(page);
      }
    }
  };
  for(const page of pages) page.retry.addEventListener('click', event => {event.preventDefault(); void loadImage(page);});
  await Promise.allSettled(pages.map(loadImage));
}
