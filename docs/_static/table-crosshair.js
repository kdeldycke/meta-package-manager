/*
 * Crosshair hover highlight for the wide comparison tables on the benchmark,
 * SBOM, cooldown and augmentations pages.
 *
 * On pointer-over of any cell, highlights that cell's whole row and whole
 * column (including the column header and the row label), plus the cell
 * itself, so a reader can trace an entry back to its (feature, tool) pair
 * without counting columns. Styling lives in table-crosshair.css.
 *
 * Scoped by pathname to those pages so it never touches tables elsewhere.
 * Every table on them is a plain grid (no colspan/rowspan), so cellIndex maps
 * cleanly to a visual column.
 */
(function () {
  function ready(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  ready(function () {
    // Both URL shapes, since the site builds with `dirhtml`: a page answers
    // to `/benchmark/` today and answered to `/benchmark.html` until the
    // builder changed under it.
    if (
      !/\/(augmentations|benchmark|cooldown|sbom)(\.html?)?\/?$/.test(
        window.location.pathname
      )
    ) {
      return;
    }

    var tables = document.querySelectorAll("article table, main table");

    Array.prototype.forEach.call(tables, function (table) {
      // Mark cells whose entire content is a single link, so the CSS can
      // stretch that link across the whole cell (full-cell click target).
      // Cells mixing a link with other text (like the "purl support" feature
      // label, or a header's footnote marker) are left alone.
      Array.prototype.forEach.call(table.querySelectorAll("td, th"), function (cell) {
        var links = cell.querySelectorAll("a[href]");
        if (
          links.length === 1 &&
          cell.textContent.trim() === links[0].textContent.trim()
        ) {
          cell.classList.add("linked-cell");
        }
      });

      function clear() {
        var marked = table.querySelectorAll(
          ".crosshair-col, .crosshair-row, .crosshair-cell"
        );
        Array.prototype.forEach.call(marked, function (el) {
          el.classList.remove("crosshair-col", "crosshair-row", "crosshair-cell");
        });
      }

      table.addEventListener("mouseover", function (event) {
        var cell = event.target.closest("td, th");
        if (!cell || !table.contains(cell)) {
          return;
        }
        var col = cell.cellIndex;
        clear();
        // Column: the cell at the same index in every row (header included).
        Array.prototype.forEach.call(table.rows, function (row) {
          var colCell = row.cells[col];
          if (colCell) {
            colCell.classList.add("crosshair-col");
          }
        });
        // Row and the intersection cell.
        cell.parentElement.classList.add("crosshair-row");
        cell.classList.add("crosshair-cell");
      });

      table.addEventListener("mouseleave", clear);
    });
  });
})();
