document.addEventListener("DOMContentLoaded", function () {
  const userSelect = document.getElementById("id_user");
  const startFromInput = document.getElementById("id_start_from");
  const currentNumberInput = document.getElementById("id_current_number");
  const organisationSelect = document.getElementById("id_organisation");

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

  const dedicatedUserId = userSelect.getAttribute("data-dedicated-user-id");
  const tbiOrganisationId = userSelect.getAttribute("data-tbi-org-id");

  function determineSeriesKey(selectedOption) {
    const selectedOrganisation = organisationSelect?.value;

    if (
      tbiOrganisationId &&
      selectedOrganisation &&
      String(selectedOrganisation) === String(tbiOrganisationId)
    ) {
      return "tbi";
    }

    if (selectedOption) {
      const optionOrganisation = selectedOption.dataset?.organisation;
      if (
        tbiOrganisationId &&
        optionOrganisation &&
        String(optionOrganisation) === String(tbiOrganisationId)
      ) {
        return "tbi";
      }

      const selectedValue = selectedOption.value;
      if (
        dedicatedUserId !== null &&
        dedicatedUserId !== undefined &&
        dedicatedUserId !== "" &&
        selectedValue !== undefined &&
        selectedValue !== null &&
        selectedValue !== "" &&
        String(selectedValue) === String(dedicatedUserId)
      ) {
        return "tbi";
      }

      const label = selectedOption.textContent?.trim().toLowerCase();
      if (label && label.includes("tbi")) {
        return "tbi";
      }
    }

    return "shared";
  }

  function dispatchInputEvent(element) {
    if (!element) return;

    element.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function updateFields(force = false) {
    const selectedOption = userSelect.options[userSelect.selectedIndex];

    const seriesKey = determineSeriesKey(selectedOption);
    const nextStart = seriesMap[seriesKey];

    if (!nextStart) return;

    const nextStartValue = String(nextStart);
    let startValueChanged = false;

    if (force || !startFromInput.value || startFromInput.value === "0") {
      startValueChanged = startFromInput.value !== nextStartValue;
      startFromInput.value = nextStartValue;
      startFromInput.readOnly = true;
    }

    if (force || !currentNumberInput.value || currentNumberInput.value === "0") {
      currentNumberInput.value = nextStartValue;
      currentNumberInput.readOnly = true;
    }

    if (startValueChanged) {
      dispatchInputEvent(startFromInput);
    }
  }

  userSelect.addEventListener("change", () => updateFields(true));

  const isNew = !window.location.pathname.includes("/change/");
  if (isNew) {
    updateFields();
  }
});
