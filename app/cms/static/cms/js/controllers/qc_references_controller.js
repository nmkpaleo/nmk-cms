(function (global, factory) {
  if (typeof module === "object" && typeof module.exports === "object") {
    module.exports = factory(require("@hotwired/stimulus"));
  } else {
    var controllerInstance = null;
    var controllerRegistered = false;

    function registerController() {
      if (controllerRegistered) {
        return true;
      }

      var Stimulus = global.Stimulus;
      if (!Stimulus || !Stimulus.Controller) {
        return false;
      }

      if (!controllerInstance) {
        controllerInstance = factory(Stimulus);
      }

      if (!controllerInstance) {
        controllerRegistered = true;
        return true;
      }

      var application = global.StimulusApp;
      if (!application && Stimulus.Application && typeof Stimulus.Application.start === "function") {
        application = Stimulus.Application.start();
        global.StimulusApp = application;
      }

      if (application && typeof application.register === "function") {
        application.register("qc-references", controllerInstance);
      }

      global.QcReferencesController = controllerInstance;
      global.QCReferencesController = controllerInstance;
      controllerRegistered = true;
      return true;
    }

    if (!registerController()) {
      var onReady = function () {
        if (registerController() && global.removeEventListener) {
          global.removeEventListener("load", onReady);
          global.removeEventListener("DOMContentLoaded", onReady);
        }
      };

      if (global.addEventListener) {
        global.addEventListener("DOMContentLoaded", onReady);
        global.addEventListener("load", onReady);
      }

      var retries = 0;
      var intervalId = setInterval(function () {
        if (registerController() || retries > 200) {
          clearInterval(intervalId);
        }
        retries += 1;
      }, 50);
    }
  }
})(typeof window !== "undefined" ? window : this, function (Stimulus) {
  if (!Stimulus || !Stimulus.Controller) {
    return null;
  }

  var Controller = Stimulus.Controller;
  var root =
    typeof window !== "undefined"
      ? window
      : typeof globalThis !== "undefined"
      ? globalThis
      : this;

  function parseInteger(value) {
    var number = parseInt(value, 10);
    return isNaN(number) ? 0 : number;
  }

  function findManagementInput(formElement, prefix, suffix) {
    if (!formElement) {
      return null;
    }
    return formElement.querySelector('input[name="' + prefix + "-" + suffix + '"]');
  }

  function referenceCards(container) {
    if (!container) {
      return [];
    }
    return Array.prototype.slice.call(container.querySelectorAll("[data-qc-reference]"));
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
    var finalValue = deleted ? "on" : "";
    deleteInput.value = finalValue;
    if (deleteInput.type === "checkbox") {
      deleteInput.checked = deleted;
    }
  }

  function setFieldsDisabled(card, disabled) {
    if (!card) {
      return;
    }
    card.querySelectorAll("input, textarea, select").forEach(function (field) {
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
      field.disabled = Boolean(disabled);
    });
  }

  function updateCardVisibility(card, deleted) {
    if (!card) {
      return;
    }
    var body = card.querySelector("[data-reference-body]");
    var deletedMessage = card.querySelector("[data-reference-deleted-message]");
    var actions = card.querySelector("[data-reference-actions]");

    if (body) {
      body.hidden = Boolean(deleted);
    }
    if (deletedMessage) {
      deletedMessage.hidden = !deleted;
    }
    if (actions) {
      actions.hidden = Boolean(deleted);
    }

    if (card.dataset) {
      if (deleted) {
        card.dataset.referenceDeleted = "true";
      } else {
        delete card.dataset.referenceDeleted;
        delete card.dataset.deleted;
      }
    }

    setFieldsDisabled(card, deleted);
  }

  function focusFirstField(element) {
    if (!element) {
      return;
    }
    var field = element.querySelector("input, textarea, select");
    if (field && typeof field.focus === "function") {
      field.focus();
    }
  }

  function createReferenceElement(templateElement, prefix, index) {
    if (!templateElement || typeof document === "undefined") {
      return null;
    }
    var templateHtml = templateElement.innerHTML;
    if (!templateHtml) {
      return null;
    }
    var markup = templateHtml.replace(new RegExp(prefix + "-__prefix__", "g"), prefix + "-" + index);
    var wrapper = document.createElement("div");
    wrapper.innerHTML = markup.trim();
    return wrapper.firstElementChild;
  }

  function ensureReferenceId(element, index) {
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

  function setOrderValue(element, value) {
    if (!element) {
      return;
    }
    var orderInput = element.querySelector('input[name$="-order"]');
    if (orderInput) {
      orderInput.value = String(value);
    }
  }

  function buildContext(source) {
    if (!source) {
      return null;
    }
    var element = source.element || source;
    if (!element || !element.querySelector) {
      return null;
    }
    var formElement = source.formElement || element.closest("form");
    var prefix = source.prefix || (element.dataset ? element.dataset.formsetPrefix : null) || "reference";
    var container = source.containerTarget || element.querySelector('[data-qc-references-target="container"]');
    var template = source.templateTarget || element.querySelector('template[data-qc-references-target="template"]');
    var emptyMessage = source.emptyMessageTarget || element.querySelector('[data-qc-references-target="emptyMessage"]');
    var totalFormsInput = source.totalFormsInput || findManagementInput(formElement, prefix, "TOTAL_FORMS");

    return {
      element: element,
      formElement: formElement,
      prefix: prefix,
      container: container,
      template: template,
      emptyMessage: emptyMessage,
      totalFormsInput: totalFormsInput,
    };
  }

  function applyInitialState(ctx) {
    if (!ctx || !ctx.container) {
      return;
    }
    referenceCards(ctx.container).forEach(function (card) {
      var deleted = readDeleteValue(card);
      updateCardVisibility(card, deleted);
    });
  }

  function visibleReferences(ctx) {
    if (!ctx || !ctx.container) {
      return [];
    }
    return referenceCards(ctx.container).filter(function (card) {
      return !readDeleteValue(card);
    });
  }

  function refreshEmptyState(ctx) {
    if (!ctx || !ctx.emptyMessage) {
      return;
    }
    ctx.emptyMessage.hidden = visibleReferences(ctx).length > 0;
  }

  function ensureTotalForms(ctx) {
    if (!ctx || ctx.totalFormsInput) {
      return;
    }
    if (!ctx.formElement) {
      return;
    }
    ctx.totalFormsInput = findManagementInput(ctx.formElement, ctx.prefix, "TOTAL_FORMS");
  }

  function setTotalForms(ctx, value) {
    if (!ctx) {
      return;
    }
    ensureTotalForms(ctx);
    if (ctx.totalFormsInput) {
      ctx.totalFormsInput.value = String(value);
    }
  }

  function nextIndex(ctx) {
    if (!ctx) {
      return 0;
    }
    ensureTotalForms(ctx);
    if (ctx.totalFormsInput) {
      return parseInteger(ctx.totalFormsInput.value);
    }
    return referenceCards(ctx.container).length;
  }

  function nextOrder(ctx) {
    if (!ctx || !ctx.container) {
      return nextIndex(ctx);
    }
    var maxOrder = -1;
    ctx.container.querySelectorAll('input[name$="-order"]').forEach(function (input) {
      var value = parseInteger(input.value);
      if (value > maxOrder) {
        maxOrder = value;
      }
    });
    return maxOrder + 1;
  }

  function addReference(ctx) {
    if (!ctx || !ctx.container) {
      return null;
    }
    var index = nextIndex(ctx);
    var element = createReferenceElement(ctx.template, ctx.prefix, index);
    if (!element) {
      return null;
    }
    setOrderValue(element, nextOrder(ctx));
    ensureReferenceId(element, index);
    setDeleteValue(element, false);
    updateCardVisibility(element, false);
    ctx.container.appendChild(element);
    setTotalForms(ctx, index + 1);
    refreshEmptyState(ctx);
    return element;
  }

  function findReferenceCard(source) {
    if (!source) {
      return null;
    }
    var element = source.target || source;
    if (!element.closest) {
      return null;
    }
    return element.closest("[data-qc-reference]");
  }

  function sectionFromSource(source) {
    if (!source || !source.closest) {
      return null;
    }
    return source.closest('[data-controller~="qc-references"]');
  }

  function toggleCardState(ctx, card, deleted) {
    if (!ctx || !card) {
      return;
    }
    setDeleteValue(card, deleted);
    updateCardVisibility(card, deleted);
    refreshEmptyState(ctx);
  }

  function initializeFallback() {
    if (typeof document === "undefined") {
      return;
    }

    function prepareSections() {
      if (root.Stimulus && root.Stimulus.Controller) {
        return;
      }
      var sections = document.querySelectorAll('[data-controller~="qc-references"]');
      sections.forEach(function (section) {
        if (section.dataset && section.dataset.qcReferencesFallback === "true") {
          return;
        }
        var ctx = buildContext({ element: section });
        applyInitialState(ctx);
        refreshEmptyState(ctx);
        if (section.dataset) {
          section.dataset.qcReferencesFallback = "true";
        }
      });
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", prepareSections);
    } else {
      prepareSections();
    }

    document.addEventListener("click", function (event) {
      if (event.defaultPrevented) {
        return;
      }
      if (root.Stimulus && root.Stimulus.Controller) {
        return;
      }
      var target = event.target;
      if (!target || !target.closest) {
        return;
      }
      var addTrigger = target.closest("[data-reference-add]");
      if (addTrigger) {
        event.preventDefault();
        var addSection = sectionFromSource(addTrigger);
        if (!addSection) {
          return;
        }
        var addCtx = buildContext({ element: addSection });
        var newElement = addReference(addCtx);
        if (newElement) {
          focusFirstField(newElement);
        }
        return;
      }
      var deleteTrigger = target.closest("[data-reference-delete]");
      if (deleteTrigger) {
        event.preventDefault();
        var deleteSection = sectionFromSource(deleteTrigger);
        if (!deleteSection) {
          return;
        }
        var deleteCtx = buildContext({ element: deleteSection });
        var deleteCard = findReferenceCard(deleteTrigger);
        toggleCardState(deleteCtx, deleteCard, true);
        return;
      }
      var restoreTrigger = target.closest("[data-reference-restore]");
      if (restoreTrigger) {
        event.preventDefault();
        var restoreSection = sectionFromSource(restoreTrigger);
        if (!restoreSection) {
          return;
        }
        var restoreCtx = buildContext({ element: restoreSection });
        var restoreCard = findReferenceCard(restoreTrigger);
        toggleCardState(restoreCtx, restoreCard, false);
      }
    });
  }

  initializeFallback();

  class QcReferencesController extends Controller {
    static get targets() {
      return ["container", "template", "emptyMessage"];
    }

    connect() {
      this.ctx = buildContext(this);
      if (!this.ctx) {
        return;
      }
      applyInitialState(this.ctx);
      refreshEmptyState(this.ctx);
    }

    addReference(event) {
      if (event) {
        event.preventDefault();
      }
      if (!this.ctx) {
        this.ctx = buildContext(this);
      }
      if (!this.ctx) {
        return;
      }
      var newElement = addReference(this.ctx);
      if (newElement) {
        focusFirstField(newElement);
      }
    }

    deleteReference(event) {
      if (event) {
        event.preventDefault();
      }
      if (!this.ctx) {
        this.ctx = buildContext(this);
      }
      if (!this.ctx) {
        return;
      }
      var card = findReferenceCard(event);
      toggleCardState(this.ctx, card, true);
    }

    restoreReference(event) {
      if (event) {
        event.preventDefault();
      }
      if (!this.ctx) {
        this.ctx = buildContext(this);
      }
      if (!this.ctx) {
        return;
      }
      var card = findReferenceCard(event);
      toggleCardState(this.ctx, card, false);
    }
  }

  return QcReferencesController;
});
