  function calculateAverage(row) {
    const qInput = row.querySelector('input[name*="[rating_q]"]');
    const eInput = row.querySelector('input[name*="[rating_e]"]');
    const tInput = row.querySelector('input[name*="[rating_t]"]');
    const aInput = row.querySelector('input[name*="[rating_a]"]');

    const q = parseFloat(qInput?.value) || 0;
    const e = parseFloat(eInput?.value) || 0;
    const t = parseFloat(tInput?.value) || 0;

    const average = Math.floor(((q + e + t) / 3) * 100) / 100;
    if (aInput) aInput.value = average;
  }

  document.querySelectorAll('tbody tr').forEach(row => {
    const qInput = row.querySelector('input[name*="[rating_q]"]');
    const eInput = row.querySelector('input[name*="[rating_e]"]');
    const tInput = row.querySelector('input[name*="[rating_t]"]');

    if (qInput && eInput && tInput) {
      [qInput, eInput, tInput].forEach(input => {
        input.addEventListener('input', () => calculateAverage(row));
      });

      // Initial calculation on page load
      calculateAverage(row);
    }
  });
