/* Suchauswahl (ab 0.4.10.0): Mehrfachauswahl mit Suchfeld, Vorschlägen und Liste im Overlay.
   Grundlage ist immer das <select multiple> des Formulars; es bleibt im Dokument (versteckt) und wird gespeichert. */
(function () {
  "use strict";

  var zaehler = 0;

  function norm(t) {
    return (t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ß/g, "ss");
  }

  function el(tag, klasse, text) {
    var e = document.createElement(tag);
    if (klasse) e.className = klasse;
    if (text != null) e.textContent = text;
    return e;
  }

  /* Trefferwert: alle Suchwörter müssen vorkommen; Wortanfänge und Vorschläge zählen mehr. */
  function wert(opt, woerter) {
    var t = " " + norm(opt.text);
    var summe = 0;
    for (var i = 0; i < woerter.length; i++) {
      var w = woerter[i];
      var pos = t.indexOf(w);
      if (pos < 0) return -1;
      summe += t.indexOf(" " + w) >= 0 || t.indexOf("(" + w) >= 0 ? 3 : 1;
    }
    if (opt.dataset.vorschlag) summe += 2;
    return summe;
  }

  function einrichten(box) {
    if (box.dataset.bereit) return;
    var sel = box.querySelector("select");
    if (!sel) return;
    box.dataset.bereit = "1";
    var t = box.dataset;
    var id = "sa" + (++zaehler);
    var gesperrt = sel.matches(":disabled");

    sel.classList.add("sa-quelle");
    sel.setAttribute("aria-hidden", "true");
    sel.tabIndex = -1;
    sel.required = false;   // das versteckte Feld darf das Abschicken nicht blockieren; Pflicht prüft der Server

    var feld = el("div", "sa-feld");
    var marken = el("ul", "sa-marken");
    var eingabe = el("input", "sa-eingabe");
    eingabe.type = "text";
    eingabe.autocomplete = "off";
    eingabe.spellcheck = false;
    eingabe.placeholder = t.tEingabe || "";
    eingabe.setAttribute("role", "combobox");
    eingabe.setAttribute("aria-autocomplete", "list");
    eingabe.setAttribute("aria-expanded", "false");
    eingabe.setAttribute("aria-controls", id + "-liste");
    eingabe.setAttribute("aria-describedby", id + "-hinweis");
    var etikett = sel.id ? document.querySelector('label[for="' + sel.id + '"]') : null;
    if (etikett) {
      if (!etikett.id) etikett.id = id + "-etikett";
      eingabe.setAttribute("aria-labelledby", etikett.id);
      etikett.addEventListener("click", function (e) { e.preventDefault(); eingabe.focus(); });
    } else {
      var legende = box.closest("fieldset") && box.closest("fieldset").querySelector("legend");
      if (legende) {
        var kopie = legende.cloneNode(true);   // nur der Titel, ohne erläuternden Kleindruck
        Array.prototype.forEach.call(kopie.querySelectorAll("small"), function (s) { s.remove(); });
        eingabe.setAttribute("aria-label", kopie.textContent.trim());
      }
    }
    feld.appendChild(marken);
    if (!gesperrt) feld.appendChild(eingabe);

    var vorschlaege = el("ul", "sa-vorschlaege");
    vorschlaege.id = id + "-liste";
    vorschlaege.setAttribute("role", "listbox");
    vorschlaege.hidden = true;

    var leiste = el("div", "sa-leiste");
    var hinweis = el("small", "sa-hinweis", t.tHinweis || "");
    hinweis.id = id + "-hinweis";
    var zahl = el("span", "sa-zahl");
    zahl.setAttribute("aria-live", "polite");
    var listeKnopf = el("button", "sa-knopf", t.tListe || "Liste");
    listeKnopf.type = "button";
    listeKnopf.setAttribute("aria-haspopup", "dialog");
    var alleKnopf = el("button", "sa-knopf", t.tAlle || "");
    alleKnopf.type = "button";

    var anker = sel;
    anker.parentNode.insertBefore(feld, anker);
    feld.parentNode.insertBefore(vorschlaege, anker);
    if (!gesperrt) {
      leiste.appendChild(listeKnopf);
      leiste.appendChild(alleKnopf);
    }
    leiste.appendChild(zahl);
    if (!gesperrt) leiste.appendChild(hinweis);
    feld.parentNode.insertBefore(leiste, anker);
    sel.classList.add("sa-versteckt");

    /* ---------------------------------------------------------- Overlay mit der ganzen Liste */
    var dialog = el("dialog", "sa-dialog");
    dialog.setAttribute("aria-labelledby", id + "-titel");
    var dKopf = el("div", "sa-dialog-kopf");
    var dTitel = el("strong", "", etikett ? etikett.textContent.replace(/:\s*$/, "").trim() : (eingabe.getAttribute("aria-label") || ""));
    dTitel.id = id + "-titel";
    var dZu = el("button", "sa-knopf sa-haupt", t.tFertig || "OK");
    dZu.type = "button";
    dKopf.appendChild(dTitel);
    dKopf.appendChild(dZu);
    var dSuche = el("input", "sa-dialog-suche");
    dSuche.type = "search";
    dSuche.placeholder = t.tSuche || "";
    dSuche.setAttribute("aria-label", t.tSuche || "");
    var dListe = el("div", "sa-dialog-liste");
    dialog.appendChild(dKopf);
    dialog.appendChild(dSuche);
    dialog.appendChild(dListe);
    box.appendChild(dialog);

    var aktiv = -1;
    var treffer = [];

    function optionen() {
      return Array.prototype.filter.call(sel.options, function (o) { return o.value !== ""; });
    }

    function geaendert() {
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      zeichnen();
    }

    function setzen(opt, an) {
      if (opt.selected === an) return;
      opt.selected = an;
      geaendert();
    }

    function zeichnen() {
      marken.textContent = "";
      var gewaehlt = optionen().filter(function (o) { return o.selected; });
      gewaehlt.forEach(function (o) {
        var li = el("li", "sa-marke" + (o.dataset.vorschlag ? " sa-vorschlag" : ""));
        li.appendChild(el("span", "", o.text));
        if (!gesperrt) {
          var x = el("button", "sa-weg", "×");
          x.type = "button";
          x.setAttribute("aria-label", o.text + " – " + (t.tEntfernen || "entfernen"));
          x.addEventListener("click", function () { setzen(o, false); eingabe.focus(); });
          li.appendChild(x);
        }
        marken.appendChild(li);
      });
      if (!gewaehlt.length && gesperrt) marken.appendChild(el("li", "sa-leer", t.tLeer || "–"));
      zahl.textContent = (t.tZahl || "%n").replace("%n", gewaehlt.length);
      var offen = optionen().filter(function (o) { return o.dataset.vorschlag && !o.selected; });
      alleKnopf.hidden = !offen.length;
      if (dialog.open) {
        Array.prototype.forEach.call(dListe.querySelectorAll("input[type=checkbox]"), function (k) { k.checked = k._option.selected; });
      }
    }

    /* ---------------------------------------------------------- Vorschläge unter dem Eingabefeld */
    function schliessen() {
      vorschlaege.hidden = true;
      eingabe.setAttribute("aria-expanded", "false");
      eingabe.removeAttribute("aria-activedescendant");
      aktiv = -1;
      treffer = [];
    }

    function vorschlagen(alleZeigen) {
      var q = norm(eingabe.value).trim();
      if (!q && !alleZeigen) { schliessen(); return; }
      var woerter = q ? q.split(/\s+/) : [];
      treffer = optionen().filter(function (o) { return !o.selected; })
        .map(function (o, i) { return { o: o, w: woerter.length ? wert(o, woerter) : (o.dataset.vorschlag ? 1 : 0), i: i }; })
        .filter(function (x) { return x.w >= 0; })
        .sort(function (a, b) { return b.w - a.w || a.i - b.i; })
        .slice(0, 8)
        .map(function (x) { return x.o; });
      vorschlaege.textContent = "";
      if (!treffer.length) {
        vorschlaege.appendChild(el("li", "sa-keine", t.tKeine || "–"));
        aktiv = -1;
      } else {
        aktiv = 0;
        treffer.forEach(function (o, i) {
          var li = el("li", "sa-treffer" + (o.dataset.vorschlag ? " sa-vorschlag" : ""), o.text);
          li.id = id + "-t" + i;
          li.setAttribute("role", "option");
          li.addEventListener("mousedown", function (e) { e.preventDefault(); waehlen(o); });
          vorschlaege.appendChild(li);
        });
      }
      vorschlaege.hidden = false;
      eingabe.setAttribute("aria-expanded", "true");
      markieren();
    }

    function markieren() {
      Array.prototype.forEach.call(vorschlaege.querySelectorAll(".sa-treffer"), function (li, i) {
        var an = i === aktiv;
        li.classList.toggle("aktiv", an);
        li.setAttribute("aria-selected", an ? "true" : "false");
        if (an) {
          eingabe.setAttribute("aria-activedescendant", li.id);
          if (li.scrollIntoView) li.scrollIntoView({ block: "nearest" });
        }
      });
    }

    function waehlen(o) {
      setzen(o, true);
      eingabe.value = "";
      schliessen();
      eingabe.focus();
    }

    eingabe.addEventListener("input", function () { vorschlagen(false); });
    eingabe.addEventListener("focus", function () { if (eingabe.value) vorschlagen(false); });
    eingabe.addEventListener("blur", function () { setTimeout(schliessen, 120); });
    eingabe.addEventListener("keydown", function (e) {
      var offen = !vorschlaege.hidden;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!offen) { vorschlagen(true); return; }
        if (treffer.length) { aktiv = (aktiv + 1) % treffer.length; markieren(); }
      } else if (e.key === "ArrowUp") {
        if (!offen) return;
        e.preventDefault();
        if (treffer.length) { aktiv = (aktiv - 1 + treffer.length) % treffer.length; markieren(); }
      } else if (e.key === "Enter") {
        if (offen) {
          e.preventDefault();
          if (aktiv >= 0 && treffer[aktiv]) waehlen(treffer[aktiv]);
        } else if (eingabe.value) {
          e.preventDefault();   // halb getippter Name schickt das Formular nicht ab
        }
      } else if (e.key === "Tab" && !e.shiftKey) {
        if (offen && eingabe.value && aktiv >= 0 && treffer[aktiv]) {
          e.preventDefault();   // Tab übernimmt den Vorschlag; das Feld bleibt für den nächsten Namen
          waehlen(treffer[aktiv]);
        }
      } else if (e.key === "Escape") {
        if (offen) { e.preventDefault(); schliessen(); }
      }
    });
    feld.addEventListener("mousedown", function (e) {
      if (e.target === feld || e.target === marken) { e.preventDefault(); eingabe.focus(); }
    });

    /* ---------------------------------------------------------- Liste im Overlay */
    function listeFuellen() {
      var q = norm(dSuche.value).trim();
      var woerter = q ? q.split(/\s+/) : [];
      dListe.textContent = "";
      var alle = optionen();
      var mitVorschlag = alle.some(function (o) { return o.dataset.vorschlag; });
      var gruppen = mitVorschlag
        ? [[t.tVorschlaege || "", alle.filter(function (o) { return o.dataset.vorschlag; })],
           [t.tWeitere || "", alle.filter(function (o) { return !o.dataset.vorschlag; })]]
        : [["", alle]];
      var gezeigt = 0;
      gruppen.forEach(function (g) {
        var liste = g[1].filter(function (o) { return !woerter.length || wert(o, woerter) >= 0; });
        if (!liste.length) return;
        var abschnitt = el("div", "sa-gruppe");
        if (g[0]) abschnitt.appendChild(el("div", "sa-gruppe-titel", g[0]));
        liste.forEach(function (o) {
          var zeile = el("label", "sa-option");
          var kasten = el("input");
          kasten.type = "checkbox";
          kasten.checked = o.selected;
          kasten._option = o;
          kasten.addEventListener("change", function () { setzen(o, kasten.checked); });
          zeile.appendChild(kasten);
          zeile.appendChild(el("span", "", o.text));
          abschnitt.appendChild(zeile);
          gezeigt++;
        });
        dListe.appendChild(abschnitt);
      });
      if (!gezeigt) dListe.appendChild(el("p", "sa-keine", t.tKeine || "–"));
    }

    listeKnopf.addEventListener("click", function () {
      dSuche.value = "";
      listeFuellen();
      if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
      dSuche.focus();
    });
    function dialogZu() {
      if (dialog.close) dialog.close(); else dialog.removeAttribute("open");
      listeKnopf.focus();
    }
    dZu.addEventListener("click", dialogZu);
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialogZu(); });
    dSuche.addEventListener("input", listeFuellen);
    dSuche.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();   // nicht das umgebende Formular abschicken
        var erster = dListe.querySelector("input[type=checkbox]:not(:checked)");
        if (erster && dSuche.value) { erster.checked = true; erster.dispatchEvent(new Event("change")); dSuche.select(); }
      }
    });

    alleKnopf.addEventListener("click", function () {
      var neu = optionen().filter(function (o) { return o.dataset.vorschlag && !o.selected; });
      neu.forEach(function (o) { o.selected = true; });
      if (neu.length) geaendert();
    });

    /* Neue Einträge über „+“ (Verwaltungsoberfläche) oder Änderungen von außen übernehmen */
    sel.addEventListener("change", function (e) { if (e.isTrusted !== false) zeichnen(); });
    if (window.MutationObserver) new MutationObserver(zeichnen).observe(sel, { childList: true });

    zeichnen();
  }

  function alleEinrichten(wurzel) {
    Array.prototype.forEach.call((wurzel || document).querySelectorAll("[data-suchauswahl]"), function (box) {
      if (!box.closest(".empty-form")) einrichten(box);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { alleEinrichten(); });
  else alleEinrichten();
  document.addEventListener("formset:added", function (e) { alleEinrichten(e.target); });
  window.Suchauswahl = { einrichten: alleEinrichten };
})();
