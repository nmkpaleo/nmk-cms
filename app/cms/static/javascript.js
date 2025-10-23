document.addEventListener("DOMContentLoaded", function() {
    const navToggle = document.getElementById("nav-toggle");
    const navLinks = document.getElementById("primary-navigation");
    const dropdown = document.querySelector(".nav-dropdown");

    if (navToggle && navLinks) {
        const toggleNavigation = () => {
            const isOpen = navLinks.classList.toggle("is-open");
            navToggle.setAttribute("aria-expanded", String(isOpen));
        };

        navToggle.addEventListener("click", function(event) {
            event.preventDefault();
            toggleNavigation();
        });
    }

    if (dropdown) {
        const dropdownToggle = dropdown.querySelector(".dropdown-toggle");
        const dropdownMenu = dropdown.querySelector(".nav-dropdown-menu");

        if (dropdownToggle && dropdownMenu) {
            const closeDropdown = () => {
                dropdown.classList.remove("is-open");
                dropdownToggle.setAttribute("aria-expanded", "false");
                dropdownMenu.setAttribute("hidden", "hidden");
            };

            const openDropdown = () => {
                dropdown.classList.add("is-open");
                dropdownToggle.setAttribute("aria-expanded", "true");
                dropdownMenu.removeAttribute("hidden");
            };

            dropdownToggle.addEventListener("click", function(event) {
                event.preventDefault();
                if (dropdown.classList.contains("is-open")) {
                    closeDropdown();
                } else {
                    openDropdown();
                }
            });

            dropdownToggle.addEventListener("keydown", function(event) {
                if (event.key === "Escape") {
                    closeDropdown();
                    dropdownToggle.focus();
                }
                if (event.key === "ArrowDown") {
                    openDropdown();
                    const firstLink = dropdownMenu.querySelector("a");
                    if (firstLink) {
                        firstLink.focus();
                        event.preventDefault();
                    }
                }
            });

            dropdownMenu.addEventListener("keydown", function(event) {
                if (event.key === "Escape") {
                    closeDropdown();
                    dropdownToggle.focus();
                }
            });

            document.addEventListener("click", function(event) {
                if (!dropdown.contains(event.target)) {
                    closeDropdown();
                }
            });
        }
    }

    const toggleBtn = document.getElementById("toggleColumns");
    if (toggleBtn) {
        const hiddenColumns = document.querySelectorAll(".hidden-mobile");
        let isExpanded = false;

        toggleBtn.addEventListener("click", function() {
            hiddenColumns.forEach(col => {
                col.style.display = isExpanded ? "none" : "table-cell";
            });

            toggleBtn.textContent = isExpanded ? "Show Less" : "Show More";
            isExpanded = !isExpanded;
        });
    }
});