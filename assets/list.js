/* 一覧ページ */
(function () {
  "use strict";
  const T = window.Tanpen;
  const wide = window.matchMedia("(min-width: 1024px)");

  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const state = {
    issue: params.get("issue") || "all", genre: params.get("genre") || "all",
    author: params.get("author") || "all", year: params.get("year") || "all", sel: null,
  };
  const FILTER_KEYS = ["issue", "genre", "author", "year"];
  const FILTER_LABELS = { author: "著者", year: "制作年" };

  let D, ordered, genres;

  T.loadAll().then((data) => {
    D = data;
    $("org").textContent = D.site.orgName;
    ordered = D.site.order === "random" ? T.shuffle(D.works) : D.works.slice();

    // ジャンルは作品数の多い順（同数なら登場順）
    const count = {}, first = {};
    D.works.forEach((w, i) => w.genres.forEach((g) => {
      count[g] = (count[g] || 0) + 1;
      if (!(g in first)) first[g] = i;
    }));
    genres = Object.keys(count).sort((a, b) => count[b] - count[a] || first[a] - first[b]);

    if (state.issue !== "all" && !D.issueById[state.issue]) state.issue = "all";
    if (state.genre !== "all" && !(state.genre in count)) state.genre = "all";
    if (state.author !== "all" && !D.works.some((w) => w.author === state.author)) state.author = "all";
    if (state.year !== "all" && !D.works.some((w) => String(w.year) === state.year)) state.year = "all";

    // 著者・制作年のリンク（タイルの説明行と右側の欄）は、ページを移らずにその場で絞り込む
    document.addEventListener("click", (e) => {
      const a = e.target.closest("a.meta-link[data-filter]");
      if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      setFilter(a.dataset.filter, a.dataset.value);
    });

    renderIssues();
    render();
  }).catch((err) => T.showError($("works"), err));

  function setFilter(key, value) {
    state[key] = value;
    const p = new URLSearchParams();
    FILTER_KEYS.forEach((k) => { if (state[k] !== "all") p.set(k, state[k]); });
    const q = p.toString();
    history.replaceState(null, "", q ? "?" + q : location.pathname);
    render();
  }

  function chip(label, pressed, onClick, swatch) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.setAttribute("aria-pressed", pressed ? "true" : "false");
    if (swatch) {
      const s = document.createElement("span");
      s.className = "swatch";
      s.setAttribute("aria-hidden", "true");
      s.style.setProperty("--sw-bg", swatch.bg);
      s.style.setProperty("--sw-fg", swatch.fg);
      b.appendChild(s);
    }
    b.appendChild(document.createTextNode(label));
    b.addEventListener("click", onClick);
    return b;
  }

  function render() {
    // チップ
    const ic = $("issue-chips"); ic.innerHTML = "";
    ic.appendChild(chip("すべて", state.issue === "all", () => setFilter("issue", "all")));
    D.issues.forEach((i) => ic.appendChild(chip(i.title, state.issue === i.id, () => setFilter("issue", i.id), i)));

    const gc = $("genre-chips"); gc.innerHTML = "";
    gc.appendChild(chip("すべて", state.genre === "all", () => setFilter("genre", "all")));
    genres.forEach((g) => gc.appendChild(chip(g, state.genre === g, () => setFilter("genre", g))));

    // 作品
    const list = ordered.filter((w) =>
      (state.issue === "all" || w.issue === state.issue) &&
      (state.genre === "all" || w.genres.indexOf(state.genre) >= 0) &&
      (state.author === "all" || w.author === state.author) &&
      (state.year === "all" || String(w.year) === state.year));

    $("count").textContent = list.length + " 作品";
    renderActiveFilters();
    $("empty").hidden = list.length > 0;
    $("grid").innerHTML = list.map((w) => "<li>" + T.tileHTML(w, D.issueById[w.issue]) + "</li>").join("");

    if (!list.some((w) => w.id === state.sel)) state.sel = list.length ? list[0].id : null;
    markSelected();
    renderPreview();

    $("grid").querySelectorAll(".tile-art-link, .tile-title").forEach((a) => {
      a.addEventListener("click", (e) => {
        if (!wide.matches) return;          // 狭い画面はそのまま作品ページへ
        e.preventDefault();
        state.sel = a.closest(".tile").dataset.id;
        markSelected();
        renderPreview();
      });
    });
  }

  // 著者・制作年で絞り込んでいる間だけ、作品数の横に解除用のチップを出す
  function renderActiveFilters() {
    const el = $("active-filters");
    el.innerHTML = "";
    ["author", "year"].forEach((k) => {
      if (state[k] === "all") return;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "active-filter";
      b.setAttribute("aria-label", FILTER_LABELS[k] + "「" + state[k] + "」の絞り込みを解除");
      b.innerHTML = T.esc(FILTER_LABELS[k] + "：" + state[k]) + '<span aria-hidden="true">×</span>';
      b.addEventListener("click", () => setFilter(k, "all"));
      el.appendChild(b);
    });
    el.hidden = !el.children.length;
  }

  function markSelected() {
    $("grid").querySelectorAll(".tile").forEach((a) => {
      if (a.dataset.id === state.sel) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
  }

  function renderPreview() {
    const el = $("preview");
    const w = D.works.find((x) => x.id === state.sel);
    if (!w) { el.innerHTML = ""; return; }
    const i = D.issueById[w.issue];
    const dist = i.distribution && i.distribution.url
      ? '<a class="btn" href="' + T.esc(i.distribution.url) + '">' + T.esc(i.distribution.label || "収録誌の頒布情報") + "</a>" : "";
    const read = w.bodyMode === "none" ? "" :
      '<a class="btn btn-primary" href="work.html?id=' + encodeURIComponent(w.id) + '">本文を読む</a>';
    el.innerHTML =
      '<div class="preview-issue">' +
        '<img src="' + T.esc(i.cover) + '" alt="' + T.esc(i.title) + 'の表紙" width="176" height="248">' +
        '<div class="issue-meta"><span>収録</span><strong>' + T.esc(i.title) + "</strong><span>" + T.esc(T.issueMeta(i)) + "</span></div>" +
      "</div>" +
      '<div class="preview-body">' +
        "<h2>『" + T.esc(w.title) + "』</h2>" +
        '<dl class="facts"><dt>著者</dt><dd>' + T.filterLink("author", w.author) + "</dd><dt>制作年</dt><dd>" + T.filterLink("year", w.year) +
        "</dd><dt>ジャンル</dt><dd>" + T.esc(w.genres.join("・")) + "</dd></dl>" +
        (w.synopsis ? '<p class="synopsis">' + T.esc(w.synopsis) + "</p>" : "") +
      "</div>" +
      '<div class="actions">' + read + dist + "</div>";
  }

  function renderIssues() {
    $("issue-list").innerHTML = D.issues.map((i) => {
      const dist = i.distribution && i.distribution.url
        ? '<a href="' + T.esc(i.distribution.url) + '">' + T.esc(i.distribution.label || "頒布情報を見る") + "</a>" : "";
      return '<li class="issue-card">' +
        '<img src="' + T.esc(i.cover) + '" alt="' + T.esc(i.title) + 'の表紙" width="140" height="197" loading="lazy">' +
        '<div class="issue-meta"><strong>' + T.esc(i.title) + "</strong><span>" + T.esc(T.issueMeta(i)) + "</span>" +
        '<a href="?issue=' + encodeURIComponent(i.id) + '#works">収録作品を見る</a>' + dist + "</div></li>";
    }).join("");
    // 「収録作品を見る」は同じページ内なので絞り込みを直接切り替える
    $("issue-list").querySelectorAll('a[href^="?issue="]').forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const id = new URLSearchParams(a.getAttribute("href").split("#")[0]).get("issue");
        state.genre = "all";
        setFilter("issue", id);
        $("works").scrollIntoView();
      });
    });
  }
})();
