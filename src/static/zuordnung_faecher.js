/* Fächer und Lehrkräfte: Fachsuche, nur belegte Fächer, 1. → 2. Halbjahr übernehmen, geänderte Felder markieren. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var form = $("#zo-faecherform");
  if (!form) return;
  var zeilen = $$(".zo-fachzeile"), suche = $("#zo-fachsuche"), nurBelegt = $("#zo-nur-belegt"), keine = $("#zo-keine-faecher");
  var geaendert = false;

  function filtern() {
    var q = (suche.value || "").trim().toLowerCase(), sichtbar = 0;
    zeilen.forEach(function (z) {
      var belegt = z.dataset.belegt || $$("select", z).some(function (s) { return s.value; });
      z.hidden = !!((q && z.dataset.name.indexOf(q) === -1) || (!q && nurBelegt.checked && !belegt));
      if (!z.hidden) sichtbar++;
    });
    keine.hidden = sichtbar > 0;
  }

  function markieren(sel) {
    var vorher = form.querySelector('input[name="vorher_' + sel.name + '"]');
    sel.classList.toggle("geaendert", !!vorher && vorher.value !== sel.value);
    geaendert = $$("select.geaendert", form).length > 0;
  }

  // Wahl im 1. Halbjahr füllt das noch leere 2. Halbjahr gleich mit
  $$("select.zo-lehrkraft", form).forEach(function (sel) {
    sel.addEventListener("change", function () {
      if (sel.dataset.nummer === "1" && sel.value) {
        var zwei = form.querySelector('select[data-fach="' + sel.dataset.fach + '"][data-nummer="2"]');
        if (zwei && !zwei.value) { zwei.value = sel.value; markieren(zwei); }
      }
      markieren(sel);
    });
  });

  var kopieren = $("#zo-hj-kopieren");
  if (kopieren) kopieren.addEventListener("click", function () {
    $$('select[data-nummer="1"]', form).forEach(function (eins) {
      var zwei = form.querySelector('select[data-fach="' + eins.dataset.fach + '"][data-nummer="2"]');
      if (eins.value && zwei && !zwei.value) { zwei.value = eins.value; markieren(zwei); }
    });
  });

  suche.addEventListener("input", filtern);
  nurBelegt.addEventListener("change", filtern);
  form.addEventListener("submit", function () { geaendert = false; });
  window.addEventListener("beforeunload", function (e) { if (geaendert) { e.preventDefault(); e.returnValue = ""; } });
  filtern();
})();
