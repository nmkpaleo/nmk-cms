(function () {
  'use strict';

  var OFFSET = 16;
  var VISIBLE_CLASS = 'is-visible';
  var CENTERED_CLASS = 'is-centered';
  var LARGE_SCREEN_QUERY = '(min-width: 993px)';

  function ready(callback) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback, { once: true });
    } else {
      callback();
    }
  }

  function clamp(value, min, max) {
    if (value < min) {
      return min;
    }
    if (value > max) {
      return max;
    }
    return value;
  }

  ready(function () {
    var previewContainer = document.getElementById('media-hover-preview');
    if (!previewContainer) {
      return;
    }

    var previewImage = document.getElementById('media-hover-preview-img');
    if (!previewImage) {
      return;
    }

    var triggers = Array.prototype.slice.call(
      document.querySelectorAll('.media-preview-trigger')
    );

    if (!triggers.length) {
      return;
    }

    var activeTrigger = null;
    var largeScreenMedia =
      typeof window.matchMedia === 'function'
        ? window.matchMedia(LARGE_SCREEN_QUERY)
        : null;
    var supportsPointerEvents = typeof window.PointerEvent !== 'undefined';

    function isLargeScreen() {
      if (largeScreenMedia) {
        return largeScreenMedia.matches;
      }
      return window.innerWidth >= 993;
    }

    function centerPreview() {
      previewContainer.classList.add(CENTERED_CLASS);
      previewContainer.style.removeProperty('left');
      previewContainer.style.removeProperty('top');
    }

    function uncenterPreview() {
      previewContainer.classList.remove(CENTERED_CLASS);
    }

    function hidePreview() {
      if (!previewContainer.classList.contains(VISIBLE_CLASS)) {
        return;
      }

      previewContainer.classList.remove(VISIBLE_CLASS);
      previewContainer.style.removeProperty('left');
      previewContainer.style.removeProperty('top');
      previewContainer.setAttribute('aria-hidden', 'true');
      previewImage.removeAttribute('src');
      previewImage.setAttribute('alt', '');
      activeTrigger = null;
      uncenterPreview();
    }

    function positionPreview(trigger, event) {
      if (!trigger) {
        return;
      }

      if (isLargeScreen()) {
        return;
      }

      var x;
      var y;

      if (event && typeof event.clientX === 'number' && typeof event.clientY === 'number') {
        x = event.clientX + OFFSET;
        y = event.clientY + OFFSET;
      } else {
        var rect = trigger.getBoundingClientRect();
        x = rect.right + OFFSET;
        y = rect.top;
      }

      var containerRect = previewContainer.getBoundingClientRect();
      var maxX = window.innerWidth - containerRect.width - OFFSET;
      var maxY = window.innerHeight - containerRect.height - OFFSET;

      previewContainer.style.left = clamp(x, OFFSET, maxX) + 'px';
      previewContainer.style.top = clamp(y, OFFSET, maxY) + 'px';
    }

    function showPreview(trigger, event) {
      var previewUrl = trigger.getAttribute('data-media-preview');
      if (!previewUrl) {
        return;
      }

      activeTrigger = trigger;
      previewImage.setAttribute('src', previewUrl);
      previewImage.setAttribute(
        'alt',
        trigger.getAttribute('data-media-alt') || ''
      );
      previewContainer.setAttribute('aria-hidden', 'false');
      previewContainer.classList.add(VISIBLE_CLASS);
      if (isLargeScreen()) {
        centerPreview();
      } else {
        uncenterPreview();
        positionPreview(trigger, event);
      }
    }

    function onPointerEnter(event) {
      if (event.pointerType === 'touch') {
        hidePreview();
        return;
      }
      showPreview(event.currentTarget, event);
    }

    function onPointerMove(event) {
      if (!previewContainer.classList.contains(VISIBLE_CLASS)) {
        return;
      }
      if (isLargeScreen()) {
        return;
      }
      if (event.pointerType === 'touch') {
        return;
      }
      positionPreview(event.currentTarget, event);
    }

    triggers.forEach(function (trigger) {
      if (supportsPointerEvents) {
        trigger.addEventListener('pointerenter', onPointerEnter);
        trigger.addEventListener('pointermove', onPointerMove);
        trigger.addEventListener('pointerleave', hidePreview);
      } else {
        trigger.addEventListener('mouseenter', function (event) {
          showPreview(event.currentTarget, event);
        });

        trigger.addEventListener('mousemove', function (event) {
          if (!previewContainer.classList.contains(VISIBLE_CLASS)) {
            return;
          }
          if (isLargeScreen()) {
            return;
          }
          positionPreview(event.currentTarget, event);
        });

        trigger.addEventListener('mouseleave', hidePreview);
      }

      trigger.addEventListener('focus', function (event) {
        showPreview(event.currentTarget, event);
      });

      trigger.addEventListener('blur', hidePreview);

      trigger.addEventListener(
        'touchstart',
        function () {
          hidePreview();
        },
        { passive: true }
      );
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' || event.key === 'Esc') {
        hidePreview();
      }
    });

    window.addEventListener(
      'scroll',
      function () {
        if (!activeTrigger) {
          return;
        }
        if (isLargeScreen()) {
          return;
        }
        positionPreview(activeTrigger);
      },
      true
    );

    window.addEventListener('resize', function () {
      if (!activeTrigger) {
        return;
      }
      if (isLargeScreen()) {
        centerPreview();
      } else {
        uncenterPreview();
        positionPreview(activeTrigger);
      }
    });

    if (largeScreenMedia) {
      var handleMediaChange = function (event) {
        if (!previewContainer.classList.contains(VISIBLE_CLASS)) {
          return;
        }

        if (event.matches) {
          centerPreview();
        } else {
          uncenterPreview();
          if (activeTrigger) {
            positionPreview(activeTrigger);
          }
        }
      };

      if (typeof largeScreenMedia.addEventListener === 'function') {
        largeScreenMedia.addEventListener('change', handleMediaChange);
      } else if (typeof largeScreenMedia.addListener === 'function') {
        largeScreenMedia.addListener(handleMediaChange);
      }
    }
  });
})();
