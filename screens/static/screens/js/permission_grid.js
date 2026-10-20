/*
 * Permission grid: tick the boxes a ticked box needs.
 *
 * Edit needs View of the same row, and Screens → Edit needs the estate
 * directory for its room picker. Each checkbox lists every box it needs in
 * data-implies (computed server-side from the catalogue), and the server adds
 * them on save regardless — this only makes the form show what saving will do.
 * A needed box cannot be unticked while the box needing it stays ticked.
 */
(function () {
    "use strict";

    function refresh(grid) {
        var boxes = grid.querySelectorAll('input[type="checkbox"]');
        var byValue = {};
        boxes.forEach(function (box) {
            byValue[box.value] = box;
            box.removeAttribute("data-required-by");
            box.removeAttribute("title");
        });
        boxes.forEach(function (box) {
            if (!box.checked) {
                return;
            }
            (box.dataset.implies || "").split(" ").forEach(function (key) {
                var needed = byValue[key];
                if (!needed) {
                    return;
                }
                needed.checked = true;
                needed.setAttribute("data-required-by", box.getAttribute("aria-label") || box.value);
                needed.title = "Needed by " + needed.getAttribute("data-required-by");
            });
        });
    }

    function init() {
        document.querySelectorAll("[data-permission-grid]").forEach(function (grid) {
            grid.addEventListener("change", function () {
                refresh(grid);
            });
            refresh(grid);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
