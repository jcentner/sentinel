// Sentinel UI — Theme toggle + toast auto-dismiss + bulk actions
(function() {
  'use strict';

  function getTheme() {
    return localStorage.getItem('sentinel-theme') || 'dark';
  }

  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('sentinel-theme', theme);
  }

  window.toggleTheme = function() {
    setTheme(getTheme() === 'dark' ? 'light' : 'dark');
  };

  // ── Bulk selection ──────────────────────────────────────────────

  window.updateBulkCount = function() {
    var checks = document.querySelectorAll('.bulk-checkbox:checked');
    var bar = document.getElementById('bulk-bar');
    var countEl = document.getElementById('bulk-count');
    if (!bar) return;
    if (checks.length > 0) {
      bar.style.display = '';
      countEl.textContent = checks.length + ' selected';
    } else {
      bar.style.display = 'none';
    }
  };

  window.toggleGroup = function(toggle, severity) {
    var boxes = document.querySelectorAll('.bulk-checkbox.severity-' + severity);
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].checked = toggle.checked;
    }
    window.updateBulkCount();
  };

  window.submitBulk = function(action) {
    var input = document.getElementById('bulk-action-input');
    var form = document.getElementById('bulk-form');
    if (!input || !form) return;
    input.value = action;
    // Trigger htmx submission
    if (window.htmx) {
      htmx.trigger(form, 'submit');
    } else {
      form.submit();
    }
  };

  // Reload page after bulk action completes (htmx event)
  document.addEventListener('bulkActionComplete', function() {
    setTimeout(function() { window.location.reload(); }, 600);
  });

  // Auto-dismiss toasts after 4 seconds
  function observeToasts() {
    var container = document.getElementById('toast-container');
    if (!container) return;
    new MutationObserver(function(mutations) {
      mutations.forEach(function(m) {
        m.addedNodes.forEach(function(node) {
          if (node.nodeType === 1 && node.classList.contains('toast')) {
            setTimeout(function() {
              node.style.animation = 'toast-out 0.3s ease forwards';
              setTimeout(function() { node.remove(); }, 300);
            }, 4000);
          }
        });
      });
    }).observe(container, { childList: true });
  }

  document.addEventListener('DOMContentLoaded', observeToasts);
})();
