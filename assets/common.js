/* 共通：データ読み込みと小さな道具 */
(function () {
  "use strict";

  /* 背景の黒／白。訪問者の選択（localStorage）を site.json の theme より優先する。
     保存済みの選択は各HTMLの head 内スクリプトが描画前に反映している。 */
  const THEME_KEY = "tanpen-theme";

  function savedTheme() {
    try {
      const t = localStorage.getItem(THEME_KEY);
      return t === "dark" || t === "light" ? t : null;
    } catch (e) { return null; }
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll(".theme-toggle button").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.themeValue === theme));
    });
  }

  applyTheme(savedTheme() || document.documentElement.dataset.theme);
  document.querySelectorAll(".theme-toggle button").forEach((b) => {
    b.addEventListener("click", () => {
      try { localStorage.setItem(THEME_KEY, b.dataset.themeValue); } catch (e) { /* 保存できなくても表示は切り替える */ }
      applyTheme(b.dataset.themeValue);
    });
  });
  // 別のタブで切り替えたときも合わせる
  window.addEventListener("storage", (e) => { if (e.key === THEME_KEY && savedTheme()) applyTheme(savedTheme()); });

  async function getJSON(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(path + " を読み込めませんでした（" + res.status + "）");
    return res.json();
  }

  async function loadAll() {
    const [site, issues, works] = await Promise.all([
      getJSON("data/site.json"),
      getJSON("data/issues.json"),
      getJSON("data/works.json"),
    ]);
    applyTheme(savedTheme() || (site.theme === "light" ? "light" : "dark"));
    const issueById = {};
    issues.forEach((i) => { issueById[i.id] = i; });
    return { site, issues, works, issueById };
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function formatDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return iso || "";
    return Number(m[1]) + "年" + Number(m[2]) + "月" + Number(m[3]) + "日";
  }

  function issueMeta(issue) {
    return "文芸同人誌" + issue.number + "号　" + formatDate(issue.date);
  }

  /* 正方形タイル（円）。href を渡すとリンクになる */
  function tileHTML(work, issue, opts) {
    opts = opts || {};
    const style = "--t-bg:" + issue.bg + ";--t-fg:" + issue.fg;
    const meta = opts.hideMeta ? "" :
      '<span class="tile-meta">' + esc(work.author) + "　／　" + esc(work.genres.join("・")) + "</span>";
    return '<a class="tile" href="work.html?id=' + encodeURIComponent(work.id) + '" data-id="' + esc(work.id) + '">' +
      '<span class="tile-art" style="' + style + '" aria-hidden="true"></span>' +
      '<span class="tile-cap"><span class="tile-title">' + esc(work.title) + "</span>" + meta + "</span></a>";
  }

  function shuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function showError(el, err) {
    el.innerHTML = '<p class="notice">読み込みに失敗しました。' + esc(err.message) +
      "<br>ファイルを直接開いている場合は、ローカルサーバー経由で表示してください（README参照）。</p>";
  }

  window.Tanpen = { loadAll, esc, formatDate, issueMeta, tileHTML, shuffle, showError };
})();
