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
      this.containerTarget.appendChild(newElement);
      this._setTotalForms(index + 1);
      this.refreshEmptyState();
      this._focusFirstField(newElement);
    }

    refreshEmptyState() {
      if (!this.hasEmptyMessageTarget) {
        return;
      }
      var hasReferences =
        this.hasContainerTarget &&
        this.containerTarget.querySelector("[data-qc-reference]");
      this.emptyMessageTarget.hidden = Boolean(hasReferences);
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
  };

  return QcReferencesController;
});
