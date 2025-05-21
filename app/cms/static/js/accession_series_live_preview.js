// static/js/accession_series_live_preview.js
document.addEventListener("DOMContentLoaded", function () {
  const startFromInput = document.querySelector("#id_start_from");
  const countInput = document.querySelector("#id_count");
  const previewDiv = document.createElement("div");
  previewDiv.classList.add("help", "live-preview");

  const insertAfter = (el, newEl) => el.parentNode.insertBefore(newEl, el.nextSibling);
  insertAfter(countInput, previewDiv);

  function updatePreview() {
    const start = parseInt(startFromInput.value);
    const count = parseInt(countInput.value);

    if (!isNaN(start) && !isNaN(count) && count > 0) {
      const end = start + count - 1;
      previewDiv.textContent = `🔢 This will generate ${count} accession(s): from ${start} to ${end}`;
    } else {
      previewDiv.textContent = "";
    }
  }

  startFromInput.addEventListener("input", updatePreview);
  countInput.addEventListener("input", updatePreview);

  updatePreview(); // init on load
});
