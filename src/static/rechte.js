/* Benutzer und Rechte (ab 0.6.0): Konten gesammelt auswählen und ändern; Einzelrechte durchsuchen und filtern. */
(function () {
  "use strict";

  // ---- Kontenliste: alle angezeigten auswählen, Sammelaktion ----
  var sammel = document.getElementById("sy-sammel");
  if (sammel) {
    var alle = document.getElementById("sy-alle"), anzahl = document.getElementById("sy-anzahl"),
      aktion = document.getElementById("sy-aktion"), rollenwahl = document.getElementById("sy-rollenwahl"),
      knopf = document.getElementById("sy-anwenden");
    var konten = Array.prototype.slice.call(sammel.querySelectorAll(".sy-konto"));
    var stand = function () {
      var n = konten.filter(function (k) { return k.checked; }).length;
      if (anzahl) anzahl.textContent = n ? anzahl.getAttribute("data-text").replace("{n}", n) : "";
      if (alle) { alle.checked = n > 0 && n === konten.length; alle.indeterminate = n > 0 && n < konten.length; }
      var wahl = aktion.options[aktion.selectedIndex];
      if (rollenwahl) rollenwahl.hidden = !(wahl && wahl.getAttribute("data-rolle"));
      if (knopf) knopf.disabled = !n || !aktion.value;
      konten.forEach(function (k) { k.closest("tr").classList.toggle("sy-gewaehlt", k.checked); });
    };
    if (alle) alle.addEventListener("change", function () { konten.forEach(function (k) { k.checked = alle.checked; }); stand(); });
    var letztes = null;
    konten.forEach(function (k, i) {
      k.addEventListener("click", function (e) {           // Umschalt+Klick wählt den Bereich dazwischen
        if (e.shiftKey && letztes !== null) {
          var von = Math.min(letztes, i), bis = Math.max(letztes, i), j;
          for (j = von; j <= bis; j++) konten[j].checked = k.checked;
        }
        letztes = i;
        stand();
      });
    });
    aktion.addEventListener("change", stand);
    sammel.addEventListener("submit", function (e) {
      if (!window.confirm(sammel.getAttribute("data-frage"))) e.preventDefault();
    });
    stand();
  }

  // ---- Einzelrechte: Suche, nur Abweichungen, alle auf-/zuklappen ----
  var formular = document.getElementById("sy-rechteform");
  if (formular) {
    var suche = document.getElementById("sy-rechtesuche"), nur = document.getElementById("sy-nur-abweichungen"),
      treffer = document.getElementById("sy-rechtetreffer");
    var bereiche = Array.prototype.slice.call(formular.querySelectorAll("details.sy-app"));
    var schlicht = function (t) {
      t = (t || "").toLowerCase();
      return t.normalize ? t.normalize("NFD").replace(/[̀-ͯ]/g, "") : t;
    };
    var filtern = function () {
      var q = schlicht(suche && suche.value).trim(), abw = nur && nur.checked, gesamt = 0;
      bereiche.forEach(function (b) {
        var titel = schlicht(b.querySelector("summary").textContent), sichtbar = 0;
        Array.prototype.forEach.call(b.querySelectorAll("tbody tr"), function (zeile) {
          var text = schlicht(zeile.querySelector("th").textContent);
          var wahlen = Array.prototype.slice.call(zeile.querySelectorAll("select"));
          var passt = (!q || text.indexOf(q) !== -1 || titel.indexOf(q) !== -1)
            && (!abw || wahlen.some(function (w) { return w.value !== ""; }));
          zeile.hidden = !passt;
          if (passt) { sichtbar++; gesamt += wahlen.length; }
        });
        b.hidden = !sichtbar;
        if (q || abw) b.open = sichtbar > 0;
      });
      if (treffer) treffer.textContent = (q || abw) ? treffer.getAttribute("data-text").replace("{n}", gesamt) : "";
    };
    if (suche) suche.addEventListener("input", filtern);
    if (nur) nur.addEventListener("change", filtern);
    var auf = document.getElementById("sy-alle-auf"), zu = document.getElementById("sy-alle-zu");
    if (auf) auf.addEventListener("click", function () { bereiche.forEach(function (b) { b.open = true; }); });
    if (zu) zu.addEventListener("click", function () { bereiche.forEach(function (b) { b.open = false; }); });
    formular.addEventListener("change", function (e) {       // Farbe der Auswahl sofort anpassen
      var w = e.target;
      if (!w.classList || !w.classList.contains("sy-wahl")) return;
      w.classList.toggle("sy-wahl-plus", w.value === "+");
      w.classList.toggle("sy-wahl-minus", w.value === "-");
    });
  }
})();
