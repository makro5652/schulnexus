/* Zuordnung: Sofortfilter, Mehrfachauswahl (auch mit Umschalttaste), Drag & Drop, Stichtag. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // ---------------------------------------------------------- Gruppenliste filtern
  var gs = $("#zo-gruppensuche");
  if (gs) gs.addEventListener("input", function () {
    var q = gs.value.trim().toLowerCase();
    $$(".zo-gruppen li").forEach(function (li) { li.hidden = q && li.dataset.name.indexOf(q) === -1; });
  });

  // ---------------------------------------------------------- Stichtag in alle Formulare übernehmen
  var datum = $("#zo-datum");
  function datumKopieren() { $$(".zo-datum-kopie").forEach(function (h) { if (datum && datum.value) h.value = datum.value; }); }
  if (datum) datum.addEventListener("change", datumKopieren);
  $$("form").forEach(function (f) { f.addEventListener("submit", datumKopieren); });

  // ---------------------------------------------------------- Pool filtern
  var pool = $(".zo-pool");
  if (!pool) return;
  var zeilen = $$(".zo-poolzeile");
  var suche = $("#zo-suche"), jahrgang = $("#zo-jahrgang"), religion = $("#zo-religion"), drinAus = $("#zo-drin-ausblenden");
  var chips = $$(".zo-chip");
  var knopf = $("#zo-hinzu-knopf"), alleSichtbaren = $("#zo-alle-sichtbaren"), zaehler = $("#zo-sichtbar"), keine = $("#zo-keine");

  function gewaehlteKlassen() {
    return chips.filter(function (c) { return c.getAttribute("aria-pressed") === "true"; }).map(function (c) { return c.dataset.klasse; });
  }

  function filtern() {
    var q = (suche.value || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
    var klassen = gewaehlteKlassen(), jg = jahrgang.value, rel = religion.value, ohneDrin = drinAus.checked;
    var sichtbar = 0;
    zeilen.forEach(function (z) {
      var d = z.dataset;
      var ok = q.every(function (w) { return d.name.indexOf(w) !== -1; })
        && (!klassen.length || klassen.indexOf(d.klasse) !== -1)
        && (!jg || d.jahrgang === jg)
        && (!rel || d.religion === rel)
        && !(ohneDrin && d.drin === "1");
      z.hidden = !ok;
      if (ok) sichtbar++;
    });
    zaehler.textContent = sichtbar;
    keine.hidden = sichtbar > 0;
    zaehlen();
  }

  function auswahl() { return $$(".zo-auswahl:checked"); }
  function zaehlen() {
    var n = auswahl().length;
    if (knopf) {
      knopf.disabled = n === 0;
      knopf.textContent = n ? knopf.dataset.text + " (" + n + ")" : knopf.dataset.text;
    }
    var sichtbare = zeilen.filter(function (z) { return !z.hidden; }).map(function (z) { return $(".zo-auswahl", z); })
      .filter(function (c) { return !c.disabled; });
    alleSichtbaren.checked = sichtbare.length > 0 && sichtbare.every(function (c) { return c.checked; });
    zeilen.forEach(function (z) { z.classList.toggle("gewaehlt", $(".zo-auswahl", z).checked); });
  }

  [suche, jahrgang, religion, drinAus].forEach(function (el) { el.addEventListener("input", filtern); el.addEventListener("change", filtern); });
  chips.forEach(function (c) {
    c.addEventListener("click", function () { c.setAttribute("aria-pressed", c.getAttribute("aria-pressed") === "true" ? "false" : "true"); filtern(); });
  });

  alleSichtbaren.addEventListener("change", function () {
    zeilen.forEach(function (z) {
      var c = $(".zo-auswahl", z);
      if (!z.hidden && !c.disabled) c.checked = alleSichtbaren.checked;
    });
    zaehlen();
  });

  // Umschalt-Klick: Bereich auswählen
  var letzte = null;
  zeilen.forEach(function (z) {
    var c = $(".zo-auswahl", z);
    c.addEventListener("click", function (e) {
      if (e.shiftKey && letzte !== null) {
        var sichtbar = zeilen.filter(function (x) { return !x.hidden; });
        var a = sichtbar.indexOf(letzte), b = sichtbar.indexOf(z);
        if (a !== -1 && b !== -1) {
          sichtbar.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(function (x) {
            var cx = $(".zo-auswahl", x);
            if (!cx.disabled) cx.checked = c.checked;
          });
        }
      }
      letzte = z;
      zaehlen();
    });
  });

  // Taste "/" springt in die Suche
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
      e.preventDefault(); suche.focus();
    }
  });

  // ---------------------------------------------------------- Drag & Drop in die Mitgliederliste
  var ablage = $("[data-ablage]");
  var formHinzu = $("#zo-hinzu");
  zeilen.forEach(function (z) {
    z.addEventListener("dragstart", function (e) {
      var c = $(".zo-auswahl", z);
      if (c.disabled) { e.preventDefault(); return; }
      if (!c.checked) { c.checked = true; zaehlen(); }
      e.dataTransfer.effectAllowed = "copy";
      e.dataTransfer.setData("text/plain", String(auswahl().length));
    });
  });
  if (ablage && formHinzu && knopf) {
    var ziel = $("#zo-mitglieder");
    ziel.addEventListener("dragover", function (e) { e.preventDefault(); ziel.classList.add("ablegen"); });
    ziel.addEventListener("dragleave", function (e) { if (!ziel.contains(e.relatedTarget)) ziel.classList.remove("ablegen"); });
    ziel.addEventListener("drop", function (e) {
      e.preventDefault(); ziel.classList.remove("ablegen");
      if (auswahl().length) { datumKopieren(); formHinzu.requestSubmit ? formHinzu.requestSubmit() : formHinzu.submit(); }
    });
  }

  // ---------------------------------------------------------- Mitglieder: Auswahl zum Entfernen
  var alleM = $("#zo-alle-mitglieder"), entf = $("#zo-entfernen-knopf");
  function mZaehlen() {
    var n = $$(".zo-mitglied:checked").length;
    if (entf) { entf.disabled = n === 0; entf.textContent = n ? entf.dataset.text + " (" + n + ")" : entf.dataset.text; }
  }
  if (alleM) alleM.addEventListener("change", function () { $$(".zo-mitglied").forEach(function (c) { if (!c.disabled) c.checked = alleM.checked; }); mZaehlen(); });
  $$(".zo-mitglied").forEach(function (c) { c.addEventListener("change", mZaehlen); });

  // ---------------------------------------------------------- Filter merken (bleibt nach dem Hinzufügen erhalten)
  var SCHLUESSEL = "zo-filter-" + (pool.dataset.gruppe || "");
  function merken() {
    try {
      window.sessionStorage.setItem(SCHLUESSEL, JSON.stringify({
        q: suche.value, k: gewaehlteKlassen(), j: jahrgang.value, r: religion.value, d: drinAus.checked }));
    } catch (e) { /* ohne Speicher */ }
  }
  function gemerkt() {
    try { return JSON.parse(window.sessionStorage.getItem(SCHLUESSEL) || "null"); } catch (e) { return null; }
  }
  [suche, jahrgang, religion, drinAus].forEach(function (el) { el.addEventListener("change", merken); el.addEventListener("input", merken); });
  chips.forEach(function (c) { c.addEventListener("click", merken); });

  // ---------------------------------------------------------- Voreinstellung der Filter
  var f = gemerkt();
  if (f) {
    suche.value = f.q || ""; jahrgang.value = f.j || ""; religion.value = f.r || ""; drinAus.checked = f.d !== false;
    chips.forEach(function (c) { c.setAttribute("aria-pressed", (f.k || []).indexOf(c.dataset.klasse) !== -1 ? "true" : "false"); });
  } else {
    var vk = (pool.dataset.vorfilterKlassen || "").split(",").filter(Boolean);
    chips.forEach(function (c) {
      if (vk.indexOf(c.dataset.klasse) !== -1 || (pool.dataset.vorfilterOhne === "1" && c.dataset.klasse === "ohne")) c.setAttribute("aria-pressed", "true");
    });
    if (pool.dataset.vorfilterReligion) religion.value = pool.dataset.vorfilterReligion;
  }
  filtern();
})();
