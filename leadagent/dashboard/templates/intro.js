// VidyaDesk first-visit intro (approved mockup: docs/specs/2026-10-20-dashboard-redesign/intro-animation.html).
// Plays once per browser; never for reduced-motion users; any failure leaves the Home page usable.
(function () {
  var KEY = "vidyadesk-intro-seen";
  var intro = document.getElementById("intro");
  if (!intro) return;
  var seen = false;
  try { seen = window.localStorage.getItem(KEY) === "1"; } catch (e) { /* storage blocked: treat as not seen */ }
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (seen || reduced) return;

  var body = document.body, finished = false;

  function remember() {
    try { window.localStorage.setItem(KEY, "1"); } catch (e) { /* nothing to do */ }
  }

  function buildUp() {
    body.classList.add("intro-build");
    document.querySelectorAll("main .stat[data-count]").forEach(function (card) {
      var out = card.querySelector("b"), to = parseInt(card.getAttribute("data-count"), 10) || 0, n = 0;
      if (!out || to <= 0) return;
      var step = Math.max(1, Math.round(to / 12));
      out.textContent = "0";
      var timer = setInterval(function () {
        n = Math.min(to, n + step);
        out.textContent = n;
        if (n >= to) clearInterval(timer);
      }, 90);
    });
    var rows = document.querySelectorAll("main .row, main .empty, main .more");
    rows.forEach(function (el, i) {
      el.style.animationDelay = (0.6 + i * 0.15) + "s";
    });
    // Once every row has risen, drop the animation styles so the page's final look never depends on them.
    setTimeout(function () { body.classList.remove("intro-build"); }, 1200 + rows.length * 150);
  }

  function finish(build) {
    if (finished) return;
    finished = true;
    remember();
    intro.hidden = true;
    body.classList.remove("intro-play");
    if (build) buildUp();
  }

  try {
    var quote = intro.querySelector(".intro-quote");
    var words = quote.textContent.trim().split(/\s+/);
    quote.textContent = "";
    words.forEach(function (word, i) {
      var span = document.createElement("span");
      span.className = "w";
      span.textContent = word;
      span.style.animationDelay = (2.0 + i * 0.13) + "s";
      quote.appendChild(span);
      quote.appendChild(document.createTextNode(" "));
    });
    intro.querySelector(".intro-by").style.animationDelay = (2.2 + words.length * 0.13) + "s";
    intro.querySelector(".intro-skip").addEventListener("click", function (event) {
      event.preventDefault();
      finish(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") finish(false);
    });
    body.classList.add("intro-play");
    intro.hidden = false;
    intro.querySelector(".intro-skip").focus();
    setTimeout(function () { intro.classList.add("leaving"); }, 5200);
    setTimeout(function () { finish(true); }, 5800);
  } catch (e) {
    finish(false); // never leave the overlay on screen
  }
})();
