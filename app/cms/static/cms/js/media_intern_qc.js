(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('[data-controller="qc-rows"]');
    if (!form) {
      return;
    }
    if (!window.StimulusApp && window.Stimulus && window.Stimulus.Application && typeof window.Stimulus.Application.start === 'function') {
      window.StimulusApp = window.Stimulus.Application.start();
    }
  });
})();
