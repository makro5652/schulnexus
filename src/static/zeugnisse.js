/* Zeugnisse: Vorschlagsmarkierung entfernen, sobald eine Note bewusst gewählt wird; Zeichenzähler; Warnung vor Verlassen. */
(function () {
  "use strict";
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var geaendert = false;
  // Abweichung vom gerundeten Vorschlag sofort farbig markieren (keine Begründungspflicht)
  function abweichung(sel) {
    var ziel = sel.dataset.ziel, wert = sel.value, zeile = sel.closest("tbody");
    var weicht = !!(ziel && wert && wert !== "nb" && wert !== "befreit" && wert !== ziel);
    if (zeile) zeile.classList.toggle("zg-abweichung", weicht);
  }
  $$("select.zg-wahl").forEach(function (sel) {
    sel.addEventListener("change", function () { sel.classList.remove("vorschlag"); geaendert = true; abweichung(sel); });
    abweichung(sel);
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
  // Textbausteine an der Schreibmarke einfügen (ab 0.4.16.0)
  var kommentar = document.querySelector("textarea[name=kommentar]");
  var benutzt = false;     // ohne Klick ins Feld kommt der Baustein ans Ende
  if (kommentar) ["focus", "click", "keyup"].forEach(function (ev) { kommentar.addEventListener(ev, function () { benutzt = true; }); });
  $$(".zg-baustein").forEach(function (b) {
    b.addEventListener("click", function () {
      if (!kommentar) return;
      var v = kommentar.value, a = benutzt ? kommentar.selectionStart : v.length, e = benutzt ? kommentar.selectionEnd : v.length;
      var vorher = v.slice(0, a), nachher = v.slice(e), text = b.dataset.text;
      if (vorher && !/\s$/.test(vorher)) text = " " + text;
      if (nachher && !/^\s/.test(nachher)) text = text + " ";
      kommentar.value = vorher + text + nachher;
      kommentar.selectionStart = kommentar.selectionEnd = (vorher + text).length;
      kommentar.focus();
      kommentar.dispatchEvent(new Event("input"));
    });
  });
  // Anmerkungsfelder wachsen mit
  $$(".zg-anmerken textarea").forEach(function (t) {
    t.addEventListener("input", function () { t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; });
  });
})();
