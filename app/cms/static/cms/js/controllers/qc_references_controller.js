(function (global, factory) {
  if (typeof module === "object" && typeof module.exports === "object") {
    module.exports = factory(require("@hotwired/stimulus"));
  } else {
    var controllerClass = factory(global.Stimulus || null);
    if (controllerClass) {
      global.QcReferencesController = controllerClass;
      global.QCReferencesController = controllerClass;
    }
  }
})(typeof window !== "undefined" ? window : this, function (Stimulus) {
  if (!Stimulus || !Stimulus.Controller) {
    return null;
  }

  var Controller = Stimulus.Controller;

  function parseInteger(value) {
    var number = parseInt(value, 10);
    return isNaN(number) ? 0 : number;
  }

  function replacePrefixTokens(html, prefix, index) {
    if (typeof html !== "string") {
      return "";
    }
    var pattern = new RegExp(prefix + "-__prefix__", "g");
    return html.replace(pattern, prefix + "-" + index);
  }

  var QcReferencesController = class extends Controller {
    static get targets() {
      return ["container", "template", "emptyMessage"];
    }

    connect() {
      this.formElement = this.element.closest("form");
      this.prefix = this.element.dataset.formsetPrefix || "reference";
      this.totalFormsInput = this._findManagementInput("TOTAL_FORMS");
      this._applyInitialDeletedState();
      this.refreshEmptyState();
    }

    addReference(event) {
      if (event) {
        event.preventDefault();
      }
      if (!this.hasTemplateTarget || !this.hasContainerTarget) {
        return;
      }
      var index = this._nextIndex();
      var newElement = this._createReferenceElement(index);
      if (!newElement) {
        return;
      }
      var orderValue = this._nextOrder();
      this._setOrderValue(newElement, orderValue);
      this._ensureRefId(newElement, index);
      this._setDeleteValue(newElement, "");
      this._toggleReferenceVisibility(newElement, false);
      this.containerTarget.appendChild(newElement);
      this._setTotalForms(index + 1);
      this.refreshEmptyState();
      this._focusFirstField(newElement);
    }

    deleteReference(event) {
      if (event) {
        event.preventDefault();
      }
      var card = this._findReferenceCard(event);
      if (!card) {
        return;
      }
      this._markDeleteField(card, true);
      this._toggleReferenceVisibility(card, true);
      this.refreshEmptyState();
    }

    restoreReference(event) {
      if (event) {
        event.preventDefault();
      }
      var card = this._findReferenceCard(event);
      if (!card) {
        return;
      }
      this._markDeleteField(card, false);
      this._toggleReferenceVisibility(card, false);
      this.refreshEmptyState();
    }

    refreshEmptyState() {
      if (!this.hasEmptyMessageTarget) {
        return;
      }
      var visible = this._visibleReferences();
      this.emptyMessageTarget.hidden = visible.length > 0;
    }

    _findManagementInput(suffix) {
      if (!this.formElement) {
        return null;
      }
      return this.formElement.querySelector(
        'input[name="' + this.prefix + "-" + suffix + '"]'
      );
    }

    _nextIndex() {
      if (!this.totalFormsInput) {
        return this._countReferences();
      }
      return parseInteger(this.totalFormsInput.value);
    }

    _nextOrder() {
      if (!this.hasContainerTarget) {
        return this._nextIndex();
      }
      var maxOrder = -1;
      this.containerTarget
        .querySelectorAll('input[name$="-order"]')
        .forEach(function (input) {
          var value = parseInteger(input.value);
          if (value > maxOrder) {
            maxOrder = value;
          }
        });
      return maxOrder + 1;
    }

    _createReferenceElement(index) {
      var templateHtml = this.templateTarget.innerHTML;
      if (!templateHtml) {
        return null;
      }
      var markup = replacePrefixTokens(templateHtml, this.prefix, index);
      var wrapper = document.createElement("div");
      wrapper.innerHTML = markup.trim();
      return wrapper.firstElementChild;
    }

    _setOrderValue(element, value) {
      if (!element) {
        return;
      }
      var orderInput = element.querySelector('input[name$="-order"]');
      if (orderInput) {
        orderInput.value = String(value);
      }
    }

    _ensureRefId(element, index) {
      if (!element) {
        return;
      }
      var refInput = element.querySelector('input[name$="-ref_id"]');
      if (!refInput) {
        return;
      }
      var current = (refInput.value || "").trim();
      if (!current) {
        refInput.value = "new-ref-" + Date.now() + "-" + index;
      }
    }

    _setDeleteValue(element, value) {
      if (!element) {
        return;
      }
      var deleteInput = element.querySelector('input[name$="-DELETE"]');
      if (deleteInput) {
        deleteInput.value = value || "";
      }
    }

    _setTotalForms(value) {
      if (this.totalFormsInput) {
        this.totalFormsInput.value = String(value);
      }
    }

    _countReferences() {
      if (!this.hasContainerTarget) {
        return 0;
      }
      return this.containerTarget.querySelectorAll("[data-qc-reference]").length;
    }

    _focusFirstField(element) {
      if (!element) {
        return;
      }
      var field = element.querySelector("input, textarea, select");
      if (field && typeof field.focus === "function") {
        field.focus();
      }
    }

    _findReferenceCard(source) {
      if (!source) {
        return null;
      }
      var element = source.target || source;
      if (!element.closest) {
        return null;
      }
      return element.closest("[data-qc-reference]");
    }

    _markDeleteField(card, deleted) {
      if (!card) {
        return;
      }
      var deleteInput = card.querySelector('input[name$="-DELETE"]');
      if (!deleteInput) {
        return;
      }
      deleteInput.value = deleted ? "on" : "";
    }

    _toggleReferenceVisibility(card, deleted) {
      if (!card) {
        return;
      }
      var body = card.querySelector("[data-reference-body]");
      var deletedMessage = card.querySelector("[data-reference-deleted-message]");
      var actions = card.querySelector("[data-reference-actions]");
      if (deleted) {
        if (body) {
          body.hidden = true;
        }
        if (deletedMessage) {
          deletedMessage.hidden = false;
        }
        if (actions) {
          actions.hidden = true;
        }
        card.dataset.deleted = "true";
        card.dataset.referenceDeleted = "true";
      } else {
        if (body) {
          body.hidden = false;
        }
        if (deletedMessage) {
          deletedMessage.hidden = true;
        }
        if (actions) {
          actions.hidden = false;
        }
        if (card.dataset) {
          delete card.dataset.deleted;
          delete card.dataset.referenceDeleted;
        }
      }
      this._setFieldDisabledState(card, deleted);
    }

    _setFieldDisabledState(card, disabled) {
      if (!card) {
        return;
      }
      card
        .querySelectorAll("input, textarea, select")
        .forEach(function (field) {
          if (!field.name) {
            return;
          }
          if (field.name.match(/-DELETE$/)) {
            field.disabled = false;
            return;
          }
          if (field.type === "hidden") {
            return;
          }
          field.disabled = disabled;
        });
    }

    _visibleReferences() {
      if (!this.hasContainerTarget) {
        return [];
      }
      var controller = this;
      return Array.prototype.filter.call(
        this.containerTarget.querySelectorAll("[data-qc-reference]"),
        function (element) {
          return !controller._isMarkedForDeletion(element);
        }
      );
    }

    _isMarkedForDeletion(element) {
      if (!element) {
        return false;
      }
      if (element.dataset) {
        if (element.dataset.deleted === "true") {
          return true;
        }
        if (element.dataset.referenceDeleted === "true") {
          return true;
        }
      }
      var deleteInput = element.querySelector('input[name$="-DELETE"]');
      if (!deleteInput) {
        return false;
      }
      var value = (deleteInput.value || "").toLowerCase();
      return value === "on" || value === "true" || value === "1";
    }

    _applyInitialDeletedState() {
      if (!this.hasContainerTarget) {
        return;
      }
      var controller = this;
      this.containerTarget
        .querySelectorAll("[data-qc-reference]")
        .forEach(function (element) {
          if (controller._isMarkedForDeletion(element)) {
            controller._toggleReferenceVisibility(element, true);
          } else {
            controller._toggleReferenceVisibility(element, false);
          }
        });
    }
  };

  return QcReferencesController;
});
