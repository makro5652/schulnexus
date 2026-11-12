/* Fehlzeiten nach Klasse (ab 0.7.1): Felder je Art ein- und ausblenden, Namensfilter, Sortieren, alle ankreuzen,
   Warnung bei ungespeicherten Eingaben. Ohne JavaScript bleiben alle Felder sichtbar und nutzbar. */
(function () {
  "use strict";
  function schlicht(t) {
    t = (t || "").toLowerCase();
    return t.normalize ? t.normalize("NFD").replace(/[̀-ͯ]/g, "") : t;
  }

  // ---- Zeilen der Eingabe: Art bestimmt, welche Angaben erscheinen ----
  var form = document.getElementById("fz-form"), zaehler = document.getElementById("fz-zaehler"), geaendert = false;
  var zeilen = form ? Array.prototype.slice.call(form.querySelectorAll("tr.fz-zeile")) : [];
  function zeileAktualisieren(tr) {
    var gewaehlt = tr.querySelector(".fz-art input:checked"), art = gewaehlt ? gewaehlt.value : "";
    tr.setAttribute("data-art", art);
    tr.classList.add("fz-js");
  }
  function zaehlen() {
    if (!zaehler) return;
    var n = zeilen.filter(function (tr) { return tr.getAttribute("data-art"); }).length;
    zaehler.textContent = n ? zaehler.getAttribute("data-text").replace("{n}", n) : "";
  }
  zeilen.forEach(function (tr) {
    zeileAktualisieren(tr);
    tr.addEventListener("change", function (e) {
      geaendert = true;
      if (e.target.name && e.target.name.indexOf("art_") === 0) {
        zeileAktualisieren(tr);
        var erstes = tr.querySelector(".fz-nur-" + e.target.value + " select, .fz-nur-" + e.target.value + " input");
        if (erstes && e.target.value !== "ganztaegig") erstes.focus();
        // Stunden: „bis“ folgt „ab“, solange es leer ist
      }
      if (e.target.name && e.target.name.indexOf("von_") === 0) {
        var bis = tr.querySelector('select[name^="bisstd_"]');
        if (bis && !bis.value) bis.value = e.target.value;
      }
      zaehlen();
    });
    tr.addEventListener("input", function (e) {           // Tippen in Minuten oder Grund wählt die passende Art mit
      var name = e.target.name || "";
      var art = name.indexOf("min_") === 0 ? "verspaetung" : "";
      if (art) {
        var radio = tr.querySelector('.fz-art input[value="' + art + '"]');
        if (radio && !radio.checked) { radio.checked = true; zeileAktualisieren(tr); zaehlen(); }
      }
      geaendert = true;
    });
  });
  if (form) {
    form.addEventListener("submit", function () { geaendert = false; });
    window.addEventListener("beforeunload", function (e) {
      if (geaendert && zeilen.some(function (tr) { return tr.getAttribute("data-art"); })) { e.preventDefault(); e.returnValue = ""; }
    });
  }

  // ---- Namensfilter und „nur mit Eintrag“ ----
  var filter = document.getElementById("fz-filter"), nurHeute = document.getElementById("fz-nur-heute");
  function filtern() {
    var q = schlicht(filter && filter.value).trim(), nur = nurHeute && nurHeute.checked;
    zeilen.forEach(function (tr) {
      var passt = (!q || schlicht(tr.getAttribute("data-name")).indexOf(q) !== -1) && (!nur || tr.classList.contains("fz-hat-eintrag"));
      tr.hidden = !passt;
    });
  }
  if (filter) {
    filter.addEventListener("input", filtern);
    filter.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { filter.value = ""; filtern(); }
      if (e.key === "Enter") {
        e.preventDefault();
        var erste = zeilen.filter(function (tr) { return !tr.hidden; })[0];
        var ziel = erste && erste.querySelector('.fz-art input[value="ganztaegig"]');
        if (ziel) ziel.focus();
      }
    });
  }
  if (nurHeute) nurHeute.addEventListener("change", filtern);

  // ---- Alle ankreuzen ----
  Array.prototype.forEach.call(document.querySelectorAll(".fz-alle"), function (alle) {
    var tabelle = alle.closest("table");
    alle.addEventListener("change", function () {
      Array.prototype.forEach.call(tabelle.querySelectorAll('tbody input[type="checkbox"]'), function (c) { c.checked = alle.checked; });
    });
  });

  // ---- Sortierbare Übersicht ----
  Array.prototype.forEach.call(document.querySelectorAll("table.fz-sortierbar"), function (tabelle) {
    var koepfe = Array.prototype.slice.call(tabelle.querySelectorAll("th[data-sort]"));
    koepfe.forEach(function (th, spalte) {
      th.tabIndex = 0;
      th.setAttribute("role", "button");
      function sortieren() {
        var abwaerts = th.getAttribute("aria-sort") !== "descending" && th.getAttribute("data-sort") === "zahl"
          ? true : th.getAttribute("aria-sort") === "ascending";
        koepfe.forEach(function (k) { k.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", abwaerts ? "descending" : "ascending");
        var tbody = tabelle.tBodies[0], reihen = Array.prototype.slice.call(tbody.rows);
        reihen.sort(function (a, b) {
          var x = a.cells[spalte].textContent.trim(), y = b.cells[spalte].textContent.trim(), r;
          r = th.getAttribute("data-sort") === "zahl" ? (parseFloat(x) || 0) - (parseFloat(y) || 0) : x.localeCompare(y, document.documentElement.lang);
          return abwaerts ? -r : r;
        });
        reihen.forEach(function (r) { tbody.appendChild(r); });
      }
      th.addEventListener("click", sortieren);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortieren(); } });
    });
  });
})();
