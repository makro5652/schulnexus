/* Neuanmeldung: Adressfelder ein-/ausblenden, Vorlagen nach Jahrgang vorschlagen, Ablagefläche für Dateien, Sofortspeichern. */
(function () {
  "use strict";
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // Adresse der Kontaktperson nur zeigen, wenn sie vom Kind abweicht
  $$("fieldset.an-kontakt").forEach(function (fs) {
    var haken = fs.querySelector('input[name$="adresse_wie_kind"]');
    var adresse = fs.querySelector("[data-adresse]");
    if (!haken || !adresse) return;
    var fehler = adresse.querySelector(".fehler");
    function zeigen() { adresse.hidden = haken.checked && !fehler; }
    haken.addEventListener("change", function () { fehler = null; zeigen(); });
    zeigen();
  });

  // Checklisten-Vorlagen passend zum Jahrgang vorschlagen (manuelle Auswahl hat Vorrang)
  var jahrgang = document.getElementById("id_jahrgang");
  var vorlagen = $$('input[name="vorlagen"]');
  vorlagen.forEach(function (v) { v.addEventListener("change", function () { v.dataset.beruehrt = "1"; }); });
  if (jahrgang && vorlagen.length) {
    jahrgang.addEventListener("change", function () {
      var jg = parseInt(jahrgang.value, 10);
      vorlagen.forEach(function (v) {
        if (v.dataset.beruehrt || v.dataset.standard === "1" || (!v.dataset.von && !v.dataset.bis)) return;
        var von = parseInt(v.dataset.von || "0", 10), bis = parseInt(v.dataset.bis || "99", 10);
        v.checked = !isNaN(jg) && jg >= von && jg <= bis;
      });
    });
  }

  // Ablagefläche: Dateinamen anzeigen, Ziehen und Ablegen
  $$("[data-ablage]").forEach(function (zone) {
    var input = zone.querySelector('input[type="file"]');
    var namen = zone.querySelector("[data-dateinamen]");
    if (!input) return;
    function anzeigen() {
      if (!namen) return;
      namen.textContent = Array.prototype.map.call(input.files || [], function (f) { return f.name; }).join(" · ");
    }
    input.addEventListener("change", anzeigen);
    ["dragenter", "dragover"].forEach(function (t) {
      zone.addEventListener(t, function (e) { e.preventDefault(); zone.classList.add("ablegen"); });
    });
    ["dragleave", "drop"].forEach(function (t) {
      zone.addEventListener(t, function () { zone.classList.remove("ablegen"); });
    });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files.length) { input.files = e.dataTransfer.files; anzeigen(); }
    });
  });

  // Formulare mit data-sofort speichern bei jeder Änderung
  $$("form[data-sofort]").forEach(function (f) {
    f.addEventListener("change", function () { f.requestSubmit ? f.requestSubmit() : f.submit(); });
  });
})();
