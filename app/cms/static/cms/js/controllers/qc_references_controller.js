(function (global, factory) {
  if (typeof module === "object" && typeof module.exports === "object") {
    module.exports = factory(require("@hotwired/stimulus"));
  } else {
    factory(global.Stimulus || null);

    var controllerRegistered = false;

    function registerController() {
      if (controllerRegistered) {
        return true;
      }

      var Stimulus = global.Stimulus;
      if (!Stimulus || !Stimulus.Controller) {
        return false;
      }

      var controllerClass = factory(Stimulus);
      if (!controllerClass) {
        controllerRegistered = true;
        return true;
      }

      var application = global.StimulusApp;
      if (!application && Stimulus.Application && typeof Stimulus.Application.start === "function") {
        application = Stimulus.Application.start();
        global.StimulusApp = application;
      }

      if (application && typeof application.register === "function") {
        application.register("qc-references", controllerClass);
      }

      global.QcReferencesController = controllerClass;
      global.QCReferencesController = controllerClass;
      controllerRegistered = true;
      return true;
    }

    if (!registerController()) {
      var onReady = function () {
        if (registerController()) {
          if (global.removeEventListener) {
            global.removeEventListener("load", onReady);
            global.removeEventListener("DOMContentLoaded", onReady);
          }
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
  var root = typeof window !== "undefined" ? window : typeof globalThis !== "undefined" ? globalThis : this;
  if (!root.__qcReferencesState) {
    root.__qcReferencesState = {
      fallbackInitialized: false,
      controllerClass: null,
      helpers: null,
    };
  }
  var state = root.__qcReferencesState;

  if (!state.helpers) {
    state.helpers = buildHelpers();
  }

  if (!state.fallbackInitialized) {
    initializeFallback(root, state.helpers);
    state.fallbackInitialized = true;
  }

  if (!Stimulus || !Stimulus.Controller) {
    return state.controllerClass;
  }

  if (!state.controllerClass) {
    state.controllerClass = createStimulusController(Stimulus.Controller, state.helpers);
  }

  return state.controllerClass;

  function buildHelpers() {
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

    function findManagementInput(formElement, prefix, suffix) {
      if (!formElement) {
        return null;
      }
      return formElement.querySelector('input[name="' + prefix + "-" + suffix + '"]');
    }

    function buildContext(source) {
      if (!source) {
        return null;
      }

      var element = null;
      if (source.element && source.element.nodeType === 1) {
        element = source.element;
      } else if (source.nodeType === 1) {
        element = source;
      }

      if (!element || !element.querySelector) {
        return null;
      }

      var formElement = source.formElement;
      if (!formElement && element.closest) {
        formElement = element.closest("form");
      }

      var prefix = source.prefix;
      if (!prefix && element.dataset) {
        prefix = element.dataset.formsetPrefix;
      }
      if (!prefix) {
        prefix = "reference";
      }

      var container = source.container || source.containerTarget;
      if (!container && element.querySelector) {
        container = element.querySelector('[data-qc-references-target="container"]');
      }

      var template = source.template || source.templateTarget;
      if (!template && element.querySelector) {
        template = element.querySelector('template[data-qc-references-target="template"]');
      }

      var emptyMessage = source.emptyMessage || source.emptyMessageTarget;
      if (!emptyMessage && element.querySelector) {
        emptyMessage = element.querySelector('[data-qc-references-target="emptyMessage"]');
      }

      var totalFormsInput = source.totalFormsInput;
      if (!totalFormsInput) {
        totalFormsInput = findManagementInput(formElement, prefix, "TOTAL_FORMS");
      }

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

    function syncContext(target, ctx) {
      if (!target || !ctx) {
        return;
      }
      target.formElement = ctx.formElement;
      target.prefix = ctx.prefix;
      target.totalFormsInput = ctx.totalFormsInput;
    }

    function ensureTotalForms(ctx) {
      if (!ctx) {
        return;
      }
      if (!ctx.totalFormsInput && ctx.formElement) {
        ctx.totalFormsInput = findManagementInput(ctx.formElement, ctx.prefix, "TOTAL_FORMS");
      }
    }

    function countReferences(ctx) {
      if (!ctx || !ctx.container) {
        return 0;
      }
      return ctx.container.querySelectorAll("[data-qc-reference]").length;
    }

    function nextIndex(ctx) {
      if (!ctx) {
        return 0;
      }
      ensureTotalForms(ctx);
      if (ctx.totalFormsInput) {
        return parseInteger(ctx.totalFormsInput.value);
      }
      return countReferences(ctx);
    }

    function nextOrder(ctx) {
      if (!ctx || !ctx.container) {
        return nextIndex(ctx);
      }
      var maxOrder = -1;
      ctx.container
        .querySelectorAll('input[name$="-order"]')
        .forEach(function (input) {
          var value = parseInteger(input.value);
          if (value > maxOrder) {
            maxOrder = value;
          }
        });
      return maxOrder + 1;
    }

    function createReferenceElement(ctx, index) {
      if (!ctx || !ctx.template) {
        return null;
      }
      if (typeof document === "undefined") {
        return null;
      }
      var templateHtml = ctx.template.innerHTML;
      if (!templateHtml) {
        return null;
      }
      var markup = replacePrefixTokens(templateHtml, ctx.prefix, index);
      var wrapper = document.createElement("div");
      wrapper.innerHTML = markup.trim();
      return wrapper.firstElementChild;
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

    function ensureRefId(element, index) {
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

    function setDeleteValue(element, value) {
      if (!element) {
        return;
      }
      var deleteInput = element.querySelector('input[name$="-DELETE"]');
      if (deleteInput) {
        var finalValue = value || "";
        deleteInput.value = finalValue;
        if (deleteInput.type === "checkbox") {
          deleteInput.checked = Boolean(finalValue);
        }
      }
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

    function focusFirstField(element) {
      if (!element) {
        return;
      }
      var field = element.querySelector("input, textarea, select");
      if (field && typeof field.focus === "function") {
        field.focus();
      }
    }

    function markDeleteField(card, deleted) {
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

    function setFieldDisabledState(card, disabled) {
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

    function toggleReferenceVisibility(card, deleted) {
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
      setFieldDisabledState(card, deleted);
    }

    function isMarkedForDeletion(card) {
      if (!card) {
        return false;
      }
      if (card.dataset) {
        if (card.dataset.deleted === "true" || card.dataset.referenceDeleted === "true") {
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

    function visibleReferences(ctx) {
      if (!ctx || !ctx.container) {
        return [];
      }
      var references = Array.prototype.slice.call(
        ctx.container.querySelectorAll("[data-qc-reference]")
      );
      return references.filter(function (element) {
        return !isMarkedForDeletion(element);
      });
    }

    function refreshEmptyState(ctx) {
      if (!ctx || !ctx.emptyMessage) {
        return;
      }
      var visible = visibleReferences(ctx);
      ctx.emptyMessage.hidden = visible.length > 0;
    }

    function applyInitialDeletedState(ctx) {
      if (!ctx || !ctx.container) {
        return;
      }
      ctx.container
        .querySelectorAll("[data-qc-reference]")
        .forEach(function (element) {
          toggleReferenceVisibility(element, isMarkedForDeletion(element));
        });
    }

    function addReference(ctx) {
      if (!ctx || !ctx.container) {
        return null;
      }
      var index = nextIndex(ctx);
      var newElement = createReferenceElement(ctx, index);
      if (!newElement) {
        return null;
      }
      var orderValue = nextOrder(ctx);
      setOrderValue(newElement, orderValue);
      ensureRefId(newElement, index);
      setDeleteValue(newElement, "");
      toggleReferenceVisibility(newElement, false);
      ctx.container.appendChild(newElement);
      setTotalForms(ctx, index + 1);
      refreshEmptyState(ctx);
      return newElement;
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

    function sectionContext(source) {
      if (!source || !source.closest) {
        return null;
      }
      var section = source.closest('[data-controller~="qc-references"]');
      if (!section) {
        return null;
      }
      return { element: section };
    }

    return {
      buildContext: buildContext,
      syncContext: syncContext,
      refreshEmptyState: refreshEmptyState,
      applyInitialDeletedState: applyInitialDeletedState,
      addReference: addReference,
      markDeleteField: markDeleteField,
      toggleReferenceVisibility: toggleReferenceVisibility,
      findReferenceCard: findReferenceCard,
      focusFirstField: focusFirstField,
      sectionContext: sectionContext,
    };
  }

  function initializeFallback(root, helpers) {
    if (typeof document === "undefined") {
      return;
    }

    function hasStimulus() {
      return Boolean(root.Stimulus && root.Stimulus.Controller);
    }

    function prepareSections() {
      if (hasStimulus()) {
        return;
      }
      var sections = document.querySelectorAll('[data-controller~="qc-references"]');
      sections.forEach(function (section) {
        if (section.dataset && section.dataset.qcReferencesFallback === "true") {
          return;
        }
        var ctx = helpers.buildContext({ element: section });
        if (!ctx) {
          return;
        }
        helpers.applyInitialDeletedState(ctx);
        helpers.refreshEmptyState(ctx);
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

      var target = event.target;
      var addTrigger = target && target.closest ? target.closest("[data-reference-add]") : null;
      if (addTrigger) {
        event.preventDefault();
        var ctxAdd = helpers.buildContext(helpers.sectionContext(addTrigger));
        if (!ctxAdd) {
          return;
        }
        var newElement = helpers.addReference(ctxAdd);
        if (newElement) {
          helpers.focusFirstField(newElement);
        }
        return;
      }

      var deleteTrigger = target && target.closest ? target.closest("[data-reference-delete]") : null;
      if (deleteTrigger) {
        event.preventDefault();
        var cardDelete = helpers.findReferenceCard(deleteTrigger);
        if (!cardDelete) {
          return;
        }
        var ctxDelete = helpers.buildContext(helpers.sectionContext(deleteTrigger));
        if (!ctxDelete) {
          return;
        }
        helpers.markDeleteField(cardDelete, true);
        helpers.toggleReferenceVisibility(cardDelete, true);
        helpers.refreshEmptyState(ctxDelete);
        return;
      }

      var restoreTrigger = target && target.closest ? target.closest("[data-reference-restore]") : null;
      if (restoreTrigger) {
        event.preventDefault();
        var cardRestore = helpers.findReferenceCard(restoreTrigger);
        if (!cardRestore) {
          return;
        }
        var ctxRestore = helpers.buildContext(helpers.sectionContext(restoreTrigger));
        if (!ctxRestore) {
          return;
        }
        helpers.markDeleteField(cardRestore, false);
        helpers.toggleReferenceVisibility(cardRestore, false);
        helpers.refreshEmptyState(ctxRestore);
      }
    });
  }

  function createStimulusController(Controller, helpers) {
    var QcReferencesController = class extends Controller {};
    QcReferencesController.targets = ["container", "template", "emptyMessage"];

    QcReferencesController.prototype.connect = function () {
      var ctx = helpers.buildContext(this);
      if (!ctx) {
        return;
      }
      helpers.applyInitialDeletedState(ctx);
      helpers.refreshEmptyState(ctx);
      helpers.syncContext(this, ctx);
    };

    QcReferencesController.prototype.addReference = function (event) {
      if (event) {
        event.preventDefault();
      }
      var ctx = helpers.buildContext(this);
      if (!ctx) {
        return;
      }
      var newElement = helpers.addReference(ctx);
      helpers.syncContext(this, ctx);
      if (newElement) {
        helpers.focusFirstField(newElement);
      }
    };

    QcReferencesController.prototype.deleteReference = function (event) {
      if (event) {
        event.preventDefault();
      }
      var card = helpers.findReferenceCard(event);
      if (!card) {
        return;
      }
      var ctx = helpers.buildContext(this);
      if (!ctx) {
        return;
      }
      helpers.markDeleteField(card, true);
      helpers.toggleReferenceVisibility(card, true);
      helpers.refreshEmptyState(ctx);
      helpers.syncContext(this, ctx);
    };

    QcReferencesController.prototype.restoreReference = function (event) {
      if (event) {
        event.preventDefault();
      }
      var card = helpers.findReferenceCard(event);
      if (!card) {
        return;
      }
      var ctx = helpers.buildContext(this);
      if (!ctx) {
        return;
      }
      helpers.markDeleteField(card, false);
      helpers.toggleReferenceVisibility(card, false);
      helpers.refreshEmptyState(ctx);
      helpers.syncContext(this, ctx);
    };

    QcReferencesController.prototype.refreshEmptyState = function () {
      var ctx = helpers.buildContext(this);
      if (!ctx) {
        return;
      }
      helpers.refreshEmptyState(ctx);
      helpers.syncContext(this, ctx);
    };

    return QcReferencesController;
  }
});
