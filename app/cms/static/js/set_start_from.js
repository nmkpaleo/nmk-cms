document.addEventListener("DOMContentLoaded", function () {
  const userSelect = document.getElementById("id_user");
  const startFromInput = document.getElementById("id_start_from");
  const currentNumberInput = document.getElementById("id_current_number");

  if (!userSelect || !startFromInput || !currentNumberInput) return;

  const seriesData = userSelect.getAttribute("data-series-starts");
  if (!seriesData) return;

  let seriesMap;
  try {
    seriesMap = JSON.parse(seriesData);
  } catch (e) {
    console.warn("Invalid data-series-starts");
    return;
  }

  function updateFields(force = false) {
    const selectedOption = userSelect.options[userSelect.selectedIndex];
    const label = selectedOption?.textContent?.trim().toLowerCase();

    const seriesKey = label.includes("mary") ? "mary" : "shared";
    const nextStart = seriesMap[seriesKey];

    if (!nextStart) return;

    if (force || !startFromInput.value || startFromInput.value === "0") {
      startFromInput.value = nextStart;
      startFromInput.readOnly = true;
    }

    if (force || !currentNumberInput.value || currentNumberInput.value === "0") {
      currentNumberInput.value = nextStart;
      currentNumberInput.readOnly = true;
    }
  }

  userSelect.addEventListener("change", () => updateFields(true));

  const isNew = !window.location.pathname.includes("/change/");
  if (isNew) {
    updateFields();
  }
});
