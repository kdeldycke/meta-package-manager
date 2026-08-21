/*
 * Manager index table: verdict group titles and whole-row links.
 *
 * The table rendered by meta_package_manager._docs.managers_index_table opens
 * each verdict group on a title row, and every manager row carries a link to
 * its own page. Neither shape survives the markdown table format on its own:
 * it has no spanning cell, and no way to hang a link on a row rather than on
 * a cell. Both are applied here instead, once the document is parsed.
 *
 * Scoped by content rather than by pathname, since the site builds with
 * `dirhtml`: the index answers to `/managers/` and each manager page to
 * `/managers/<id>/`, so no path test separates them cleanly. The table marks
 * itself instead, through the `manager-group` spans its title rows carry.
 * Styling lives in manager-index.css.
 */
(function () {
  function ready(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  function follow(row, event) {
    var href = row.getAttribute("data-href");
    if (!href) {
      return;
    }
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button === 1) {
      window.open(href, "_blank", "noopener");
    } else {
      window.location.href = href;
    }
  }

  // A click landing on a real link is that link's, and one ending a text
  // selection is the reader's: the row is a shortcut, never an interception.
  function rowFor(event) {
    if (event.target.closest("a[href]")) {
      return null;
    }
    var selection = window.getSelection();
    if (selection && selection.toString()) {
      return null;
    }
    return event.target.closest("tr.manager-row");
  }

  ready(function () {
    var tables = document.querySelectorAll("article table, main table");

    Array.prototype.forEach.call(tables, function (table) {
      if (!table.querySelector(".manager-group")) {
        return;
      }
      table.classList.add("manager-index");
      var width = table.rows[0] ? table.rows[0].cells.length : 0;

      Array.prototype.forEach.call(table.rows, function (row) {
        if (row.parentElement.tagName === "THEAD") {
          return;
        }
        var cell = row.cells[1];
        if (cell && cell.querySelector(".manager-group")) {
          // A title row is a heading, not data. Its mark column keeps the
          // state's glyph, like every row below it; the cells right of the
          // label exist only because the markdown table had to declare them,
          // so drop them and let the label span the width they occupied.
          while (row.cells.length > 2) {
            row.deleteCell(2);
          }
          cell.colSpan = width - 1;
          row.classList.add("manager-group-row");
          return;
        }
        // The ID column is the row's canonical target: a dedicated page for a
        // wrapped manager, a verdict section for a declined one.
        var link = row.cells[2] && row.cells[2].querySelector("a[href]");
        if (!link) {
          return;
        }
        row.classList.add("manager-row");
        row.setAttribute("data-href", link.href);
      });

      // Delegated, so the listener count stays at two whatever the row count.
      table.addEventListener("click", function (event) {
        var row = rowFor(event);
        if (row) {
          follow(row, event);
        }
      });

      // Middle-click opens a new tab, the way it does on a link.
      table.addEventListener("auxclick", function (event) {
        if (event.button !== 1) {
          return;
        }
        var row = rowFor(event);
        if (row) {
          event.preventDefault();
          follow(row, event);
        }
      });
    });
  });
})();
