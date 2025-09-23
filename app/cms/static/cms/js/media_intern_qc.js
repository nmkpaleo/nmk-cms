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
  });
})();
