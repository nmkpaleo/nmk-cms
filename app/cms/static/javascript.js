document.addEventListener("DOMContentLoaded", function() {
    const navToggle = document.getElementById("nav-toggle");
    const mobileNav = document.getElementById("primary-navigation");

    if (navToggle && mobileNav) {
        const setCollapsedState = (isOpen) => {
            mobileNav.setAttribute("data-collapsed", isOpen ? "false" : "true");
            navToggle.setAttribute("aria-expanded", String(isOpen));
        };

        const toggleNavigation = () => {
            const isOpen = mobileNav.classList.toggle("w3-show");
            if (isOpen) {
                mobileNav.classList.remove("w3-hide");
            } else {
                mobileNav.classList.add("w3-hide");
            }
            setCollapsedState(isOpen);
        };

        navToggle.addEventListener("click", function(event) {
            event.preventDefault();
            toggleNavigation();
        });
    }

    document.querySelectorAll("[data-dropdown-toggle]").forEach((dropdownToggle) => {
        const menuId = dropdownToggle.getAttribute("data-dropdown-toggle");
        if (!menuId) {
            return;
        }

        const dropdownMenu = document.getElementById(menuId);
        if (!dropdownMenu) {
            return;
        }

        const dropdownContainer = dropdownToggle.closest("[data-dropdown]");

        const closeDropdown = () => {
            dropdownMenu.classList.remove("w3-show");
            dropdownMenu.setAttribute("hidden", "hidden");
            dropdownToggle.setAttribute("aria-expanded", "false");
            if (dropdownContainer) {
                dropdownContainer.classList.remove("is-open");
            }
        };

        const openDropdown = () => {
            dropdownMenu.classList.add("w3-show");
            dropdownMenu.removeAttribute("hidden");
            dropdownToggle.setAttribute("aria-expanded", "true");
            if (dropdownContainer) {
                dropdownContainer.classList.add("is-open");
            }
        };

        dropdownToggle.addEventListener("click", function(event) {
            event.preventDefault();
            if (dropdownMenu.classList.contains("w3-show")) {
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
            if (!dropdownContainer || dropdownContainer.contains(event.target)) {
                return;
            }
            closeDropdown();
        });
    });

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