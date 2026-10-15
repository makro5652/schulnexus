/* Schnelleingabe von Noten: sofortige Prüfung, Enter/Pfeiltasten, Einfügen einer Spalte, Gewichtsanzeige je Ordner. */
(function () {
  "use strict";
  var form = document.getElementById("ne-form");
  if (!form) return;

  function json(id, ersatz) {
    var el = document.getElementById(id);
    try { return el ? JSON.parse(el.textContent) : ersatz; } catch (e) { return ersatz; }
  }
  var erlaubt = json("ne-erlaubt", []);
  var schluessel = json("ne-schluessel", {});
  var T = json("ne-texte", {});

  function norm(t) {
    return (t || "").trim().toLowerCase().replace(/[−–—]/g, "-").replace(/\s+/g, "");
  }
  var verzeichnis = {};
  erlaubt.forEach(function (b) {
    var n = norm(b);
    verzeichnis[n] = b;
    if (/^\d$/.test(n)) verzeichnis["0" + n] = b;
  });
  var STATUS = {
    e: "entschuldigt", en: "entschuldigt", ent: "entschuldigt", entsch: "entschuldigt", "entsch.": "entschuldigt",
    u: "unentschuldigt", un: "unentschuldigt", unent: "unentschuldigt", unentsch: "unentschuldigt", "unentsch.": "unentschuldigt",
    b: "befreit", bef: "befreit", befreit: "befreit",
    nb: "nicht_bewertbar", "n.b.": "nicht_bewertbar", "n.b": "nicht_bewertbar", nichtbewertbar: "nicht_bewertbar"
  };

  var selSchluessel = form.querySelector("[name=schluessel]");
  var maxBe = form.querySelector("[name=max_be]");
  function zahl(text) { return parseFloat(String(text || "").replace(",", ".")); }
  function fmt(x) { return String(Math.round(x * 100) / 100).replace(".", T.komma || ","); }

  function deuten(text) {
    var t = norm(text);
    if (!t) return { ok: true, text: "" };
    if (STATUS[t]) return { ok: true, text: T[STATUS[t]] || STATUS[t] };
    if (t.charAt(0) === "u") {
      var rest = t.slice(1).replace(/^:/, "");
      if (rest && verzeichnis[rest]) return { ok: true, text: (T.unentschuldigt || "") + " · " + verzeichnis[rest] };
    }
    if (t.charAt(0) === "=") {
      return verzeichnis[t.slice(1)] ? { ok: true, text: verzeichnis[t.slice(1)] } : { ok: false, text: T.ungueltig };
    }
    var sk = selSchluessel && selSchluessel.value, max = maxBe ? zahl(maxBe.value) : NaN;
    if (sk && max > 0) {
      if (!/^\d+([.,]\d{1,2})?$/.test(t)) return { ok: false, text: T.be_ungueltig };
      var be = zahl(t);
      if (be < 0 || be > max) return { ok: false, text: T.be_ungueltig };
      var prozent = be / max * 100, stufe = null;
      (schluessel[sk] || []).some(function (s) { if (prozent >= s[0] - 1e-9) { stufe = s[1]; return true; } return false; });
      return { ok: true, text: fmt(prozent) + " % → " + (stufe || "?") };
    }
    return verzeichnis[t] ? { ok: true, text: "" } : { ok: false, text: T.ungueltig };
  }

  var felder = Array.prototype.slice.call(form.querySelectorAll(".ne-note"));
  var geaendert = false;

  function pruefen(feld) {
    var d = deuten(feld.value), zeile = feld.closest("tr");
    zeile.classList.toggle("ne-falsch", !d.ok);
    var deutung = zeile.querySelector(".ne-deutung");
    if (deutung) deutung.textContent = d.text;
    var alt = zeile.querySelector(".ne-fehlertext");
    if (alt && d.ok) alt.remove();
  }
  function gehe(i) {
    var f = felder[i];
    if (f) { f.focus(); f.select(); return true; }
    return false;
  }

  felder.forEach(function (feld, i) {
    feld.addEventListener("input", function () { pruefen(feld); });
    feld.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === "ArrowDown") {
        e.preventDefault();
        if (!gehe(i + 1) && e.key === "Enter") form.querySelector(".ne-speichern").focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        gehe(i - 1);
      }
    });
    feld.addEventListener("paste", function (e) {
      var text = (e.clipboardData || window.clipboardData).getData("text") || "";
      if (!/[\n\t]/.test(text.replace(/\s+$/, ""))) return;
      e.preventDefault();
      var werte = text.replace(/\r/g, "").replace(/\n+$/, "").split("\n");
      werte.forEach(function (w, j) {
        var ziel = felder[i + j];
        if (ziel) { ziel.value = w.split("\t")[0].trim(); pruefen(ziel); }
      });
      geaendert = true;
      gehe(Math.min(i + werte.length, felder.length - 1));
    });
    pruefen(feld);
  });
  if (selSchluessel) selSchluessel.addEventListener("change", function () { felder.forEach(pruefen); });
  if (maxBe) maxBe.addEventListener("input", function () { felder.forEach(pruefen); });

  // Gewicht: Einheit und Summe im gewählten Ordner
  var selOrdner = form.querySelector("[name=ordner]");
  var einheit = form.querySelector(".ne-einheit");
  var summe = form.querySelector(".ne-summe");
  var gewicht = form.querySelector("[name=gewicht]");
  function ordnerInfo() {
    var opt = selOrdner && selOrdner.options[selOrdner.selectedIndex];
    if (!opt) return;
    var prozent = opt.dataset.art === "prozent";
    if (einheit) einheit.textContent = prozent ? "%" : "";
    if (!summe) return;
    if (prozent) {
      var bisher = zahl(opt.dataset.summe) || 0, g = zahl(gewicht && gewicht.value) || 0;
      summe.textContent = (T.summe || "").replace("{a}", fmt(bisher)).replace("{b}", fmt(bisher + g));
      summe.classList.toggle("ne-ueber", bisher + g > 100.0001);
      summe.hidden = false;
    } else {
      summe.hidden = true;
    }
  }
  if (selOrdner) selOrdner.addEventListener("change", ordnerInfo);
  if (gewicht) gewicht.addEventListener("input", ordnerInfo);
  ordnerInfo();

  // Einzelgewichte ein- und ausblenden
  var einzel = document.getElementById("ne-einzel"), tabelle = form.querySelector(".ne-tabelle");
  if (einzel && tabelle) {
    einzel.addEventListener("change", function () { tabelle.classList.toggle("ne-mit-gewicht", einzel.checked); });
  }

  // Warnung bei ungespeicherten Eingaben
  form.addEventListener("input", function () { geaendert = true; });
  form.addEventListener("submit", function () { geaendert = false; });
  window.addEventListener("beforeunload", function (e) {
    if (geaendert) { e.preventDefault(); e.returnValue = T.verlassen || ""; }
  });

  // Fokus: bei neuem Leistungsnachweis die Bezeichnung, sonst das erste leere Notenfeld
  var titel = form.querySelector("[name=titel]");
  if (titel && !titel.value) { titel.focus(); }
  else {
    var leer = felder.filter(function (f) { return !f.value; })[0];
    if (leer) leer.focus();
  }
})();
