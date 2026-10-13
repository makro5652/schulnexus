/* Menüband: Registerkarten umschalten, einklappen (im Browser gemerkt), Tastaturbedienung. */
(function () {
  "use strict";
  var mb = document.getElementById("menueband");
  if (!mb) return;
  var reiter = Array.prototype.slice.call(mb.querySelectorAll('[role="tab"]'));
  var knopf = mb.querySelector(".mb-einklappen");
  var SCHLUESSEL = "menueband-eingeklappt";

  function lesen() { try { return window.localStorage.getItem(SCHLUESSEL) === "1"; } catch (e) { return false; } }
  function schreiben(wert) { try { window.localStorage.setItem(SCHLUESSEL, wert ? "1" : "0"); } catch (e) { /* ohne Speicher */ } }

  function zeigen(tab, fokus) {
    reiter.forEach(function (t) {
      var aktiv = t === tab;
      t.setAttribute("aria-selected", aktiv ? "true" : "false");
      t.tabIndex = aktiv ? 0 : -1;
      var band = document.getElementById(t.getAttribute("aria-controls"));
      if (band) band.hidden = !aktiv;
    });
    if (fokus) tab.focus();
  }

  function einklappen(wert, merken) {
    mb.classList.toggle("eingeklappt", wert);
    mb.classList.remove("offen");
    if (knopf) {
      knopf.setAttribute("aria-expanded", wert ? "false" : "true");
      var text = wert ? knopf.dataset.textEin : knopf.dataset.textAus;
      knopf.title = text;
      var span = knopf.querySelector(".mb-unsichtbar");
      if (span) span.textContent = text;
    }
    if (merken) schreiben(wert);
  }

  reiter.forEach(function (t, i) {
    t.addEventListener("click", function () {
      var warAktiv = t.getAttribute("aria-selected") === "true";
      zeigen(t, false);
      if (mb.classList.contains("eingeklappt")) {
        mb.classList.toggle("offen", !(warAktiv && mb.classList.contains("offen")));
      }
    });
    t.addEventListener("keydown", function (e) {
      var ziel = null;
      if (e.key === "ArrowRight") ziel = reiter[(i + 1) % reiter.length];
      if (e.key === "ArrowLeft") ziel = reiter[(i - 1 + reiter.length) % reiter.length];
      if (e.key === "Home") ziel = reiter[0];
      if (e.key === "End") ziel = reiter[reiter.length - 1];
      if (ziel) { e.preventDefault(); zeigen(ziel, true); }
    });
  });

  if (knopf) knopf.addEventListener("click", function () { einklappen(!mb.classList.contains("eingeklappt"), true); });

  document.addEventListener("click", function (e) {
    if (mb.classList.contains("offen") && !mb.contains(e.target)) mb.classList.remove("offen");
    mb.querySelectorAll("details[open]").forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute("open"); });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      mb.classList.remove("offen");
      mb.querySelectorAll("details[open]").forEach(function (d) { d.removeAttribute("open"); });
    }
  });

  einklappen(lesen(), false);
})();
