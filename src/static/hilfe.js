/* Hilfe-Einblendung (ab 0.7.0): Knopf am rechten Rand jeder Seite, Einblendung von rechts.
   „Diese Seite“ zeigt das zur Seite passende Thema (vom Server bestimmt), „Alle Themen“ die Übersicht.
   Verweise mit data-hilfe öffnen ein Thema in der Einblendung; die Suche lädt einmal einen Index und filtert im Browser. */
(function () {
  "use strict";
  var panel = document.getElementById("hp"), knopf = document.getElementById("hp-knopf");
  if (!panel || !knopf || !window.fetch) return;
  var inhalt = document.getElementById("hp-inhalt"), suche = document.getElementById("hp-suche"),
    gross = document.getElementById("hp-gross"), zu = document.getElementById("hp-zu");
  var basis = panel.getAttribute("data-basis"), seitenThema = panel.getAttribute("data-thema") || "";
  var reiter = Array.prototype.slice.call(panel.querySelectorAll(".hp-reiter button"));
  var zwischenspeicher = {}, index = null, aktuell = null;

  function url(slug) { return basis + (slug ? slug + "/" : ""); }
  function laden(adresse) {
    if (zwischenspeicher[adresse]) return Promise.resolve(zwischenspeicher[adresse]);
    return fetch(adresse + "?teil=1", { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (t) { zwischenspeicher[adresse] = t; return t; });
  }
  function zeigen(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");      // Inhalt kommt vom eigenen Server, ohne Skripte
    inhalt.textContent = "";
    Array.prototype.forEach.call(doc.body.childNodes, function (n) { inhalt.appendChild(document.importNode(n, true)); });
    inhalt.scrollTop = 0;
  }
  function fehler() {
    inhalt.textContent = "";
    var p = document.createElement("p");
    p.className = "hp-fehler"; p.textContent = panel.getAttribute("data-t-fehler");
    inhalt.appendChild(p);
  }
  function reiterSetzen(ziel) {
    reiter.forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-ziel") === ziel ? "true" : "false"); });
  }
  function thema(slug) {
    aktuell = slug;
    reiterSetzen(slug === seitenThema ? "seite" : "");
    gross.href = url(slug);
    return laden(url(slug)).then(zeigen, fehler);
  }
  function uebersicht() {
    aktuell = null;
    reiterSetzen("alle");
    gross.href = url("");
    return laden(url("")).then(function (html) { zeigen(html); filtern(); }, fehler);
  }

  // ---- Öffnen und Schließen ----
  var vorher = null;
  function oeffnen(slug) {
    if (panel.hidden) {
      vorher = document.activeElement;
      panel.hidden = false;
      knopf.setAttribute("aria-expanded", "true");
      document.documentElement.classList.add("hp-offen");
      window.requestAnimationFrame(function () { panel.classList.add("hp-sichtbar"); });
    }
    var weiter = slug ? thema(slug) : (aktuell || seitenThema) ? thema(aktuell || seitenThema) : uebersicht();
    weiter.then(function () { zu.focus(); });
  }
  function schliessen() {
    panel.classList.remove("hp-sichtbar");
    knopf.setAttribute("aria-expanded", "false");
    document.documentElement.classList.remove("hp-offen");
    window.setTimeout(function () { panel.hidden = true; }, 200);
    if (vorher && vorher.focus) vorher.focus(); else knopf.focus();
  }
  knopf.addEventListener("click", function () { if (panel.hidden) oeffnen(); else schliessen(); });
  zu.addEventListener("click", schliessen);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden && !document.querySelector("dialog[open]")) { e.preventDefault(); schliessen(); }
  });
  reiter.forEach(function (b) {
    b.addEventListener("click", function () {
      suche.value = "";
      if (b.getAttribute("data-ziel") === "seite") thema(seitenThema); else uebersicht();
    });
  });

  // ---- Verweise auf Hilfethemen: in der Einblendung öffnen (auch aus Seiteninhalten heraus) ----
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-hilfe]");
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    if (!panel.contains(a) && window.location.pathname.indexOf(basis) === 0) return;   // auf den Hilfeseiten normal blättern
    e.preventDefault();
    suche.value = "";
    oeffnen(a.getAttribute("data-hilfe"));
  });
  inhalt.addEventListener("click", function (e) {             // Inhaltsverzeichnis: innerhalb der Einblendung springen
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a) return;
    var ziel = inhalt.querySelector(a.getAttribute("href"));
    if (ziel) { e.preventDefault(); ziel.scrollIntoView({ block: "start" }); }
  });

  // ---- Suche ----
  function schlicht(t) {
    t = (t || "").toLowerCase();
    return t.normalize ? t.normalize("NFD").replace(/[̀-ͯ]/g, "") : t;
  }
  function indexLaden() {
    if (index) return Promise.resolve(index);
    return fetch(panel.getAttribute("data-suche"), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        index = {};
        d.themen.forEach(function (t) { index[t.slug] = { titel: schlicht(t.titel), text: schlicht(t.kurz + " " + t.text) }; });
        return index;
      });
  }
  function filtern() {
    var q = schlicht(suche.value).trim(), woerter = q.split(/\s+/).filter(Boolean);
    var eintraege = Array.prototype.slice.call(inhalt.querySelectorAll(".hp-liste li"));
    if (!eintraege.length) return;
    var leer = inhalt.querySelector(".hp-keine");
    if (!woerter.length) {
      eintraege.forEach(function (li) { li.hidden = false; li.removeAttribute("data-titeltreffer"); });
      ordnen(eintraege);
      Array.prototype.forEach.call(inhalt.querySelectorAll(".hp-gruppe"), function (g) { g.hidden = false; });
      if (leer) leer.remove();
      return;
    }
    indexLaden().then(function (idx) {
      var treffer = 0;
      eintraege.forEach(function (li) {
        var e = idx[li.getAttribute("data-slug")] || { titel: "", text: "" };
        var imTitel = woerter.every(function (w) { return e.titel.indexOf(w) !== -1; });
        var passt = imTitel || woerter.every(function (w) { return e.titel.indexOf(w) !== -1 || e.text.indexOf(w) !== -1; });
        li.hidden = !passt;
        if (imTitel) li.setAttribute("data-titeltreffer", "1"); else li.removeAttribute("data-titeltreffer");
        if (passt) treffer++;
      });
      ordnen(eintraege);
      Array.prototype.forEach.call(inhalt.querySelectorAll(".hp-gruppe"), function (g) {
        g.hidden = !g.querySelector(".hp-liste li:not([hidden])");
      });
      if (!treffer && !inhalt.querySelector(".hp-keine")) {
        var p = document.createElement("p");
        p.className = "hp-keine"; p.textContent = panel.getAttribute("data-t-keine");
        inhalt.appendChild(p);
      } else if (treffer && leer) { leer.remove(); }
    });
  }
  // Treffer im Titel stehen in jeder Gruppe oben; sonst bleibt die ursprüngliche Reihenfolge
  function ordnen(eintraege) {
    eintraege.forEach(function (li, i) { if (!li.hasAttribute("data-pos")) li.setAttribute("data-pos", i); });
    var nachListe = new Map();
    eintraege.forEach(function (li) {
      var ul = li.parentNode;
      if (!nachListe.has(ul)) nachListe.set(ul, []);
      nachListe.get(ul).push(li);
    });
    nachListe.forEach(function (lis, ul) {
      lis.sort(function (a, b) {
        var ta = a.hasAttribute("data-titeltreffer") ? 0 : 1, tb = b.hasAttribute("data-titeltreffer") ? 0 : 1;
        return ta - tb || a.getAttribute("data-pos") - b.getAttribute("data-pos");
      }).forEach(function (li) { ul.appendChild(li); });
    });
  }
  var warten = null;
  suche.addEventListener("input", function () {
    window.clearTimeout(warten);
    warten = window.setTimeout(function () {
      if (!inhalt.querySelector(".hp-index")) uebersicht(); else filtern();
    }, 120);
  });
  suche.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      var erster = inhalt.querySelector(".hp-liste li[data-titeltreffer]:not([hidden]) a")
        || inhalt.querySelector(".hp-liste li:not([hidden]) a");
      if (erster) erster.click();
    }
  });

  // Hilfe lässt sich auch mit ?hilfe=thema in einer Adresse öffnen (z. B. aus einem Hinweis)
  var gewuenscht = new URLSearchParams(window.location.search).get("hilfe");
  if (gewuenscht && /^[a-z0-9-]+$/.test(gewuenscht)) oeffnen(gewuenscht);
})();
