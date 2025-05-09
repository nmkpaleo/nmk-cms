document.addEventListener("DOMContentLoaded", function () {
    const userSelect = document.querySelector("select[name='user']");
    const startFromInput = document.querySelector("input[name='start_from']");
    const currentNumberInput = document.querySelector("input[name='current_number']");
  
    if (!userSelect || !startFromInput || !currentNumberInput) return;
  
  
    try {
        const rawMap = userSelect.getAttribute("data-series-starts");
        if (!rawMap) {
          console.error("Missing data-series-starts attribute on user field");
          return;
        }
        const seriesMap = JSON.parse(rawMap);
          
      userSelect.addEventListener("change", function () {
        const userId = this.value;
        const nextStart = seriesMap[userId];
        if (nextStart) {
          startFromInput.value = nextStart;
          currentNumberInput.value = nextStart;
        }
      });
    } catch (e) {
      console.error("Could not parse data-series-starts:", e);
    }
  });
  