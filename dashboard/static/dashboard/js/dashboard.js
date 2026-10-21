"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const filterInput = document.querySelector("[data-table-filter]");
    const tableBody = document.querySelector("[data-filter-table]");

    if (!filterInput || !tableBody) {
        return;
    }

    const rows = Array.from(
        tableBody.querySelectorAll("[data-filter-row]")
    );
    const emptyState = tableBody.querySelector("[data-filter-empty]");

    function filterRows() {
        const query = filterInput.value.trim().toLocaleLowerCase();
        let visibleCount = 0;

        rows.forEach((row) => {
            const matches = row.textContent
                .toLocaleLowerCase()
                .includes(query);

            row.hidden = !matches;

            if (matches) {
                visibleCount += 1;
            }
        });

        if (emptyState) {
            emptyState.hidden = visibleCount > 0;
        }
    }

    filterInput.addEventListener("input", filterRows);
});