(function (global) {
  function toArray(list) {
    return Array.prototype.slice.call(list || []);
  }

  function parseInteger(value) {
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

  function setDeleteValue(card, deleted) {
    if (!card) {
      return;
    }

    const deleteInput = card.querySelector('input[name$="-DELETE"]');
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

  function updateCardPresentation(card, deleted) {
    if (!card) {
      return;
    }

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

  function focusFirstField(element) {
    if (!element) {
      return;
    }

    const field = element.querySelector("input:not([type='hidden']), textarea, select");
    if (field && typeof field.focus === 'function') {
      field.focus();
    }
  }

  function replacePrefix(markup, prefix, index) {
    if (typeof markup !== 'string') {
      return markup;
    }

    const pattern = new RegExp(`${prefix}-__prefix__`, 'g');
    return markup.replace(pattern, `${prefix}-${index}`);
  }

  function nextOrderValue(container) {
    if (!container) {
      return 0;
    }

    let max = -1;
    container.querySelectorAll('input[name$="-order"]').forEach((input) => {
      const value = parseInteger(input.value);
      if (value > max) {
        max = value;
      }
    });

    return max + 1;
  }

  function setOrderValue(card, value) {
    if (!card) {
      return;
    }

    const orderInput = card.querySelector('input[name$="-order"]');
    if (orderInput) {
      orderInput.value = String(value);
    }
  }

  function buildController(StimulusInstance) {
    if (!StimulusInstance || !StimulusInstance.Controller) {
      return null;
    }

    const { Controller } = StimulusInstance;

    class QcReferencesController extends Controller {
      static get targets() {
        return ['container', 'template', 'emptyMessage'];
      }

      connect() {
        this.formElement = this.element.closest('form');
        this.prefix = this.element.dataset.formsetPrefix || 'reference';
        this.totalFormsInput = this.findManagementInput('TOTAL_FORMS');
        this.applyInitialState();
        this.updateEmptyMessage();
      }

      findManagementInput(suffix) {
        if (!this.formElement) {
          return null;
        }

        return this.formElement.querySelector(`input[name="${this.prefix}-${suffix}"]`);
      }

      references() {
        if (!this.hasContainerTarget) {
          return [];
        }

        return toArray(this.containerTarget.querySelectorAll('[data-qc-reference]'));
      }

      applyInitialState() {
        this.references().forEach((card) => {
          const deleted = readDeleteValue(card);
          updateCardPresentation(card, deleted);
        });
      }

      updateEmptyMessage() {
        if (!this.hasEmptyMessageTarget) {
          return;
        }

        const hasActive = this.references().some((card) => !readDeleteValue(card));
        this.emptyMessageTarget.hidden = hasActive;
      }

      nextIndex() {
        if (this.totalFormsInput) {
          return parseInteger(this.totalFormsInput.value);
        }

        return this.references().length;
      }

      setTotalForms(value) {
        if (this.totalFormsInput) {
          this.totalFormsInput.value = String(value);
        }
      }

      addReference(event) {
        if (event && typeof event.preventDefault === 'function') {
          event.preventDefault();
        }

        if (!this.hasTemplateTarget || !this.hasContainerTarget) {
          return;
        }

        const index = this.nextIndex();
        const orderValue = nextOrderValue(this.containerTarget);
        const markup = replacePrefix(this.templateTarget.innerHTML, this.prefix, index);
        const wrapper = document.createElement('div');
        wrapper.innerHTML = markup.trim();
        const card = wrapper.firstElementChild;

        if (!card) {
          return;
        }

        setDeleteValue(card, false);
        updateCardPresentation(card, false);
        setOrderValue(card, orderValue);

        this.containerTarget.appendChild(card);
        this.setTotalForms(index + 1);
        this.updateEmptyMessage();
        focusFirstField(card);
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

        setDeleteValue(card, true);
        updateCardPresentation(card, true);
        this.updateEmptyMessage();
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

        setDeleteValue(card, false);
        updateCardPresentation(card, false);
        this.updateEmptyMessage();
      }
    }

    global.QcReferencesController = QcReferencesController;
    return QcReferencesController;
  }

  const controller = buildController(global && global.Stimulus);

  if (!controller && global && typeof global.addEventListener === 'function') {
    const tryAttach = () => {
      if (buildController(global && global.Stimulus)) {
        global.removeEventListener('DOMContentLoaded', tryAttach);
        global.removeEventListener('load', tryAttach);
      }
    };

    global.addEventListener('DOMContentLoaded', tryAttach);
    global.addEventListener('load', tryAttach);
  }
})(typeof window !== 'undefined' ? window : this);
