function toggleMenu() {
    let sidebar = document.querySelector('.sidebar-nav');
    let hero_section_container = document.querySelector('.col-sm-10'); // Adjust if needed

    sidebar.classList.toggle('active');
    hero_section_container.classList.toggle('shifted');
}

/* Show more function */
document.addEventListener("DOMContentLoaded", function() {
    let toggleBtn = document.getElementById("toggleColumns");
    let hiddenColumns = document.querySelectorAll(".hidden-mobile");
    let isExpanded = false;

    toggleBtn.addEventListener("click", function() {
        hiddenColumns.forEach(col => {
            col.style.display = isExpanded ? "none" : "table-cell";
        });

        toggleBtn.textContent = isExpanded ? "Show More" : "Show Less";
        isExpanded = !isExpanded;
    });
});