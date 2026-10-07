import {label, translateMarked} from './i18n.js';

// A dialog session is a UI identity, not an engineering or authorisation state.
// Call prepare before replacing content and opened after showModal/hydration.
export function createDialogController(dialog) {
  const document = dialog.ownerDocument;
  let session = 0, opener = null, baseline = null, pending = false;
  let rememberedFocus = null, closeGuard = null, pendingNotice = null, controlledCloses = 0;

  const captureSession = () => session;
  const isCurrent = value => value === session;
  const fingerprint = () => JSON.stringify([...dialog.querySelectorAll('form input, form textarea, form select')]
    .filter(el => !['submit', 'button', 'reset', 'hidden'].includes(el.type))
    .map(el => ({form:el.form?.getAttribute('id') || '', name:el.name || '', id:el.id || '', type:el.type || '',
      value:el.type === 'file' ? [...(el.files || [])].map(file => [file.name, file.size, file.lastModified]) : el.value,
      checked:['checkbox', 'radio'].includes(el.type) ? el.checked : undefined})));
  const dirty = () => baseline !== null && fingerprint() !== baseline;
  const removeGuard = () => { closeGuard?.remove(); closeGuard = null; };
  const removePendingNotice = () => { pendingNotice?.remove(); pendingNotice = null; };
  const focusForm = () => {
    const candidate = rememberedFocus?.isConnected && !rememberedFocus.disabled ? rememberedFocus :
      dialog.querySelector('form input:not([type="hidden"]):not(:disabled), form textarea:not(:disabled), form select:not(:disabled)');
    const fallback = dialog.querySelector('form') || dialog.querySelector('h2') || dialog;
    if(!candidate) fallback.setAttribute('tabindex', '-1');
    (candidate || fallback).focus({preventScroll:true});
  };
  const appendNotice = element => {
    const body = dialog.querySelector('.modal-body');
    (body || dialog).append(element);
    translateMarked(element);
  };
  const showPendingNotice = () => {
    if(pendingNotice) return;
    pendingNotice = document.createElement('div');
    pendingNotice.className = 'notice dialog-pending-notice';
    pendingNotice.setAttribute('role', 'status');
    pendingNotice.innerHTML = label('Saving is in progress. Please wait.');
    appendNotice(pendingNotice);
  };
  const restoreFocus = () => queueMicrotask(() => {
    if(dialog.open) return;
    if(opener?.isConnected && !opener.disabled) opener.focus({preventScroll:true});
    else {
      const heading = document.querySelector('#app main h1, #app h1');
      if(heading) { heading.setAttribute('tabindex', '-1'); heading.focus({preventScroll:true}); }
    }
    opener = null;
  });

  function prepare() {
    const active = document.activeElement;
    if(!dialog.open && active && !dialog.contains(active)) opener = active;
    session += 1;
    baseline = null; pending = false; rememberedFocus = null;
    removeGuard(); removePendingNotice();
    return session;
  }
  function opened() {
    const current = session;
    const heading = dialog.querySelector('h2');
    if(heading) {
      heading.id ||= `strata-dialog-title-${current}`;
      heading.setAttribute('tabindex', '-1');
      dialog.setAttribute('aria-labelledby', heading.id);
    }
    queueMicrotask(() => {
      if(!isCurrent(current) || !dialog.open) return;
      // Editors add their visual controls synchronously after openModal.
      baseline = fingerprint();
      focusForm();
    });
  }
  function requestClose({force=false}={}) {
    if(!force && pending) { showPendingNotice(); focusForm(); return false; }
    if(!force && dialog.open && dirty()) {
      if(!closeGuard) {
        closeGuard = document.createElement('div');
        closeGuard.className = 'notice warning dialog-close-guard';
        closeGuard.setAttribute('role', 'alert');
        closeGuard.innerHTML = `<div><p>${label('You have unsaved changes.')}</p><div class="row-actions"><button type="button" class="button small" data-dialog-choice="keep">${label('Keep editing')}</button><button type="button" class="button small danger" data-dialog-choice="discard">${label('Discard changes')}</button></div></div>`;
        appendNotice(closeGuard);
      }
      closeGuard.querySelector('[data-dialog-choice="keep"]')?.focus({preventScroll:true});
      return false;
    }
    session += 1; // Immediately invalidates in-flight UI work, even before close fires.
    baseline = null; pending = false;
    removeGuard(); removePendingNotice();
    if(dialog.open) { controlledCloses += 1; dialog.close(); restoreFocus(); }
    return true;
  }
  function setPending(value) {
    pending = Boolean(value);
    if(pending) { removeGuard(); if(dialog.open) showPendingNotice(); }
    else removePendingNotice();
  }
  dialog.addEventListener('cancel', event => { event.preventDefault(); requestClose(); });
  dialog.addEventListener('click', event => {
    const choice = event.target.closest?.('[data-dialog-choice]');
    if(choice && dialog.contains(choice)) {
      event.preventDefault();
      if(choice.dataset.dialogChoice === 'discard') requestClose({force:true});
      else { removeGuard(); focusForm(); }
      return;
    }
    if(event.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if(event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) requestClose();
    }
  });
  dialog.addEventListener('focusin', event => {
    if(event.target.closest?.('form') && !closeGuard?.contains(event.target) && !pendingNotice?.contains(event.target)) rememberedFocus = event.target;
  });
  dialog.addEventListener('close', () => {
    // Controlled closes already invalidated the session and queued focus return.
    if(controlledCloses) { controlledCloses -= 1; return; }
    // A queued close event from replaced content must not touch a newer dialog.
    if(dialog.open) return;
    session += 1; baseline = null; pending = false;
    removeGuard(); removePendingNotice(); restoreFocus();
  });
  return {prepare, opened, requestClose, setPending, captureSession, isCurrent};
}
