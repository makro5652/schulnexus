/* Bearbeitbare Notentabelle „Noten nach Klasse“ (ab 0.4.12.0):
   Enter/Pfeil ab → nächste Zeile, Pfeil auf → vorige Zeile; geänderte Zellen markieren; ungültige Eingaben kennzeichnen;
   Warnung beim Verlassen mit ungespeicherten Änderungen.
   Ab 0.4.17.0: Gewichte im Spaltenkopf und Zeugnisnoten zählen mit; nach „+ Spalte“ steht der Cursor in der neuen Spalte. */
(function () {
  "use strict";
  var form = document.getElementById("nk-form");
  if (!form) return;
  var erlaubt = {};
  try {
    JSON.parse(document.getElementById("nk-erlaubt").textContent).forEach(function (b) { erlaubt[norm(b)] = true; });
  } catch (e) { /* ohne Liste keine Vorprüfung */ }
  var status = ["e", "en", "ent", "entsch", "u", "un", "unent", "b", "bef", "befreit", "nb", "n.b.", "n.b"];
  var zaehler = document.getElementById("nk-zaehler");
  var gesendet = false;

  function norm(t) {
    return (t || "").trim().toLowerCase().replace(/[−–—]/g, "-").replace(/\s+/g, "");
  }
  function gueltig(t) {
    var n = norm(t);
    if (!n || erlaubt[n] || status.indexOf(n) >= 0) return true;
    if (n.charAt(0) === "u" && erlaubt[n.slice(1).replace(/^:/, "")]) return true;
    if (n.charAt(0) === "=" && erlaubt[n.slice(1)]) return true;
    return Object.keys(erlaubt).length === 0;
  }
  var felder = Array.prototype.slice.call(form.querySelectorAll("input[type=text][data-orig]"));

  function zeichnen(f) {
    var geaendert = norm(f.value) !== norm(f.dataset.orig);
    f.classList.toggle("geaendert", geaendert);
    f.classList.toggle("ungueltig", !gueltig(f.value));
    f.setAttribute("aria-invalid", gueltig(f.value) ? "false" : "true");
  }
  var gewichte = Array.prototype.slice.call(form.querySelectorAll("input[data-gewicht]"));
  var zeugnis = Array.prototype.slice.call(form.querySelectorAll("select[data-zn]"));
  function anders(f) {
    if (f.dataset.gewicht !== undefined) return norm(f.value) !== norm(f.dataset.gewicht);
    if (f.dataset.zn !== undefined) return f.value !== f.dataset.zn;
    return norm(f.value) !== norm(f.dataset.orig);
  }
  function zaehlen() {
    var n = felder.concat(gewichte, zeugnis).filter(anders).length;
    if (zaehler) zaehler.textContent = n ? (form.dataset.zaehler || "%n").replace("%n", n) : "";
    return n;
  }
  function nachbar(f, schritt) {
    var zelle = f.closest("td"), zeile = zelle.parentElement;
    var spalte = Array.prototype.indexOf.call(zeile.children, zelle);
    var z = zeile;
    for (;;) {
      z = schritt > 0 ? z.nextElementSibling : z.previousElementSibling;
      if (!z) return null;
      var ziel = z.children[spalte] && z.children[spalte].querySelector("input[type=text]");
      if (ziel) return ziel;
    }
  }
  felder.forEach(function (f) {
    zeichnen(f);
    f.addEventListener("input", function () { zeichnen(f); zaehlen(); });
    f.addEventListener("focus", function () { f.select(); });
    f.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        var ziel = nachbar(f, e.key === "ArrowUp" ? -1 : 1);
        if (ziel) ziel.focus();
      }
    });
  });
  gewichte.concat(zeugnis).forEach(function (f) {
    var markieren = function () { f.classList.toggle("geaendert", anders(f)); zaehlen(); };
    f.addEventListener("input", markieren);
    f.addEventListener("change", markieren);
    if (f.tagName === "INPUT") {
      f.addEventListener("focus", function () { f.select(); });
      f.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); f.blur(); } });
    }
  });
  // nach „+ Spalte“: erste Zelle der neuen Spalte
  var neu = form.querySelector("th.nk-neu-spalte");
  if (neu) {
    var index = Array.prototype.indexOf.call(neu.parentElement.children, neu) + 1;
    var zeile = form.querySelector("tbody tr");
    var ziel = zeile && zeile.children[index] && zeile.children[index].querySelector("input[type=text]");
    if (ziel) window.addEventListener("load", function () {
      ziel.scrollIntoView({ block: "center", inline: "center" });
      ziel.focus();
    });
  }
  form.addEventListener("submit", function () { gesendet = true; });
  window.addEventListener("beforeunload", function (e) {
    if (!gesendet && zaehlen()) { e.preventDefault(); e.returnValue = form.dataset.verlassen || ""; }
  });
  zaehlen();
})();
