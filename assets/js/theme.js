/* Theme toggle (light/dark) with persistence + system-preference default.
   Also handles the mobile nav toggle. */
(function () {
  var KEY = "wb-theme";
  var root = document.documentElement;

  function systemPref() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light" : "dark";
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    var btn = document.querySelector(".theme-toggle");
    if (btn) {
      btn.textContent = theme === "light" ? "🌙" : "☀️";
      btn.setAttribute("aria-label", "Switch to " + (theme === "light" ? "dark" : "light") + " theme");
    }
  }

  // Initialise as early as possible
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  apply(saved || systemPref());

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.querySelector(".theme-toggle");
    if (btn) {
      apply(root.getAttribute("data-theme")); // set the icon
      btn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
        apply(next);
        try { localStorage.setItem(KEY, next); } catch (e) {}
      });
    }

    var navToggle = document.querySelector(".nav-toggle");
    var navLinks = document.querySelector(".nav-links");
    if (navToggle && navLinks) {
      navToggle.addEventListener("click", function () {
        navLinks.classList.toggle("open");
      });
      navLinks.addEventListener("click", function (e) {
        if (e.target.tagName === "A") navLinks.classList.remove("open");
      });
    }
  });
})();
