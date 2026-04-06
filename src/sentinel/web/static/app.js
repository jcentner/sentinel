// Sentinel UI — Theme toggle + toast auto-dismiss
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
