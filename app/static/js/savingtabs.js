document.addEventListener('DOMContentLoaded', function () {
  const tabButtons = document.querySelectorAll('button[data-bs-toggle="tab"]');

  // Save the clicked tab ID
  tabButtons.forEach(button => {
    button.addEventListener('shown.bs.tab', function (e) {
      localStorage.setItem('activeTabId', e.target.id);
    });
  });

  // Get saved tab ID from localStorage
  const activeTabId = localStorage.getItem('activeTabId');
  const savedTab = activeTabId ? document.getElementById(activeTabId) : null;

  if (savedTab) {
    new bootstrap.Tab(savedTab).show(); // Show saved tab
  } else if (tabButtons.length > 0) {
    new bootstrap.Tab(tabButtons[0]).show(); // Fallback: show the first tab
  }
});
