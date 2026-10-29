// Academy widgets: the loop map, the explainer stepper, the chooser and the symptom finder.
// Each page declares its widgets in markup (data-* attributes, see tests/test_widgets.py); this
// file only reads them. Bound through Material's document$ so they survive instant navigation.
// Without JavaScript every widget still reads top to bottom: steps as a list, every target shown.
(function () {
  function ids(value) {
    return (value || "").split(/\s+/).filter(Boolean);
  }

  function button(label, cls) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "academy-btn" + (cls ? " " + cls : "");
    b.textContent = label;
    return b;
  }

  // Animate children from their old to their new position after `mutate` reorders them (FLIP).
  function flip(container, mutate) {
    var items = Array.prototype.slice.call(container.children);
    var first = items.map(function (n) { return n.getBoundingClientRect(); });
    mutate();
    items.forEach(function (n, i) {
      var b = n.getBoundingClientRect();
      var dx = first[i].left - b.left, dy = first[i].top - b.top;
      if ((dx || dy) && n.animate) {
        n.animate([{ transform: "translate(" + dx + "px," + dy + "px)" }, { transform: "none" }], { duration: 650, easing: "cubic-bezier(.6,.05,.2,1)" });
      }
    });
  }

  function initLoopMap(root) {
    root.querySelectorAll(".loop-stage").forEach(function (s) {
      s.classList.toggle("is-current", s.dataset.stage === root.dataset.current);
    });
  }

  function initExplainer(root) {
    if (root.dataset.bound) return;
    root.dataset.bound = "1";
    var steps = Array.prototype.slice.call(root.querySelectorAll(".explainer-steps > li"));
    var stage = root.querySelector(".explainer-stage");
    if (!steps.length || !stage) return;
    var byId = function (id) { return root.querySelector("#" + CSS.escape(id)); };
    var targets = [];
    steps.forEach(function (s) {
      ["show", "hot", "bad"].forEach(function (k) {
        ids(s.dataset[k]).forEach(function (id) { if (targets.indexOf(id) < 0) targets.push(id); });
      });
    });

    // group-by: rows carry data-customer; order them per customer when a step says data-group.
    var group = root.querySelector("[data-group-by]");
    if (group) {
      var customers = [];
      Array.prototype.forEach.call(group.children, function (n, i) {
        var c = n.dataset.customer;
        if (customers.indexOf(c) < 0) customers.push(c);
        var label = n.classList.contains("log-group-label");
        n.style.setProperty("--group-order", customers.indexOf(c) * 100 + (label ? 0 : i + 1));
      });
    }

    var bar = document.createElement("div");
    bar.className = "explainer-bar";
    var back = button("Back"), next = button("Next →", "is-primary"), reset = button("Reset");
    var dots = document.createElement("div");
    dots.className = "explainer-dots";
    steps.forEach(function () { dots.appendChild(document.createElement("span")); });
    bar.append(back, next, reset, dots);
    var caption = document.createElement("div");
    caption.className = "explainer-caption";
    caption.setAttribute("aria-live", "polite");
    stage.before(bar);
    stage.after(caption);
    root.classList.add("is-interactive");

    var at = 0;
    function render() {
      var shown = [], bad = [], grouped = false;
      for (var k = 0; k <= at; k++) {
        shown = shown.concat(ids(steps[k].dataset.show));
        bad = bad.concat(ids(steps[k].dataset.bad));
        if ("group" in steps[k].dataset) grouped = true;
      }
      targets.forEach(function (id) {
        var t = byId(id);
        if (!t) return;
        t.classList.toggle("is-hidden", shown.indexOf(id) < 0);
        t.classList.toggle("is-bad", bad.indexOf(id) >= 0);
        t.classList.toggle("is-hot", ids(steps[at].dataset.hot).indexOf(id) >= 0);
      });
      if (group && group.classList.contains("is-grouped") !== grouped) {
        flip(group, function () { group.classList.toggle("is-grouped", grouped); });
      }
      caption.innerHTML = steps[at].innerHTML;
      Array.prototype.forEach.call(dots.children, function (d, i) { d.classList.toggle("is-on", i <= at); });
      back.disabled = at === 0;
      next.disabled = at === steps.length - 1;
    }
    back.onclick = function () { at = Math.max(0, at - 1); render(); };
    next.onclick = function () { at = Math.min(steps.length - 1, at + 1); render(); };
    reset.onclick = function () { at = 0; render(); };
    render();
  }

  function initChooser(root) {
    if (root.dataset.bound) return;
    root.dataset.bound = "1";
    var why = root.querySelector(".chooser-why");
    var options = root.querySelectorAll("[data-lights]");
    root.classList.add("is-interactive");
    options.forEach(function (opt) {
      opt.addEventListener("click", function () {
        options.forEach(function (o) { o.classList.toggle("is-on", o === opt); });
        root.querySelectorAll(".chooser-way").forEach(function (w) { w.classList.remove("is-lit"); });
        ids(opt.dataset.lights).forEach(function (id) {
          var w = root.querySelector("#" + CSS.escape(id));
          if (w) w.classList.add("is-lit");
        });
        var reason = opt.querySelector(".chooser-reason");
        if (why) why.textContent = reason ? reason.textContent : opt.dataset.why;
      });
    });
  }

  // Ticked symptoms light their stages; the result lists the lit stages in loop order.
  function initSymptomFinder(root) {
    if (root.dataset.bound) return;
    root.dataset.bound = "1";
    var stages = root.querySelectorAll(".loop-stage");
    var result = root.querySelector(".symptom-result");
    function render() {
      var count = {};
      root.querySelectorAll("input[data-stage]:checked").forEach(function (box) {
        count[box.dataset.stage] = (count[box.dataset.stage] || 0) + 1;
      });
      var lit = [];
      stages.forEach(function (s) {
        var on = !!count[s.dataset.stage];
        s.classList.toggle("is-lit", on);
        if (on) lit.push(s);
      });
      if (!result) return;
      result.innerHTML = "";
      if (!lit.length) return;
      var head = document.createElement("p");
      head.innerHTML = "<strong>Start here, in this order:</strong>";
      var list = document.createElement("ol");
      lit.forEach(function (s) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = s.getAttribute("href");
        a.textContent = s.textContent;
        var n = count[s.dataset.stage];
        li.append(a, document.createTextNode(" (" + n + (n === 1 ? " symptom)" : " symptoms)")));
        list.appendChild(li);
      });
      result.append(head, list);
    }
    root.addEventListener("change", render);
    render();
  }

  document$.subscribe(function () {
    document.querySelectorAll("[data-symptom-finder]").forEach(initSymptomFinder);
    document.querySelectorAll(".loop-map").forEach(initLoopMap);
    document.querySelectorAll("[data-explainer]").forEach(initExplainer);
    document.querySelectorAll("[data-chooser]").forEach(initChooser);
  });
})();
