/* Befehlssuche und Favoriten (ab 0.6.0).
   Strg+K (Mac: ⌘+K) öffnet eine Suche über alle Befehle des Menübands, die das Konto nutzen darf – die Liste stammt
   aus dem Menüband der Seite, enthält also nie mehr als dieses. Mit ★ gemerkte Befehle stehen als Favoritenleiste
   unter dem Menüband. Favoriten und „zuletzt verwendet“ merkt sich der Browser (localStorage), nicht der Server. */
(function () {
  "use strict";
  var mb = document.getElementById("menueband"), dialog = document.getElementById("bs");
  if (!mb || !dialog || !dialog.showModal) return;
  var eingabe = document.getElementById("bs-eingabe"), liste = document.getElementById("bs-liste"),
    leiste = document.getElementById("mb-schnell");
  var T = function (k) { return dialog.getAttribute("data-t-" + k) || ""; };
  var FAV = "befehle-favoriten", ZULETZT = "befehle-zuletzt";

  function lesen(k) { try { return JSON.parse(window.localStorage.getItem(k) || "[]"); } catch (e) { return []; } }
  function schreiben(k, v) { try { window.localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ohne Speicher */ } }
  function schlicht(t) {
    t = (t || "").toLowerCase();
    return t.normalize ? t.normalize("NFD").replace(/[̀-ͯ]/g, "") : t;
  }

  // Alle Befehle aus dem Menüband einsammeln (einmal je Adresse)
  var befehle = [], nachUrl = {};
  Array.prototype.forEach.call(mb.querySelectorAll(".mb-band"), function (band) {
    var reiter = document.getElementById(band.getAttribute("aria-labelledby"));
    var karte = reiter ? reiter.textContent.trim() : "";
    Array.prototype.forEach.call(band.querySelectorAll(".mb-gruppe"), function (gruppe) {
      var gt = gruppe.querySelector(".mb-gruppentitel"), gruppenname = gt ? gt.textContent.trim() : "";
      Array.prototype.forEach.call(gruppe.querySelectorAll("a[href]"), function (a) {
        var url = a.getAttribute("href"), titel = (a.querySelector("span") || a).textContent.trim();
        if (!url || nachUrl[url]) return;
        var symbol = a.querySelector("use");
        var b = { url: url, titel: titel, pfad: karte + " › " + gruppenname, hinweis: a.getAttribute("title") || "",
                  symbol: symbol ? symbol.getAttribute("href") : "" };
        b.such = schlicht(b.titel + " " + b.pfad + " " + (b.hinweis === b.titel ? "" : b.hinweis));
        nachUrl[url] = b;
        befehle.push(b);
      });
    });
  });
  if (!befehle.length) return;

  function favoriten() { return lesen(FAV).filter(function (u) { return nachUrl[u]; }); }
  function istFavorit(url) { return favoriten().indexOf(url) !== -1; }
  function favoritUmschalten(url) {
    var f = favoriten(), i = f.indexOf(url);
    if (i === -1) f.push(url); else f.splice(i, 1);
    schreiben(FAV, f.slice(0, 12));
    leisteZeichnen();
  }
  function gemerkt(url) {
    var z = lesen(ZULETZT).filter(function (u) { return u !== url; });
    z.unshift(url);
    schreiben(ZULETZT, z.slice(0, 6));
  }

  function bild(href) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"), use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true");
    use.setAttribute("href", href);
    svg.appendChild(use);
    return svg;
  }

  // ---- Favoritenleiste unter dem Menüband ----
  function leisteZeichnen() {
    if (!leiste) return;
    Array.prototype.slice.call(leiste.querySelectorAll("a")).forEach(function (a) { a.remove(); });
    var f = favoriten();
    f.forEach(function (url) {
      var b = nachUrl[url], a = document.createElement("a");
      a.href = b.url; a.title = b.pfad + (b.hinweis && b.hinweis !== b.titel ? " – " + b.hinweis : "");
      if (b.symbol) a.appendChild(bild(b.symbol));
      a.appendChild(document.createTextNode(b.titel));
      leiste.appendChild(a);
    });
    leiste.hidden = !f.length;
  }
  leisteZeichnen();

  // ---- Suchfenster ----
  var treffer = [], aktiv = 0;
  function zeile(b, i) {
    var el = document.createElement("div"), a = document.createElement("a"), text = document.createElement("span"),
      titel = document.createElement("strong"), pfad = document.createElement("small"), stern = document.createElement("button");
    el.className = "bs-zeile" + (i === aktiv ? " aktiv" : "");
    el.setAttribute("role", "option");
    el.setAttribute("aria-selected", i === aktiv ? "true" : "false");
    a.href = b.url;
    if (b.symbol) a.appendChild(bild(b.symbol));
    titel.textContent = b.titel;
    pfad.textContent = b.pfad + (b.hinweis && b.hinweis !== b.titel ? " – " + b.hinweis : "");
    text.appendChild(titel); text.appendChild(pfad);
    a.appendChild(text);
    a.addEventListener("click", function () { if (!b.person) gemerkt(b.url); });
    el.appendChild(a);
    if (!b.person) {
      var fav = istFavorit(b.url);
      stern.type = "button";
      stern.className = "bs-stern" + (fav ? " an" : "");
      stern.textContent = fav ? "★" : "☆";
      stern.title = fav ? T("entfernen") : T("merken");
      stern.setAttribute("aria-label", stern.title + ": " + b.titel);
      stern.setAttribute("aria-pressed", fav ? "true" : "false");
      stern.addEventListener("click", function () { favoritUmschalten(b.url); zeichnen(); eingabe.focus(); });
      el.appendChild(stern);
    }
    return el;
  }
  function ueberschrift(text) {
    var h = document.createElement("p");
    h.className = "bs-titel"; h.textContent = text;
    return h;
  }
  function zeichnen() {
    var q = schlicht(eingabe.value).trim(), woerter = q.split(/\s+/).filter(Boolean), abschnitte = [];
    liste.textContent = "";
    if (!woerter.length) {
      var f = favoriten().map(function (u) { return nachUrl[u]; });
      var z = lesen(ZULETZT).filter(function (u) { return nachUrl[u] && !istFavorit(u); }).map(function (u) { return nachUrl[u]; });
      var rest = befehle.filter(function (b) { return f.indexOf(b) === -1 && z.indexOf(b) === -1; });
      if (f.length) abschnitte.push([T("favoriten"), f]);
      if (z.length) abschnitte.push([T("zuletzt"), z]);
      abschnitte.push([T("alle"), rest]);
    } else {
      var gefunden = befehle.filter(function (b) { return woerter.every(function (w) { return b.such.indexOf(w) !== -1; }); });
      gefunden.sort(function (a, b) {               // Treffer im Titel zuerst, am Wortanfang ganz vorn
        var ta = schlicht(a.titel), tb = schlicht(b.titel);
        var wa = ta.indexOf(woerter[0]) === 0 ? 0 : ta.indexOf(woerter[0]) !== -1 ? 1 : 2;
        var wb = tb.indexOf(woerter[0]) === 0 ? 0 : tb.indexOf(woerter[0]) !== -1 ? 1 : 2;
        return wa - wb;
      });
      if (eingabe.value.trim().length >= 2) {
        gefunden.push({ person: true, url: dialog.getAttribute("data-suche") + "?q=" + encodeURIComponent(eingabe.value.trim()),
                        titel: T("person").replace("{q}", eingabe.value.trim()), pfad: "", hinweis: "", symbol: "#s-lupe" });
      }
      abschnitte.push(["", gefunden]);
    }
    treffer = [];
    abschnitte.forEach(function (a) { treffer = treffer.concat(a[1]); });
    if (aktiv >= treffer.length) aktiv = Math.max(0, treffer.length - 1);
    var i = 0;
    abschnitte.forEach(function (a) {
      if (a[0] && a[1].length) liste.appendChild(ueberschrift(a[0]));
      a[1].forEach(function (b) { liste.appendChild(zeile(b, i)); i++; });
    });
    if (!treffer.length) liste.appendChild(ueberschrift(T("keine")));
    var el = liste.querySelector(".bs-zeile.aktiv");
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }
  function oeffnen() {
    if (dialog.open) return;
    eingabe.value = ""; aktiv = 0;
    zeichnen();
    dialog.showModal();
    eingabe.focus();
  }
  eingabe.addEventListener("input", function () { aktiv = 0; zeichnen(); });
  eingabe.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") { e.preventDefault(); aktiv = Math.min(aktiv + 1, treffer.length - 1); zeichnen(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); aktiv = Math.max(aktiv - 1, 0); zeichnen(); }
    else if (e.key === "Enter") {
      e.preventDefault();
      var b = treffer[aktiv];
      if (b) { if (!b.person) gemerkt(b.url); window.location.href = b.url; }
    }
  });
  dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });   // Klick neben das Fenster
  var knopf = document.getElementById("mb-befehle-oeffnen");
  if (knopf) knopf.addEventListener("click", oeffnen);
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === "k" || e.key === "K")) { e.preventDefault(); oeffnen(); }
  });
})();
