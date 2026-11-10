/* Schnelleingabe von Noten: sofortige Prüfung, Enter/Pfeiltasten, Einfügen einer Spalte, Gewichtsanzeige je Ordner.
   Ab 0.5.0: Statistik beim Tippen, Namensfilter, Tastenkürzel (Strg+S, Strg+Enter, F1), Entwurf im Browser. */
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
  var werte = json("ne-werte", {});

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
    if (!t) return { ok: true, text: "", leer: true };
    if (STATUS[t]) return { ok: true, text: T[STATUS[t]] || STATUS[t], status: STATUS[t] };
    if (t.charAt(0) === "u") {
      var rest = t.slice(1).replace(/^:/, "");
      if (rest && verzeichnis[rest]) return { ok: true, text: (T.unentschuldigt || "") + " · " + verzeichnis[rest], status: "unentschuldigt", stufe: verzeichnis[rest] };
    }
    if (t.charAt(0) === "=") {
      return verzeichnis[t.slice(1)] ? { ok: true, text: verzeichnis[t.slice(1)], stufe: verzeichnis[t.slice(1)] } : { ok: false, text: T.ungueltig };
    }
    var sk = selSchluessel && selSchluessel.value, max = maxBe ? zahl(maxBe.value) : NaN;
    if (sk && max > 0) {
      if (!/^\d+([.,]\d{1,2})?$/.test(t)) return { ok: false, text: T.be_ungueltig };
      var be = zahl(t);
      if (be < 0 || be > max) return { ok: false, text: T.be_ungueltig };
      var prozent = be / max * 100, stufe = null;
      (schluessel[sk] || []).some(function (s) { if (prozent >= s[0] - 1e-9) { stufe = s[1]; return true; } return false; });
      return { ok: true, text: fmt(prozent) + " % → " + (stufe || "?"), stufe: stufe };
    }
    return verzeichnis[t] ? { ok: true, text: "", stufe: verzeichnis[t] } : { ok: false, text: T.ungueltig };
  }

  var felder = Array.prototype.slice.call(form.querySelectorAll(".ne-note:not([disabled])"));
  var alleNoten = Array.prototype.slice.call(form.querySelectorAll(".ne-note"));
  var geaendert = false;
  function sichtbare() { return felder.filter(function (f) { return !f.closest("tr").hidden; }); }

  function pruefen(feld) {
    var d = deuten(feld.value), zeile = feld.closest("tr");
    zeile.classList.toggle("ne-falsch", !d.ok);
    var deutung = zeile.querySelector(".ne-deutung");
    if (deutung) deutung.textContent = d.text;
    var alt = zeile.querySelector(".ne-fehlertext");
    if (alt && d.ok) alt.remove();
  }
  function gehe(feld, schritt) {
    var liste = sichtbare(), f = liste[liste.indexOf(feld) + schritt];
    if (f) { f.focus(); f.select(); return true; }
    return false;
  }

  felder.forEach(function (feld, i) {
    feld.addEventListener("input", function () { pruefen(feld); });
    feld.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === "ArrowDown") {
        e.preventDefault();
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) return;   // Strg+Enter: speichern und nächsten anlegen
        if (!gehe(feld, 1) && e.key === "Enter") form.querySelector(".ne-speichern").focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        gehe(feld, -1);
      }
    });
    feld.addEventListener("paste", function (e) {
      var text = (e.clipboardData || window.clipboardData).getData("text") || "";
      if (!/[\n\t]/.test(text.replace(/\s+$/, ""))) return;
      e.preventDefault();
      var zeilen = text.replace(/\r/g, "").replace(/\n+$/, "").split("\n");
      var liste = sichtbare(), start = liste.indexOf(feld), letztes = feld;
      zeilen.forEach(function (w, j) {
        var ziel = liste[start + j];
        if (ziel) { ziel.value = w.split("\t")[0].trim(); pruefen(ziel); letztes = ziel; }
      });
      geaendert = true;
      statistik(); merken();
      if (!gehe(letztes, 1)) { letztes.focus(); letztes.select(); }
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

  // ---- Statistik beim Tippen (nur Anzeige) ----
  function setze(id, text) { var el = document.getElementById(id); if (el) el.textContent = text; }
  function gruppe(b) { var m = /^(\d)[+-]?$/.exec(b); return m ? m[1] : b; }
  function statistik() {
    if (!document.getElementById("ne-statistik")) return;
    var z = { entschuldigt: 0, unentschuldigt: 0, befreit: 0, nicht_bewertbar: 0 }, leer = 0, summe = 0, n = 0, verteilung = {};
    alleNoten.forEach(function (f) {
      var d = deuten(f.value);
      if (d.leer || !d.ok) { if (d.leer) leer++; return; }
      if (d.status) z[d.status]++;
      if (d.stufe && werte[d.stufe] !== undefined) {
        summe += werte[d.stufe]; n++;
        var g = gruppe(d.stufe);
        verteilung[g] = (verteilung[g] || 0) + 1;
      }
    });
    setze("ne-st-schnitt", n ? fmt(summe / n) : "–");
    setze("ne-st-anzahl", (T.eingetragen || "{a} / {b}").replace("{a}", alleNoten.length - leer).replace("{b}", alleNoten.length));
    setze("ne-st-e", z.entschuldigt); setze("ne-st-u", z.unentschuldigt); setze("ne-st-b", z.befreit);
    setze("ne-st-nb", z.nicht_bewertbar); setze("ne-st-leer", leer);
    var balken = document.getElementById("ne-st-balken");
    if (!balken) return;
    balken.textContent = "";
    var reihen = [], gesehen = {}, max = 0;
    erlaubt.forEach(function (b) { var g = gruppe(b); if (!gesehen[g]) { gesehen[g] = true; reihen.push(g); } });
    reihen.forEach(function (g) { max = Math.max(max, verteilung[g] || 0); });
    if (reihen.length > 8) reihen = reihen.filter(function (g) { return verteilung[g]; });   // Punkte 15 … 0: nur vergebene
    reihen.forEach(function (g) {
      var zeile = document.createElement("div"), name = document.createElement("b"), spur = document.createElement("span"),
        strich = document.createElement("i"), zahlEl = document.createElement("span"), k = verteilung[g] || 0;
      zeile.className = "ne-balkenzeile";
      name.textContent = g;
      strich.style.width = (max ? k / max * 100 : 0) + "%";
      if (!k) strich.style.visibility = "hidden";
      zahlEl.textContent = k;
      spur.appendChild(strich);
      zeile.appendChild(name); zeile.appendChild(spur); zeile.appendChild(zahlEl);
      balken.appendChild(zeile);
    });
  }

  // ---- Namensfilter und „nur ohne Note“ ----
  var filter = document.getElementById("ne-filter"), nurLeer = document.getElementById("ne-nur-leer"),
    treffer = document.getElementById("ne-treffer");
  var datenzeilen = alleNoten.map(function (f) { return f.closest("tr"); });
  function schlicht(t) {
    t = (t || "").toLowerCase();
    return t.normalize ? t.normalize("NFD").replace(/[\u0300-\u036f]/g, "") : t;
  }
  function filtern() {
    var q = schlicht(filter && filter.value).trim(), leer = nurLeer && nurLeer.checked, n = 0;
    datenzeilen.forEach(function (zeile) {
      var name = zeile.querySelector("th"), note = zeile.querySelector(".ne-note");
      var zeigen = (!q || schlicht(name && name.textContent).indexOf(q) !== -1) && (!leer || !note.value.trim());
      zeile.hidden = !zeigen;
      if (zeigen) n++;
    });
    if (treffer) treffer.textContent = (q || leer) ? (T.treffer || "{a} / {b}").replace("{a}", n).replace("{b}", datenzeilen.length) : "";
  }
  if (filter) {
    filter.addEventListener("input", filtern);
    filter.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === "ArrowDown") {
        e.preventDefault();
        var erste = sichtbare()[0];
        if (erste) { erste.focus(); erste.select(); }
      }
    });
  }
  if (nurLeer) nurLeer.addEventListener("change", filtern);

  // ---- Entwurf: ungespeicherte Eingaben bis zum Schließen des Fensters im Browser merken ----
  var SCHLUESSEL = form.getAttribute("data-entwurf") || "", status = document.getElementById("ne-status");
  var NICHT_MERKEN = { csrfmiddlewaretoken: true, weiter: true };
  function speicher() { try { return window.sessionStorage; } catch (e) { return null; } }
  function stand() {
    var f = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || NICHT_MERKEN[el.name] || el.disabled || el.type === "submit" || el.type === "button") return;
      f[el.name] = (el.type === "checkbox" || el.type === "radio") ? (el.checked ? "1" : "") : el.value;
    });
    return f;
  }
  function gleich(a, b) {
    return Object.keys(b).every(function (k) { return a[k] === undefined || a[k] === b[k]; });
  }
  function uhrzeit(ms) {
    var d = new Date(ms), zwei = function (x) { return (x < 10 ? "0" : "") + x; };
    return zwei(d.getHours()) + ":" + zwei(d.getMinutes());
  }
  var ausgang = stand(), merkZeit = null;
  function merkenJetzt() {
    var s = speicher();
    if (!s || !SCHLUESSEL || !geaendert) return;
    try {
      var jetzt = Date.now();
      s.setItem(SCHLUESSEL, JSON.stringify({ t: jetzt, f: stand() }));
      if (status) status.textContent = (T.gemerkt || "").replace("{zeit}", uhrzeit(jetzt));
    } catch (e) { /* Speicher voll oder gesperrt: dann eben ohne Entwurf */ }
  }
  function merken() { window.clearTimeout(merkZeit); merkZeit = window.setTimeout(merkenJetzt, 500); }
  function entwurfLoeschen() { var s = speicher(); if (s && SCHLUESSEL) { try { s.removeItem(SCHLUESSEL); } catch (e) { /* egal */ } } }

  (function entwurfPruefen() {
    var s = speicher(), kasten = document.getElementById("ne-entwurf");
    if (!s || !SCHLUESSEL) return;
    var eigener = SCHLUESSEL.split(".").slice(0, 2).join(".") + ".", i, k, weg = [];
    try {
      for (i = 0; i < s.length; i++) { k = s.key(i); if (k && k.indexOf("ne.") === 0 && k.indexOf(eigener) !== 0) weg.push(k); }
      weg.forEach(function (x) { s.removeItem(x); });     // Entwürfe anderer Konten in diesem Fenster entfernen
    } catch (e) { /* egal */ }
    var roh = null, entwurf = null;
    try { roh = s.getItem(SCHLUESSEL); entwurf = roh ? JSON.parse(roh) : null; } catch (e) { entwurf = null; }
    if (!entwurf || !entwurf.f || gleich(entwurf.f, ausgang)) { if (roh) entwurfLoeschen(); return; }
    if (!kasten) return;
    kasten.querySelector(".ne-entwurf-text").textContent = (T.entwurf || "").replace("{zeit}", uhrzeit(entwurf.t || Date.now()));
    kasten.hidden = false;
    document.getElementById("ne-entwurf-holen").addEventListener("click", function () {
      Object.keys(entwurf.f).forEach(function (name) {
        var el = form.elements[name];
        if (!el || el.disabled || el.length !== undefined && el.tagName !== "SELECT") return;
        if (el.type === "checkbox") el.checked = entwurf.f[name] === "1"; else el.value = entwurf.f[name];
      });
      felder.forEach(pruefen);
      ordnerInfo();
      if (einzel && tabelle && Object.keys(entwurf.f).some(function (n) { return /^g_/.test(n) && entwurf.f[n]; })) {
        einzel.checked = true; tabelle.classList.add("ne-mit-gewicht");
      }
      geaendert = true;
      statistik(); filtern();
      kasten.hidden = true;
    });
    document.getElementById("ne-entwurf-weg").addEventListener("click", function () { entwurfLoeschen(); kasten.hidden = true; });
  })();

  // ---- Tastenkürzel: Strg/⌘+S speichern, Strg/⌘+Enter speichern und nächsten anlegen, F1 Übersicht, Esc leert den Filter ----
  var dialog = document.getElementById("ne-kuerzel"), dialogKnopf = document.getElementById("ne-kuerzel-oeffnen");
  function hilfe() { if (dialog && dialog.showModal && !dialog.open) dialog.showModal(); }
  if (dialogKnopf) dialogKnopf.addEventListener("click", hilfe);
  function absenden(knopf) {
    if (!knopf) return;
    if (form.requestSubmit) form.requestSubmit(knopf); else knopf.click();
  }
  document.addEventListener("keydown", function (e) {
    var strg = e.ctrlKey || e.metaKey;
    if (dialog && dialog.open) return;
    if (strg && !e.altKey && (e.key === "s" || e.key === "S")) {
      e.preventDefault(); absenden(form.querySelector(".ne-speichern"));
    } else if (strg && e.key === "Enter") {
      e.preventDefault(); absenden(form.querySelector("button[name=weiter]"));
    } else if (e.key === "F1") {
      e.preventDefault(); hilfe();
    } else if (e.key === "Escape" && filter && (filter.value || (nurLeer && nurLeer.checked))) {
      filter.value = ""; if (nurLeer) nurLeer.checked = false; filtern();
    }
  });

  form.addEventListener("input", function () { statistik(); merken(); });
  form.addEventListener("change", function () { statistik(); merken(); });
  statistik();

  // Warnung bei ungespeicherten Eingaben
  form.addEventListener("input", function (e) { if (!e.target || e.target.name || e.target.id === "ne-einzel") geaendert = true; });
  form.addEventListener("submit", function () { window.clearTimeout(merkZeit); merkenJetzt(); geaendert = false; });
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
