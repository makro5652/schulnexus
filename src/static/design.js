/* Setzt das gewählte Design auf <html>, bevor die Seite gezeichnet wird (Verwaltungsoberfläche). */
(function () {
  var s = document.currentScript, d = s && s.getAttribute("data-design");
  if (d) { document.documentElement.setAttribute("data-design", d); }
})();
