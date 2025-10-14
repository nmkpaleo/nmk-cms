(function (global, factory) {
  if (typeof module === "object" && typeof module.exports === "object") {
    module.exports = factory(global, require("@hotwired/stimulus"));
  } else {
    factory(global, global.Stimulus);
  }
})(typeof window !== "undefined" ? window : this, function (global, Stimulus) {
  function parseInteger(value) {
    var number = parseInt(value, 10);
    return isNaN(number) ? 0 : number;
  }

  function toArray(list) {
    return Array.prototype.slice.call(list || []);
  }

  function readDeleteValue(card) {
    if (!card) {
      return false;
    }

    if (card.dataset) {
      if (card.dataset.referenceDeleted === "true" || card.dataset.deleted === "true") {
        return true;
      }
    }

    var deleteInput = card.querySelector('input[name$="-DELETE"]');
    if (!deleteInput) {
      return false;
    }

    if (deleteInput.type === "checkbox") {
      return Boolean(deleteInput.checked);
    }

    var value = (deleteInput.value || "").toLowerCase();
    return value === "on" || value === "true" || value === "1";
  }

  function setDeleteValue(card, deleted) {
    if (!card) {
      return;
    }

    var deleteInput = card.querySelector('input[name$="-DELETE"]');
    if (!deleteInput) {
      return;
    }

    if (deleteInput.type === "checkbox") {
      deleteInput.checked = Boolean(deleted);
      if (!deleted) {
        deleteInput.value = "";
      } else if (!deleteInput.value) {
        deleteInput.value = "on";
      }
    } else {
      deleteInput.value = deleted ? "on" : "";
    }
  }

  function updateCardPresentation(card, deleted) {
    if (!card) {
      return;
    }

    var body = card.querySelector("[data-reference-body]");
    if (body) {
      body.hidden = Boolean(deleted);
    }

    var actions = card.querySelector("[data-reference-actions]");
    if (actions) {
      actions.hidden = Boolean(deleted);
    }

    var deletedMessage = card.querySelector("[data-reference-deleted-message]");
    if (deletedMessage) {
      deletedMessage.hidden = !deleted;
    }

    if (card.dataset) {
      if (deleted) {
        card.dataset.referenceDeleted = "true";
      } else {
        delete card.dataset.referenceDeleted;
        delete card.dataset.deleted;
      }
    }
  }

  function focusFirstField(element) {
    if (!element) {
      return;
    }

    var field = element.querySelector("input:not([type='hidden']), textarea, select");
    if (field && typeof field.focus === "function") {
      field.focus();
    }
  }

  function replacePrefix(markup, prefix, index) {
    if (typeof markup !== "string") {
      return markup;
    }

    var pattern = new RegExp(prefix + "-__prefix__", "g");
    return markup.replace(pattern, prefix + "-" + index);
  }

  function nextOrderValue(container) {
    if (!container) {
      return 0;
    }

    var max = -1;
    container.querySelectorAll('input[name$="-order"]').forEach(function (input) {
      var value = parseInteger(input.value);
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

    var orderInput = card.querySelector('input[name$="-order"]');
    if (orderInput) {
      orderInput.value = String(value);
    }
  }

  function attachController(StimulusInstance) {
    if (!StimulusInstance || !StimulusInstance.Controller) {
      return null;
    }

    var Controller = StimulusInstance.Controller;

    class QcReferencesController extends Controller {
      static get targets() {
        return ["container", "template", "emptyMessage"];
      }

      connect() {
        this.formElement = this.element.closest("form");
        this.prefix = this.element.dataset ? this.element.dataset.formsetPrefix || "reference" : "reference";
        this.totalFormsInput = this.findManagementInput("TOTAL_FORMS");
        this.applyInitialState();
        this.updateEmptyMessage();
      }

      findManagementInput(suffix) {
        if (!this.formElement) {
          return null;
        }

        return this.formElement.querySelector('input[name="' + this.prefix + "-" + suffix + '"]');
      }

      references() {
        if (!this.hasContainerTarget) {
          return [];
        }

        return toArray(this.containerTarget.querySelectorAll("[data-qc-reference]"));
      }

      applyInitialState() {
        var cards = this.references();
        cards.forEach(function (card) {
          var deleted = readDeleteValue(card);
          updateCardPresentation(card, deleted);
        });
      }

      updateEmptyMessage() {
        if (!this.hasEmptyMessageTarget) {
          return;
        }

        var hasActive = this.references().some(function (card) {
          return !readDeleteValue(card);
        });

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
        if (event && typeof event.preventDefault === "function") {
          event.preventDefault();
        }

        if (!this.hasTemplateTarget || !this.hasContainerTarget) {
          return;
        }

        var index = this.nextIndex();
        var orderValue = nextOrderValue(this.containerTarget);
        var markup = replacePrefix(this.templateTarget.innerHTML, this.prefix, index);
        var wrapper = document.createElement("div");
        wrapper.innerHTML = markup.trim();
        var card = wrapper.firstElementChild;
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
        if (event && typeof event.preventDefault === "function") {
          event.preventDefault();
        }

        var target = event && event.target ? event.target : null;
        var card = target && target.closest ? target.closest("[data-qc-reference]") : null;
        if (!card) {
          return;
        }

        setDeleteValue(card, true);
        updateCardPresentation(card, true);
        this.updateEmptyMessage();
      }

      restoreReference(event) {
        if (event && typeof event.preventDefault === "function") {
          event.preventDefault();
        }

        var target = event && event.target ? event.target : null;
        var card = target && target.closest ? target.closest("[data-qc-reference]") : null;
        if (!card) {
          return;
        }

        setDeleteValue(card, false);
        updateCardPresentation(card, false);
        this.updateEmptyMessage();
      }
    }

    global.QcReferencesController = QcReferencesController;
    global.QCReferencesController = QcReferencesController;
    return QcReferencesController;
  }

  var controller = attachController(Stimulus);

  if (!controller && global && typeof global.addEventListener === "function") {
    var tryAttach = function () {
      if (attachController(global.Stimulus)) {
        global.removeEventListener("DOMContentLoaded", tryAttach);
        global.removeEventListener("load", tryAttach);
      }
    };

    global.addEventListener("DOMContentLoaded", tryAttach);
    global.addEventListener("load", tryAttach);
  }

  return controller;
});
