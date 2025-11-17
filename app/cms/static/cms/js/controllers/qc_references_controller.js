(function (global) {
  const Stimulus = global && global.Stimulus;

  if (!Stimulus || !Stimulus.Controller) {
    console.error('Stimulus Controller not found for QcReferencesController');
    return;
  }

  const { Controller } = Stimulus;

  function toArray(list) {
    return Array.prototype.slice.call(list || []);
  }

  function parseIndex(value) {
    const number = parseInt(value, 10);
    return Number.isNaN(number) ? 0 : number;
  }

  function readDeleteValue(card) {
    if (!card) {
      return false;
    }

    const deleteInput = card.querySelector('input[name$="-DELETE"]');
    if (!deleteInput) {
      return false;
    }

    if (deleteInput.type === 'checkbox') {
      return Boolean(deleteInput.checked);
    }

    const value = (deleteInput.value || '').toLowerCase();
    return value === 'on' || value === 'true' || value === '1';
  }

  function extractIndexFromCard(card, prefix) {
    if (!card || !prefix) {
      return null;
    }

    const indexedField = card.querySelector(`[name^="${prefix}-"]`);

    if (!indexedField || !indexedField.name) {
      return null;
    }

    const match = indexedField.name.match(new RegExp(`^${prefix}-(\\d+)-`));
    if (!match) {
      return null;
    }

    return match[1];
  }

  function ensureDeleteInput(card, prefix) {
    if (!card) {
      return null;
    }

    const existing = card.querySelector('input[name$="-DELETE"]');
    if (existing) {
      return existing;
    }

    const formIndex = extractIndexFromCard(card, prefix);
    if (formIndex === null) {
      return null;
    }

    const deleteInput = document.createElement('input');
    deleteInput.type = 'hidden';
    deleteInput.name = `${prefix}-${formIndex}-DELETE`;
    deleteInput.value = '';
    card.prepend(deleteInput);
    return deleteInput;
  }

  function setDeleteValue(card, deleted, prefix) {
    if (!card) {
      return;
    }

    const deleteInput = ensureDeleteInput(card, prefix);
    if (!deleteInput) {
      return;
    }

    if (deleteInput.type === 'checkbox') {
      deleteInput.checked = Boolean(deleted);
      deleteInput.value = deleted ? deleteInput.value || 'on' : '';
    } else {
      deleteInput.value = deleted ? 'on' : '';
    }
  }

  function toggleCardPresentation(card, deleted) {
    if (!card) {
      return;
    }

    card.toggleAttribute('data-reference-deleted', Boolean(deleted));

    const actions = card.querySelector('[data-reference-actions]');
    if (actions) {
      actions.hidden = Boolean(deleted);
    }

    const body = card.querySelector('[data-reference-body]');
    if (body) {
      body.hidden = Boolean(deleted);
    }

    const deletedMessage = card.querySelector('[data-reference-deleted-message]');
    if (deletedMessage) {
      deletedMessage.hidden = !deleted;
    }
  }

  function replacePrefix(markup, prefix, index) {
    if (typeof markup !== 'string') {
      return markup;
    }

    const pattern = new RegExp(`${prefix}-__prefix__`, 'g');
    return markup.replace(pattern, `${prefix}-${index}`);
  }

  class QcReferencesController extends Controller {
    static get targets() {
      return ['container', 'template', 'emptyMessage'];
    }

    connect() {
      this.prefix = this.element.getAttribute('data-formset-prefix') || 'reference';
      this.formElement = this.element.closest('form');
      this.totalFormsInput = this._findManagementInput('TOTAL_FORMS');
      this._applyInitialState();
      this._updateEmptyMessage();
    }

    addReference(event) {
      if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }

      if (!this.hasTemplateTarget || !this.hasContainerTarget) {
        return;
      }

      const nextIndex = this._nextIndex();
      const markup = replacePrefix(this.templateTarget.innerHTML, this.prefix, nextIndex);
      const wrapper = document.createElement('div');
      wrapper.innerHTML = (markup || '').trim();
      const card = wrapper.firstElementChild;

      if (!card) {
        return;
      }

      setDeleteValue(card, false, this.prefix);
      toggleCardPresentation(card, false);

      this.containerTarget.appendChild(card);
      this._setTotalForms(nextIndex + 1);
      this._updateEmptyMessage();

      const focusTarget = card.querySelector("input:not([type='hidden']), textarea, select");
      if (focusTarget && typeof focusTarget.focus === 'function') {
        focusTarget.focus();
      }
    }

    deleteReference(event) {
      if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }

      const trigger = event ? event.currentTarget || event.target : null;
      const card = trigger && typeof trigger.closest === 'function'
        ? trigger.closest('[data-qc-reference]')
        : null;

      if (!card) {
        return;
      }

      setDeleteValue(card, true, this.prefix);
      toggleCardPresentation(card, true);
      this._updateEmptyMessage();
    }

    restoreReference(event) {
      if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }

      const trigger = event ? event.currentTarget || event.target : null;
      const card = trigger && typeof trigger.closest === 'function'
        ? trigger.closest('[data-qc-reference]')
        : null;

      if (!card) {
        return;
      }

      setDeleteValue(card, false, this.prefix);
      toggleCardPresentation(card, false);
      this._updateEmptyMessage();
    }

    _applyInitialState() {
      this._cards().forEach((card) => {
        ensureDeleteInput(card, this.prefix);
        const deleted = readDeleteValue(card);
        toggleCardPresentation(card, deleted);
      });
    }

    _updateEmptyMessage() {
      if (!this.hasEmptyMessageTarget) {
        return;
      }

      const hasActive = this._cards().some((card) => !readDeleteValue(card));
      this.emptyMessageTarget.hidden = hasActive;
    }

    _cards() {
      if (!this.hasContainerTarget) {
        return [];
      }

      return toArray(this.containerTarget.querySelectorAll('[data-qc-reference]'));
    }

    _nextIndex() {
      if (this.totalFormsInput) {
        return parseIndex(this.totalFormsInput.value);
      }

      return this._cards().length;
    }

    _setTotalForms(value) {
      if (this.totalFormsInput) {
        this.totalFormsInput.value = String(value);
      }
    }

    _findManagementInput(suffix) {
      if (!this.formElement) {
        return null;
      }

      return this.formElement.querySelector(`input[name="${this.prefix}-${suffix}"]`);
    }
  }

  global.QcReferencesController = QcReferencesController;

  function tryAutoRegister() {
    if (!global.Stimulus || !global.Stimulus.Application) {
      return;
    }

    let app = global.StimulusApp;
    if (!app && typeof global.Stimulus.Application.start === 'function') {
      app = global.Stimulus.Application.start();
      global.StimulusApp = app;
    }

    if (!app || typeof app.register !== 'function') {
      return;
    }

    try {
      app.register('qc-references', QcReferencesController);
    } catch (error) {
      const message = String(error || '');
      if (message.indexOf('already been registered') === -1) {
        console.error(error);
      }
    }
  }

  tryAutoRegister();
})(typeof window !== 'undefined' ? window : this);
