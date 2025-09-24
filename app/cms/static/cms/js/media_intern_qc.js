(function () {
  function updateOrder(container) {
    var rows = container.querySelectorAll('[data-qc-row]');
    rows.forEach(function (row, index) {
      var orderInput = row.querySelector('input[name$="-order"]');
      if (orderInput) {
        orderInput.value = index;
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('[data-controller="qc-rows"]');
    if (!form) {
      return;
    }

    form.querySelectorAll('textarea').forEach(function (textarea) {
      textarea.setAttribute('rows', '2');
    });

    var container = form.querySelector('[data-qc-rows-target="container"]');
    if (!container) {
      container = form;
    }

    container.addEventListener('click', function (event) {
      var button = event.target.closest('[data-action="qc-rows#moveUp"], [data-action="qc-rows#moveDown"]');
      if (!button) {
        return;
      }
      event.preventDefault();
      var row = button.closest('[data-qc-row]');
      if (!row) {
        return;
      }
      if (button.dataset.action === 'qc-rows#moveUp') {
        var previous = row.previousElementSibling;
        while (previous && !previous.hasAttribute('data-qc-row')) {
          previous = previous.previousElementSibling;
        }
        if (previous) {
          container.insertBefore(row, previous);
        }
      } else {
        var next = row.nextElementSibling;
        while (next && !next.hasAttribute('data-qc-row')) {
          next = next.nextElementSibling;
        }
        if (next) {
          container.insertBefore(next, row);
        }
      }
      updateOrder(container);
    });

    updateOrder(container);

    function toggleConflict(container) {
      var selected = container.querySelector('input[name^="resolution_action__"]:checked');
      var value = selected ? selected.value : null;
      container.querySelectorAll('[data-conflict-section]').forEach(function (section) {
        var sectionType = section.getAttribute('data-conflict-section');
        if (sectionType === 'new_instance') {
          section.style.display = value === 'new_instance' ? '' : 'none';
        } else if (sectionType === 'update_existing') {
          section.style.display = value === 'update_existing' ? '' : 'none';
        }
      });
    }

    form.querySelectorAll('[data-conflict]').forEach(function (conflictCard) {
      toggleConflict(conflictCard);
      conflictCard
        .querySelectorAll('input[name^="resolution_action__"]')
        .forEach(function (radio) {
          radio.addEventListener('change', function () {
            toggleConflict(conflictCard);
          });
        });
    });
  });
})();
