// TechRadar AI — minimal frontend JS
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    animateCards();
  });

  function animateCards() {
    var cards = document.querySelectorAll(".card");
    if (!cards.length || !("IntersectionObserver" in window)) return;

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08 }
    );

    cards.forEach(function (card) {
      card.style.opacity = "0";
      card.style.transform = "translateY(18px)";
      card.style.transition = "opacity 0.45s ease, transform 0.45s ease";
      observer.observe(card);
    });
  }

  var style = document.createElement("style");
  style.textContent = ".card.visible { opacity: 1 !important; transform: translateY(0) !important; }";
  document.head.appendChild(style);
})();
