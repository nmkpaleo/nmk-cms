document.addEventListener("DOMContentLoaded", function() {
    const siteHeader = document.querySelector(".site-header");
    const siteNavigation = document.querySelector(".site-navigation");
    const navToggle = document.getElementById("nav-toggle");
    const mobileNav = document.getElementById("primary-navigation");

    const updateHeaderHeight = () => {
        if (!siteHeader) {
            return;
        }
        document.documentElement.style.setProperty(
            "--site-header-height",
            `${Math.ceil(siteHeader.getBoundingClientRect().height)}px`
        );
    };

    const setOpenDropdownSpace = (dropdownMenu) => {
        if (!siteNavigation) {
            return;
        }
        const menuHeight = Math.ceil(dropdownMenu.getBoundingClientRect().height);
        siteNavigation.style.setProperty("--open-dropdown-space", `${menuHeight + 8}px`);
    };

    const clearOpenDropdownSpace = () => {
        if (!siteNavigation) {
            return;
        }
        siteNavigation.style.removeProperty("--open-dropdown-space");
    };

    const refreshOpenDropdownSpace = () => {
        if (!siteNavigation || !siteNavigation.classList.contains("has-open-dropdown")) {
            return;
        }
        const openDropdown = siteNavigation.querySelector(".nav-dropdown .w3-dropdown-content.w3-show");
        if (openDropdown) {
            setOpenDropdownSpace(openDropdown);
        }
    };

    const queueHeaderHeightUpdate = () => {
        window.requestAnimationFrame(() => {
            refreshOpenDropdownSpace();
            updateHeaderHeight();
        });
    };

    updateHeaderHeight();
    window.addEventListener("load", queueHeaderHeightUpdate);
    window.addEventListener("resize", queueHeaderHeightUpdate);

    const closeFloatingFieldMenus = () => {
        const select2jQuery = window.jQuery || (window.django && window.django.jQuery);
        if (select2jQuery && select2jQuery.fn && select2jQuery.fn.select2) {
            select2jQuery(".select2-hidden-accessible").each(function() {
                const field = select2jQuery(this);
                if (field.data("select2")) {
                    field.select2("close");
                }
            });
        }

        document.querySelectorAll(".select2-container--open").forEach((container) => {
            container.classList.remove("select2-container--open");
        });
        document.querySelectorAll(".select2-dropdown, .ui-autocomplete, .tt-menu").forEach((menu) => {
            menu.setAttribute("aria-hidden", "true");
            menu.style.display = "none";
        });
    };

    let scrollCloseQueued = false;
    window.addEventListener("scroll", () => {
        if (scrollCloseQueued) {
            return;
        }
        scrollCloseQueued = true;
        window.requestAnimationFrame(() => {
            closeFloatingFieldMenus();
            scrollCloseQueued = false;
        });
    }, true);

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
            updateHeaderHeight();
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
            if (siteNavigation) {
                siteNavigation.classList.remove("has-open-dropdown");
            }
            clearOpenDropdownSpace();
            queueHeaderHeightUpdate();
        };

        const openDropdown = () => {
            dropdownMenu.classList.add("w3-show");
            dropdownMenu.removeAttribute("hidden");
            dropdownToggle.setAttribute("aria-expanded", "true");
            if (dropdownContainer) {
                dropdownContainer.classList.add("is-open");
            }
            if (siteNavigation) {
                siteNavigation.classList.add("has-open-dropdown");
            }
            window.requestAnimationFrame(() => {
                setOpenDropdownSpace(dropdownMenu);
                updateHeaderHeight();
            });
            queueHeaderHeightUpdate();
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
            if (dropdownContainer && !dropdownContainer.contains(event.target)) {
                closeDropdown();
            }
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
