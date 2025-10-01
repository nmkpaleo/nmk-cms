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
      if (!Stimulus) {
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
        application.register("qc-rows", controllerInstance);
      }

      global.QCRowsController = controllerInstance;
      global.QcRowsController = controllerInstance;
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
  var Controller = Stimulus.Controller;

  function optionText(select) {
    if (!select) {
      return "";
    }
    if (select.tagName === "SELECT") {
      var option = select.selectedOptions && select.selectedOptions[0];
      if (option) {
        return option.textContent || option.innerText || option.value || "";
      }
    }
    return select.value || "";
  }

  function replaceIndex(value, prefix, index) {
    if (typeof value !== "string") {
      return value;
    }
    var pattern = new RegExp("^" + prefix + "-\\d+-");
    return value.replace(pattern, prefix + "-" + index + "-");
  }

  function replaceId(value, prefix, index) {
    if (typeof value !== "string") {
      return value;
    }
    var pattern = new RegExp("^" + prefix + "-\\d+-");
    return value.replace(pattern, prefix + "-" + index + "-");
  }

  function iterateChipFields(chip, callback) {
    if (!chip) {
      return;
    }
    var fields = chip.querySelectorAll("input[name], select[name], textarea[name]");
    fields.forEach(function (field) {
      var name = field.getAttribute("name") || "";
      var match = name.match(/^(ident|specimen)-[^-]+-(.+)$/);
      if (!match) {
        return;
      }
      callback(field, match[2], match[1]);
    });
  }

  var QCRowsController = class extends Controller {
    static get targets() {
      return [
        "container",
        "rowTemplate",
        "identTemplate",
        "specimenTemplate",
        "emptyMessage",
      ];
    }

    initialize() {
      this.boundRowDragOver = this.onRowDragOver.bind(this);
      this.boundRowDrop = this.onRowDrop.bind(this);
      this.boundRowDragStart = this.onRowDragStart.bind(this);
      this.boundRowDragEnd = this.onRowDragEnd.bind(this);
      this.boundChipDragStart = this.onChipDragStart.bind(this);
      this.boundChipDragEnd = this.onChipDragEnd.bind(this);
      this.boundChipDragOver = this.onChipDragOver.bind(this);
      this.boundChipDrop = this.onChipDrop.bind(this);
      this.boundChipDragLeave = this.onChipDragLeave.bind(this);
      this.boundRequestChipRemoval = this.requestChipRemoval.bind(this);
      this.draggedRow = null;
      this.draggedChip = null;
      this.chipSourceContainer = null;
      this.sourceRow = null;
      this.management = {};
      this.nextRowSequence = null;
      this.initialRowCount = 0;
      this.removalBinElement = null;
    }

    connect() {
      this.formElement = this.element;
      if (this.hasContainerTarget) {
        this.containerElement = this.containerTarget;
      } else {
        this.containerElement = this.element.querySelector('[data-qc-row-container]') || this.element;
      }
      this.setupManagementForms();
      this.handleTextareaSizing();
      this.prepareRows();
      this.setupConflictCards();
      this.enhanceDynamicWidgets(this.formElement);
      this.refreshEmptyState();
    }

    setupManagementForms() {
      var prefixes = ["row", "ident", "specimen"];
      var self = this;
      prefixes.forEach(function (prefix) {
        var record = {
          prefix: prefix,
          totalInput: self.formElement.querySelector('input[name="' + prefix + '-TOTAL_FORMS"]'),
          initialInput: self.formElement.querySelector('input[name="' + prefix + '-INITIAL_FORMS"]'),
        };
        self.management[prefix] = record;
      });
      this.nextRowSequence = this.computeNextRowSequence();
      var rowRecord = this.management.row;
      if (rowRecord && rowRecord.initialInput) {
        var initialValue = parseInt(rowRecord.initialInput.value || '0', 10);
        if (!Number.isNaN(initialValue)) {
          this.initialRowCount = initialValue;
        }
      }
      if (!this.initialRowCount) {
        this.initialRowCount = this.rows().length;
      }
    }

    computeNextRowSequence() {
      var maxIndex = 0;
      var rows = this.rows();
      for (var i = 0; i < rows.length; i += 1) {
        var rowId = rows[i].getAttribute("data-qc-row-id") || "";
        var match = rowId.match(/-(\d+)$/);
        if (match) {
          var numeric = parseInt(match[1], 10);
          if (!Number.isNaN(numeric) && numeric >= maxIndex) {
            maxIndex = numeric + 1;
          }
        }
      }
      if (rows.length > maxIndex) {
        maxIndex = rows.length;
      }
      return maxIndex;
    }

    rows() {
      return Array.prototype.slice.call(
        this.containerElement.querySelectorAll('[data-qc-row]')
      );
    }

    handleTextareaSizing() {
      var textareas = this.formElement.querySelectorAll("textarea");
      textareas.forEach(function (textarea) {
        if (!textarea.hasAttribute("rows")) {
          textarea.setAttribute("rows", "2");
        }
      });
    }

    prepareRows() {
      var self = this;
      this.rows().forEach(function (row) {
        self.initializeRow(row);
      });
      this.updateRowIndexes();
      this.updateChipIndexes("ident");
      this.updateChipIndexes("specimen");
      this.refreshEmptyState();
    }

    initializeRow(row) {
      if (!row) {
        return;
      }
      row.classList.add("qc-row-card--ready");
      row.addEventListener("dragover", this.boundRowDragOver);
      row.addEventListener("drop", this.boundRowDrop);
      row.addEventListener("dragend", this.boundRowDragEnd);

      var handle = row.querySelector("[data-row-handle]");
      if (handle) {
        handle.addEventListener("dragstart", this.boundRowDragStart);
        handle.addEventListener("dragend", this.boundRowDragEnd);
      }

      var containers = row.querySelectorAll("[data-chip-container]");
      var self = this;
      containers.forEach(function (container) {
        container.addEventListener("dragover", self.boundChipDragOver);
        container.addEventListener("drop", self.boundChipDrop);
        container.addEventListener("dragleave", self.boundChipDragLeave);
        self.refreshEmptyIndicators(container);
      });

      var chips = row.querySelectorAll("[data-qc-chip]");
      chips.forEach(function (chip) {
        self.initializeChip(chip);
      });

      this.enhanceDynamicWidgets(row);
      this.checkRowEmpty(row);
    }

    initializeChip(chip) {
      if (!chip) {
        return;
      }
      chip.setAttribute("draggable", "true");
      chip.addEventListener("dragstart", this.boundChipDragStart);
      chip.addEventListener("dragend", this.boundChipDragEnd);
      var row = chip.closest('[data-qc-row]');
      if (row) {
        this.assignChipToRow(chip, row);
      }
      this.refreshChipSummary(chip);
      if (this.isChipMarkedForDeletion(chip)) {
        chip.dataset.chipRemoved = 'true';
        chip.hidden = true;
        chip.style.display = 'none';
        chip.setAttribute('aria-hidden', 'true');
      } else {
        chip.dataset.chipRemoved = 'false';
        chip.hidden = false;
        chip.style.removeProperty('display');
        chip.removeAttribute('aria-hidden');
      }
      if (chip.dataset.chipOpen === 'true') {
        this.openChipFields(chip, { focus: false });
      } else {
        this.closeChipFields(chip);
      }
      this.enhanceDynamicWidgets(chip);
      var removeButton = chip.querySelector('[data-action~="qc-rows#requestChipRemoval"]');
      if (removeButton && !removeButton.hasAttribute('data-qc-chip-remove-bound')) {
        removeButton.addEventListener('click', this.boundRequestChipRemoval);
        removeButton.setAttribute('data-qc-chip-remove-bound', 'true');
      }
    }

    setupConflictCards() {
      var self = this;
      var cards = this.formElement.querySelectorAll('[data-conflict]');
      cards.forEach(function (card) {
        self.toggleConflictSections(card);
        var radios = card.querySelectorAll('input[name^="resolution_action__"]');
        radios.forEach(function (radio) {
          radio.addEventListener('change', function () {
            self.toggleConflictSections(card);
          });
        });
      });
    }

    toggleConflictSections(card) {
      if (!card) {
        return;
      }
      var selected = card.querySelector('input[name^="resolution_action__"]:checked');
      var value = selected ? selected.value : null;
      var sections = card.querySelectorAll('[data-conflict-section]');
      sections.forEach(function (section) {
        var sectionType = section.getAttribute('data-conflict-section');
        if (sectionType === 'new_instance') {
          section.style.display = value === 'new_instance' ? '' : 'none';
        } else if (sectionType === 'update_existing') {
          section.style.display = value === 'update_existing' ? '' : 'none';
        }
      });
    }

    onRowDragStart(event) {
      if (!event || !event.dataTransfer) {
        return;
      }
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", "");
      var row = event.currentTarget.closest('[data-qc-row]');
      if (!row) {
        return;
      }
      this.draggedRow = row;
      row.classList.add("is-dragging");
    }

    onRowDragEnd(event) {
      if (event && event.currentTarget) {
        var row = event.currentTarget.closest('[data-qc-row]');
        if (row) {
          row.classList.remove("is-dragging");
        }
      }
      if (this.draggedRow) {
        this.draggedRow.classList.remove("is-dragging");
      }
      this.draggedRow = null;
    }

    onRowDragOver(event) {
      if (!this.draggedRow) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    }

    onRowDrop(event) {
      if (!this.draggedRow) {
        return;
      }
      event.preventDefault();
      var targetRow = event.currentTarget.closest('[data-qc-row]');
      if (!targetRow || targetRow === this.draggedRow) {
        return;
      }
      var bounding = targetRow.getBoundingClientRect();
      var offset = event.clientY - bounding.top;
      var shouldInsertBefore = offset < bounding.height / 2;
      var parent = targetRow.parentNode || this.containerElement;
      if (shouldInsertBefore) {
        parent.insertBefore(this.draggedRow, targetRow);
      } else if (targetRow.nextSibling) {
        parent.insertBefore(this.draggedRow, targetRow.nextSibling);
      } else {
        parent.appendChild(this.draggedRow);
      }
      this.updateRowIndexes();
    }

    onChipDragStart(event) {
      if (!event || !event.dataTransfer) {
        return;
      }
      var chip = event.currentTarget.closest('[data-qc-chip]');
      if (!chip) {
        return;
      }
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", "");
      this.draggedChip = chip;
      this.chipSourceContainer = chip.parentElement;
      this.sourceRow = chip.closest('[data-qc-row]');
      chip.classList.add("is-dragging");
    }

    onChipDragEnd(event) {
      if (event && event.currentTarget) {
        var chip = event.currentTarget.closest('[data-qc-chip]');
        if (chip) {
          chip.classList.remove("is-dragging");
        }
      }
      if (this.draggedChip) {
        this.draggedChip.classList.remove("is-dragging");
      }
      this.draggedChip = null;
      this.chipSourceContainer = null;
      this.sourceRow = null;
    }

    onChipDragOver(event) {
      if (!this.draggedChip) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      var container = event.currentTarget;
      container.classList.add("qc-chip-zone--active");
    }

    onChipDragLeave(event) {
      var container = event.currentTarget;
      container.classList.remove("qc-chip-zone--active");
    }

    onChipDrop(event) {
      if (!this.draggedChip) {
        return;
      }
      event.preventDefault();
      var container = event.currentTarget;
      container.classList.remove("qc-chip-zone--active");
      this.moveChipToContainer(this.draggedChip, container);
      if (this.chipSourceContainer && this.chipSourceContainer !== container) {
        this.refreshEmptyIndicators(this.chipSourceContainer);
        if (this.sourceRow) {
          this.checkRowEmpty(this.sourceRow);
        }
      }
      var newRow = container.closest('[data-qc-row]');
      this.checkRowEmpty(newRow);
      this.draggedChip.classList.remove("is-dragging");
      this.draggedChip = null;
      this.chipSourceContainer = null;
      this.sourceRow = null;
    }

    moveChipToContainer(chip, container) {
      if (!chip || !container) {
        return;
      }
      this.clearDeletionState(chip);
      container.appendChild(chip);
      var row = container.closest('[data-qc-row]');
      if (row) {
        this.assignChipToRow(chip, row);
        this.refreshChipSummary(chip);
      }
      this.refreshEmptyIndicators(container);
    }

    assignChipToRow(chip, row) {
      if (!chip || !row) {
        return;
      }
      var rowId = row.getAttribute('data-qc-row-id') || '';
      iterateChipFields(chip, function (field, suffix) {
        if (suffix === 'row_id') {
          field.value = rowId;
        }
      });
    }

    refreshEmptyIndicators(container) {
      if (!container) {
        return;
      }
      var indicator = container.parentElement
        ? container.parentElement.querySelector('[data-empty-indicator]')
        : null;
      if (!indicator) {
        return;
      }
      var hasChip = this.activeChips(container).length > 0;
      indicator.hidden = hasChip;
    }

    checkRowEmpty(row) {
      if (!row) {
        return;
      }
      var hasChip = this.activeChips(row).length > 0;
      var alert = row.querySelector('[data-row-alert]');
      if (alert) {
        alert.hidden = hasChip;
      }
      if (!hasChip) {
        row.setAttribute('data-row-empty', 'true');
      } else {
        row.removeAttribute('data-row-empty');
      }
    }

    refreshEmptyState() {
      if (!this.hasEmptyMessageTarget) {
        return;
      }
      var hasRows = this.rows().length > 0;
      this.emptyMessageTarget.hidden = hasRows;
    }

    toggleChipSelection(event) {
      if (event) {
        event.preventDefault();
      }
      var button = event ? event.currentTarget : null;
      var chip = button ? button.closest('[data-qc-chip]') : null;
      if (!chip || !button) {
        return;
      }
      var isSelected = chip.classList.contains('qc-chip--selected');
      if (isSelected) {
        this.closeChipFields(chip);
      } else {
        this.openChipFields(chip, { focus: true });
      }
    }

    addChip(event) {
      if (event) {
        event.preventDefault();
      }
      var trigger = event ? event.currentTarget : null;
      if (!trigger) {
        return;
      }
      var type = trigger.getAttribute('data-chip-type') || 'ident';
      var row = this.rowFromEvent(event);
      if (!row) {
        return;
      }
      var container = row.querySelector('[data-chip-container-type="' + type + '"]');
      if (!container) {
        return;
      }
      if (type === 'ident') {
        var existing = this.activeChips(container, type);
        if (existing.length > 0) {
          this.openChipFields(existing[0], { focus: true });
          if (typeof existing[0].scrollIntoView === 'function') {
            existing[0].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
          return;
        }
      }
      var chip = this.createChipFromTemplate(type);
      if (!chip) {
        return;
      }
      container.appendChild(chip);
      this.initializeChip(chip);
      this.clearDeletionState(chip);
      this.refreshChipSummary(chip);
      this.updateChipIndexes(type);
      this.refreshEmptyIndicators(container);
      this.checkRowEmpty(row);
      this.openChipFields(chip, { focus: true });
    }

    requestChipRemoval(event) {
      if (event) {
        event.preventDefault();
      }
      var chip = this.chipFromEvent(event);
      if (!chip || chip.dataset.chipRemoved === 'true') {
        return;
      }
      var type = chip.getAttribute('data-chip-type');
      this.finalizeChipRemoval(chip, type);
    }

    chipFromEvent(event) {
      var trigger = event ? event.currentTarget : null;
      return trigger ? trigger.closest('[data-qc-chip]') : null;
    }

    finalizeChipRemoval(chip, type) {
      if (!chip) {
        return;
      }
      var container = chip.parentElement;
      var row = chip.closest('[data-qc-row]');
      var deleteInput = chip.querySelector('input[name$="-DELETE"]');
      var shouldReindex = true;
      if (deleteInput) {
        if (deleteInput.type === 'checkbox') {
          deleteInput.checked = true;
          deleteInput.value = 'on';
        } else {
          deleteInput.value = 'on';
        }
        chip.dataset.chipRemoved = 'true';
        chip.classList.remove('qc-chip--selected');
        var toggleButton = chip.querySelector('.qc-chip__pill');
        if (toggleButton) {
          toggleButton.setAttribute('aria-pressed', 'false');
        }
        var fields = chip.querySelector('.qc-chip__fields');
        if (fields) {
          fields.hidden = true;
        }
        chip.hidden = true;
        chip.style.display = 'none';
        chip.setAttribute('aria-hidden', 'true');
        this.ensureRemovalBin().appendChild(chip);
        shouldReindex = false;
      } else if (chip.parentElement) {
        chip.parentElement.removeChild(chip);
      }
      if (shouldReindex) {
        this.updateChipIndexes(type);
      }
      if (container) {
        this.refreshEmptyIndicators(container);
      }
      if (row) {
        this.checkRowEmpty(row);
      }
    }

    ensureRemovalBin() {
      if (this.removalBinElement && this.removalBinElement.isConnected) {
        return this.removalBinElement;
      }
      var bin = this.formElement.querySelector('[data-qc-rows-removal-bin]');
      if (!bin) {
        bin = document.createElement('div');
        bin.setAttribute('data-qc-rows-removal-bin', '');
        bin.style.display = 'none';
        bin.setAttribute('aria-hidden', 'true');
        this.formElement.appendChild(bin);
      }
      this.removalBinElement = bin;
      return bin;
    }

    enhanceDynamicWidgets(root) {
      if (!root) {
        return;
      }
      var widgets = root.querySelectorAll('.django-select2');
      if (!widgets.length) {
        return;
      }
      var jq = null;
      if (window.django && window.django.jQuery) {
        jq = window.django.jQuery;
      } else if (window.jQuery) {
        jq = window.jQuery;
      }
      if (!jq) {
        return;
      }
      widgets.forEach(function (element) {
        var $element = jq(element);
        if (typeof $element.djangoSelect2 !== 'function') {
          return;
        }
        if ($element.hasClass('select2-hidden-accessible')) {
          return;
        }
        $element.djangoSelect2();
      });
    }

    insertRow(event) {
      if (event) {
        event.preventDefault();
      }
      var referenceRow = this.rowFromEvent(event);
      var position = event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.position
        : 'after';
      var newRow = this.createRowElement();
      if (!newRow) {
        return;
      }
      var parent = this.getRowParent(referenceRow);
      if (referenceRow) {
        if (position === 'before') {
          parent.insertBefore(newRow, referenceRow);
        } else if (referenceRow.nextSibling) {
          parent.insertBefore(newRow, referenceRow.nextSibling);
        } else {
          parent.appendChild(newRow);
        }
      } else {
        parent.appendChild(newRow);
      }
      this.initializeRow(newRow);
      this.updateRowIndexes();
      this.refreshEmptyState();
    }

    duplicateRow(event) {
      if (event) {
        event.preventDefault();
      }
      var sourceRow = this.rowFromEvent(event);
      if (!sourceRow) {
        return;
      }
      var newRow = this.createRowElement();
      if (!newRow) {
        return;
      }
      var parent = this.getRowParent(sourceRow);
      if (sourceRow.nextSibling) {
        parent.insertBefore(newRow, sourceRow.nextSibling);
      } else {
        parent.appendChild(newRow);
      }
      this.initializeRow(newRow);
      this.copyRowValues(sourceRow, newRow);
      this.copyRowChips(sourceRow, newRow);
      this.updateRowIndexes();
      this.updateChipIndexes('ident');
      this.updateChipIndexes('specimen');
      this.checkRowEmpty(sourceRow);
      this.checkRowEmpty(newRow);
      this.refreshEmptyState();
    }

    splitRow(event) {
      if (event) {
        event.preventDefault();
      }
      var sourceRow = this.rowFromEvent(event);
      if (!sourceRow) {
        return;
      }
      var selected = Array.prototype.slice.call(
        sourceRow.querySelectorAll('.qc-chip--selected')
      );
      if (!selected.length) {
        var specimenContainer = sourceRow.querySelector('[data-chip-container-type="specimen"]');
        if (specimenContainer) {
          var specimenChips = specimenContainer.querySelectorAll('[data-qc-chip]');
          if (specimenChips.length) {
            selected.push(specimenChips[specimenChips.length - 1]);
          }
        }
      }
      if (!selected.length) {
        var identContainer = sourceRow.querySelector('[data-chip-container-type="ident"]');
        if (identContainer) {
          var identChip = identContainer.querySelector('[data-qc-chip]');
          if (identChip) {
            selected.push(identChip);
          }
        }
      }
      if (!selected.length) {
        window.alert('Select at least one chip to split into a new row.');
        return;
      }
      var newRow = this.createRowElement();
      if (!newRow) {
        return;
      }
      var parent = this.getRowParent(sourceRow);
      if (sourceRow.nextSibling) {
        parent.insertBefore(newRow, sourceRow.nextSibling);
      } else {
        parent.appendChild(newRow);
      }
      this.initializeRow(newRow);
      var self = this;
      selected.forEach(function (chip) {
        var button = chip.querySelector('[data-action="qc-rows#toggleChipSelection"]');
        if (button) {
          button.setAttribute('aria-pressed', 'false');
        }
        chip.classList.remove('qc-chip--selected');
        var containerType = chip.getAttribute('data-chip-type');
        var container = newRow.querySelector('[data-chip-container-type="' + containerType + '"]');
        if (container) {
          self.moveChipToContainer(chip, container);
        }
      });
      this.updateRowIndexes();
      this.updateChipIndexes('ident');
      this.updateChipIndexes('specimen');
      this.checkRowEmpty(sourceRow);
      this.checkRowEmpty(newRow);
      this.refreshEmptyState();
    }

    mergeRow(event) {
      if (event) {
        event.preventDefault();
      }
      var sourceRow = this.rowFromEvent(event);
      if (!sourceRow) {
        return;
      }
      var previous = this.findSiblingRow(sourceRow, -1);
      var next = this.findSiblingRow(sourceRow, 1);
      var targetRow = previous || next;
      if (!targetRow) {
        window.alert('No adjacent row is available to merge with.');
        return;
      }
      var confirmed = window.confirm('Merge this row with its neighbour?');
      if (!confirmed) {
        return;
      }
      var self = this;
      ['ident', 'specimen'].forEach(function (type) {
        var sourceContainer = sourceRow.querySelector('[data-chip-container-type="' + type + '"]');
        var targetContainer = targetRow.querySelector('[data-chip-container-type="' + type + '"]');
        if (!sourceContainer || !targetContainer) {
          return;
        }
        var chips = self.activeChips(sourceContainer, type);
        chips.forEach(function (chip) {
          self.moveChipToContainer(chip, targetContainer);
        });
        self.refreshEmptyIndicators(sourceContainer);
        self.refreshEmptyIndicators(targetContainer);
      });
      this.removeRowElement(sourceRow, { skipConfirm: true });
      this.checkRowEmpty(targetRow);
      this.updateChipIndexes('ident');
      this.updateChipIndexes('specimen');
    }

    deleteRow(event) {
      if (event) {
        event.preventDefault();
      }
      var row = this.rowFromEvent(event);
      if (!row) {
        return;
      }
      this.removeRowElement(row, { skipConfirm: false });
    }

    confirmRemoveRow(event) {
      if (event) {
        event.preventDefault();
      }
      var row = this.rowFromEvent(event);
      if (!row) {
        return;
      }
      this.removeRowElement(row, { skipConfirm: false });
    }

    dismissEmptyRowWarning(event) {
      if (event) {
        event.preventDefault();
      }
      var row = this.rowFromEvent(event);
      if (!row) {
        return;
      }
      var alert = row.querySelector('[data-row-alert]');
      if (alert) {
        alert.hidden = true;
      }
    }

    removeRowElement(row, options) {
      if (!row) {
        return;
      }
      var settings = options || {};
      var skipConfirm = settings.skipConfirm;
      if (!skipConfirm) {
        var chipCount = this.activeChips(row).length;
        var message = chipCount > 0
          ? 'Remove this specimen row and its linked identifications and specimens?'
          : 'Remove this specimen row?';
        var confirmed = window.confirm(message);
        if (!confirmed) {
          return;
        }
      }
      if (row.parentElement) {
        row.parentElement.removeChild(row);
      }
      this.updateRowIndexes();
      this.updateChipIndexes('ident');
      this.updateChipIndexes('specimen');
      this.refreshEmptyState();
    }

    copyRowValues(sourceRow, targetRow) {
      var values = {};
      var sourceFields = sourceRow.querySelectorAll('input[name^="row-"], select[name^="row-"], textarea[name^="row-"]');
      sourceFields.forEach(function (field) {
        var name = field.getAttribute('name') || '';
        var suffix = name.replace(/^row-\d+-/, '');
        if (suffix === 'row_id' || suffix === 'order') {
          return;
        }
        values[suffix] = field.value;
      });
      var targetFields = targetRow.querySelectorAll('input[name^="row-"], select[name^="row-"], textarea[name^="row-"]');
      targetFields.forEach(function (field) {
        var name = field.getAttribute('name') || '';
        var suffix = name.replace(/^row-\d+-/, '');
        if (Object.prototype.hasOwnProperty.call(values, suffix)) {
          field.value = values[suffix];
        }
      });
    }

    copyRowChips(sourceRow, targetRow) {
      var self = this;
      ['ident', 'specimen'].forEach(function (type) {
        var sourceContainer = sourceRow.querySelector('[data-chip-container-type="' + type + '"]');
        var targetContainer = targetRow.querySelector('[data-chip-container-type="' + type + '"]');
        if (!sourceContainer || !targetContainer) {
          return;
        }
        var chips = self.activeChips(sourceContainer, type);
        chips.forEach(function (chip) {
          var clone = self.createChipFromTemplate(type);
          if (!clone) {
            return;
          }
          targetContainer.appendChild(clone);
          self.initializeChip(clone);
          self.clearDeletionState(clone);
          self.copyChipValues(chip, clone);
          self.assignChipToRow(clone, targetRow);
          self.refreshChipSummary(clone);
        });
        self.refreshEmptyIndicators(targetContainer);
      });
    }

    copyChipValues(sourceChip, targetChip) {
      var values = {};
      iterateChipFields(sourceChip, function (field, suffix) {
        if (suffix === 'row_id') {
          return;
        }
        values[suffix] = field.value;
      });
      iterateChipFields(targetChip, function (field, suffix) {
        if (suffix === 'row_id') {
          return;
        }
        if (Object.prototype.hasOwnProperty.call(values, suffix)) {
          field.value = values[suffix];
        }
      });
    }

    createRowElement() {
      if (!this.hasRowTemplateTarget) {
        return null;
      }
      var fragment = this.rowTemplateTarget.content.cloneNode(true);
      var row = fragment.querySelector('[data-qc-row]');
      if (!row) {
        return null;
      }
      var newId = this.generateRowId();
      row.setAttribute('data-qc-row-id', newId);
      row.setAttribute('data-new-row', 'true');
      var rowIdInput = row.querySelector('input[name^="row-"][name$="-row_id"]');
      if (rowIdInput) {
        rowIdInput.value = newId;
      }
      var orderInput = row.querySelector('input[name^="row-"][name$="-order"]');
      if (orderInput) {
        orderInput.value = this.rows().length;
      }
      return row;
    }

    createChipFromTemplate(type) {
      var template = type === 'ident' ? this.identTemplateTarget : this.specimenTemplateTarget;
      if (!template) {
        return null;
      }
      var fragment = template.content.cloneNode(true);
      return fragment.querySelector('[data-qc-chip]');
    }

    generateRowId() {
      if (typeof this.nextRowSequence !== 'number') {
        this.nextRowSequence = this.rows().length;
      }
      var rowId = 'row-' + this.nextRowSequence;
      this.nextRowSequence += 1;
      return rowId;
    }

    getRowParent(referenceRow) {
      if (referenceRow && referenceRow.parentNode) {
        return referenceRow.parentNode;
      }
      return this.containerElement;
    }

    updateRowIndexes() {
      var rows = this.rows();
      rows.forEach(function (row, index) {
        var display = row.querySelector('[data-row-index-display]');
        if (display) {
          display.textContent = String(index + 1);
        }
        var orderInput = row.querySelector('input[name^="row-"][name$="-order"]');
        if (orderInput) {
          orderInput.value = index;
        }
        var inputs = row.querySelectorAll('input[name^="row-"], select[name^="row-"], textarea[name^="row-"]');
        inputs.forEach(function (field) {
          field.name = replaceIndex(field.name, 'row', index);
          if (field.id) {
            field.id = replaceId(field.id, 'id_row', index);
          }
        });
        var labels = row.querySelectorAll('label[for^="id_row-"]');
        labels.forEach(function (label) {
          label.htmlFor = replaceId(label.htmlFor, 'id_row', index);
        });
      });
      this.setTotalForms('row', rows.length);
    }

    updateChipIndexes(type) {
      var prefix = type === 'ident' ? 'ident' : 'specimen';
      var chips = Array.prototype.slice.call(
        this.formElement.querySelectorAll('[data-qc-chip][data-chip-type="' + type + '"]')
      );
      chips.forEach(function (chip, index) {
        chip.dataset.formPrefix = prefix + '-' + index;
        iterateChipFields(chip, function (field, suffix, fieldPrefix) {
          field.name = replaceIndex(field.name, fieldPrefix, index);
          if (field.id) {
            field.id = replaceId(field.id, 'id_' + fieldPrefix, index);
          }
        });
        var labels = chip.querySelectorAll('label[for^="id_' + prefix + '-"]');
        labels.forEach(function (label) {
          label.htmlFor = replaceId(label.htmlFor, 'id_' + prefix, index);
        });
      });
      this.setTotalForms(prefix, chips.length);
    }

    setTotalForms(prefix, value) {
      var record = this.management[prefix];
      if (record && record.totalInput) {
        record.totalInput.value = String(value);
        if (record.initialInput) {
          var initialValue = parseInt(record.initialInput.value || '0', 10);
          if (initialValue > value) {
            record.initialInput.value = String(value);
            if (prefix === 'row') {
              this.initialRowCount = value;
            }
          }
        }
      }
    }

    activeChips(root, type) {
      if (!root) {
        return [];
      }
      var selector = '[data-qc-chip]';
      if (type) {
        selector += '[data-chip-type="' + type + '"]';
      }
      var chips = Array.prototype.slice.call(root.querySelectorAll(selector));
      var self = this;
      return chips.filter(function (chip) {
        return !self.isChipMarkedForDeletion(chip);
      });
    }

    isChipMarkedForDeletion(chip) {
      if (!chip) {
        return false;
      }
      if (chip.dataset.chipRemoved === 'true') {
        return true;
      }
      var deleteInput = chip.querySelector('input[name$="-DELETE"]');
      if (!deleteInput) {
        return false;
      }
      if (deleteInput.type === 'checkbox') {
        return deleteInput.checked;
      }
      var value = deleteInput.value;
      return value === 'on' || value === 'true' || value === '1';
    }

    clearDeletionState(chip) {
      if (!chip) {
        return;
      }
      chip.dataset.chipRemoved = 'false';
      chip.hidden = false;
      chip.style.removeProperty('display');
      chip.removeAttribute('aria-hidden');
      var deleteInput = chip.querySelector('input[name$="-DELETE"]');
      if (deleteInput) {
        if (deleteInput.type === 'checkbox') {
          deleteInput.checked = false;
          deleteInput.value = 'on';
        } else {
          deleteInput.value = '';
        }
      }
    }

    openChipFields(chip, options) {
      if (!chip) {
        return;
      }
      chip.classList.add('qc-chip--selected');
      var button = chip.querySelector('.qc-chip__pill');
      if (button) {
        button.setAttribute('aria-pressed', 'true');
      }
      var fields = chip.querySelector('.qc-chip__fields');
      if (fields) {
        fields.hidden = false;
      }
      var shouldFocus = !options || options.focus !== false;
      if (shouldFocus && fields) {
        var focusTarget = fields.querySelector('input, select, textarea');
        if (focusTarget && typeof focusTarget.focus === 'function') {
          focusTarget.focus();
        }
      }
    }

    closeChipFields(chip) {
      if (!chip) {
        return;
      }
      chip.classList.remove('qc-chip--selected');
      var button = chip.querySelector('.qc-chip__pill');
      if (button) {
        button.setAttribute('aria-pressed', 'false');
      }
      var fields = chip.querySelector('.qc-chip__fields');
      if (fields) {
        fields.hidden = true;
      }
    }

    refreshChipSummary(chip) {
      if (!chip) {
        return;
      }
      var summaryElement = chip.querySelector('[data-chip-summary]');
      if (!summaryElement) {
        return;
      }
      var type = chip.getAttribute('data-chip-type');
      var summary = '';
      if (type === 'ident') {
        var verbatim = chip.querySelector('textarea[name$="-verbatim_identification"], input[name$="-verbatim_identification"]');
        if (verbatim && verbatim.value) {
          summary = verbatim.value.trim();
        }
      } else {
        var elementField = chip.querySelector('select[name$="-element"]');
        summary = optionText(elementField);
        var specVerbatim = chip.querySelector('textarea[name$="-verbatim_element"], input[name$="-verbatim_element"]');
        if (!summary && specVerbatim && specVerbatim.value) {
          summary = specVerbatim.value;
        }
        var portion = chip.querySelector('input[name$="-portion"]');
        if (portion && portion.value) {
          summary = summary ? summary + ' (' + portion.value + ')' : portion.value;
        }
      }
      if (!summary) {
        summary = type === 'ident' ? 'Unassigned identification' : 'Unspecified specimen';
      }
      summaryElement.textContent = summary;
    }

    rowFromEvent(event) {
      if (!event) {
        return null;
      }
      var element = event.currentTarget || event.target;
      if (!element) {
        return null;
      }
      return element.closest('[data-qc-row]');
    }

    findSiblingRow(row, direction) {
      if (!row) {
        return null;
      }
      var sibling = row;
      do {
        sibling = direction < 0 ? sibling.previousElementSibling : sibling.nextElementSibling;
      } while (sibling && !sibling.hasAttribute('data-qc-row'));
      return sibling;
    }
  };

  QCRowsController.targets = ["container", "rowTemplate", "identTemplate", "specimenTemplate", "emptyMessage"];

  return QCRowsController;
});
