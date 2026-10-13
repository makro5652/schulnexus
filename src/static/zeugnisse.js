/* Zeugnisse: Vorschlagsmarkierung entfernen, sobald eine Note bewusst gewählt wird; Zeichenzähler; Warnung vor Verlassen. */
(function () {
  "use strict";
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var geaendert = false;
  $$("select.zg-wahl").forEach(function (sel) {
    sel.addEventListener("change", function () { sel.classList.remove("vorschlag"); geaendert = true; });
  });
  $$("input.zg-begruendung").forEach(function (i) { i.addEventListener("input", function () { geaendert = true; }); });
  var form = document.getElementById("noten-form");
  if (form) form.addEventListener("submit", function () { geaendert = false; });
  window.addEventListener("beforeunload", function (e) { if (geaendert) { e.preventDefault(); e.returnValue = ""; } });

  $$("textarea[data-zaehler]").forEach(function (t) {
    var ziel = document.getElementById(t.dataset.zaehler);
    function zaehlen() { if (ziel) ziel.textContent = t.value.length; }
    t.addEventListener("input", zaehlen);
    zaehlen();
  });
  // Anmerkungsfelder wachsen mit
  $$(".zg-anmerken textarea").forEach(function (t) {
    t.addEventListener("input", function () { t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; });
  });
})();
