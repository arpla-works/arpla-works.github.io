/* 作品ページ */
(function () {
  "use strict";
  const T = window.Tanpen;
  const content = document.getElementById("content");
  const id = new URLSearchParams(location.search).get("id");
  const MODE_KEY = "tanpen-reading-mode";

  T.loadAll().then(async (D) => {
    const w = D.works.find((x) => x.id === id);
    if (!w) {
      content.innerHTML = '<p class="notice">この作品は見つかりませんでした。<a href="index.html">作品一覧</a>から選んでください。</p>';
      return;
    }
    const i = D.issueById[w.issue];
    document.title = w.title + "（" + w.author + "）｜" + D.site.orgNameJa;

    const dist = i.distribution && i.distribution.url
      ? '<a href="' + T.esc(i.distribution.url) + '">' + T.esc(i.distribution.label || "頒布情報を見る") + "</a>" : "";

    let bodyHTML = "";
    if (w.bodyMode !== "none") {
      let text = null;
      try {
        const res = await fetch(w.body, { cache: "no-cache" });
        if (res.ok) text = await res.text();
      } catch (e) { /* 下で扱う */ }
      const mode = localStorage.getItem(MODE_KEY) === "vertical" ? "vertical" : "horizontal";
      bodyHTML =
        '<div class="reader-bar"><h2>本文</h2>' +
          '<div class="toggle" role="group" aria-label="表示方向">' +
            '<button type="button" data-mode="horizontal" aria-pressed="' + (mode === "horizontal") + '">横書き</button>' +
            '<button type="button" data-mode="vertical" aria-pressed="' + (mode === "vertical") + '">縦書き</button>' +
          "</div></div>" +
        (text == null
          ? '<p class="text-note">本文を読み込めませんでした。</p>'
          : '<div class="text-frame ' + mode + '" id="text-frame"><div class="text ' + mode + '" id="text" lang="ja">' +
              // 縦書きのときだけ、本文の頭（いちばん右）に扉のような作品名・著者名を出す
              '<div class="text-head" aria-hidden="true"><p class="text-title">' + T.esc(w.title) + "</p>" +
              '<p class="text-author">' + T.esc(w.author) + "</p></div>" +
              renderText(text) + "</div></div>") +
        (w.bodyMode === "excerpt"
          ? '<p class="text-note">続きは『' + T.esc(i.title) + "』でお読みいただけます。" + (dist ? "　" + dist : "") + "</p>"
          : "");
    }

    const siblings = D.works.filter((x) => x.issue === w.issue && x.id !== w.id);

    content.innerHTML =
      '<div class="work-hero">' +
        '<span class="tile-art" style="--t-bg:' + i.bg + ";--t-fg:" + i.fg + '" aria-hidden="true"></span>' +
        '<div class="work-head">' +
          "<h1>『" + T.esc(w.title) + "』</h1>" +
          '<dl class="facts"><dt>著者</dt><dd>' + T.filterLink("author", w.author) + "</dd><dt>制作年</dt><dd>" + T.filterLink("year", w.year) +
          "</dd><dt>ジャンル</dt><dd>" + T.esc(w.genres.join("・")) + "</dd></dl>" +
          (w.synopsis ? '<p class="synopsis">' + T.esc(w.synopsis) + "</p>" : "") +
        "</div>" +
      "</div>" +
      bodyHTML +
      '<div class="work-issue">' +
        '<div class="issue-card">' +
          '<img src="' + T.esc(i.cover) + '" alt="' + T.esc(i.title) + 'の表紙" width="140" height="197" loading="lazy">' +
          '<div class="issue-meta"><span>収録</span><strong>' + T.esc(i.title) + "</strong><span>" + T.esc(T.issueMeta(i)) + "</span>" + dist + "</div>" +
        "</div>" +
        (siblings.length
          ? '<section class="siblings" aria-labelledby="sib-h"><h2 id="sib-h">同じ収録誌の作品</h2><ul class="grid">' +
            siblings.map((x) => "<li>" + T.tileHTML(x, i, { hideMeta: true }) + "</li>").join("") + "</ul></section>"
          : "") +
      "</div>";

    const t = document.getElementById("text");
    const frame = document.getElementById("text-frame");
    if (t) {
      t.addEventListener("scroll", updateFade, { passive: true });
      window.addEventListener("resize", updateFade);
      if (t.classList.contains("vertical")) scrollToStart();
    }

    content.querySelectorAll(".toggle button").forEach((b) => {
      b.addEventListener("click", () => {
        const m = b.dataset.mode;
        localStorage.setItem(MODE_KEY, m);
        content.querySelectorAll(".toggle button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        if (t) {
          [t, frame].forEach((el) => { el.classList.remove("horizontal", "vertical"); el.classList.add(m); });
          if (m === "vertical") scrollToStart(); else updateFade();
        }
      });
    });

    /* 縦書きの本文欄を冒頭（いちばん右）に合わせる。
       scrollLeft の始点はブラウザで 0 だったり負の値だったりするので、決め打ちせず
       「先頭の要素の右端」と「本文欄の内側の右端」のずれだけ動かす。本文欄の中だけを動かし、ページは動かさない */
    function scrollToStart() {
      const first = t.firstElementChild;
      const box = t.getBoundingClientRect();
      const padRight = parseFloat(getComputedStyle(t).paddingRight) || 0;
      t.scrollLeft += first.getBoundingClientRect().right - (box.right - padRight);
      updateFade();
    }

    /* 左端（続き側）のグラデーションは、まだ左に続きがあるときだけ出す */
    function updateFade() {
      const last = t.lastElementChild;
      const more = t.classList.contains("vertical") && last &&
        last.getBoundingClientRect().left < t.getBoundingClientRect().left - 1;
      frame.classList.toggle("has-more", !!more);
    }
  }).catch((err) => T.showError(content, err));

  /* 本文テキスト → HTML
     ・1行＝1段落。空行は一行空き。行頭の全角スペースはそのまま字下げ。
     ・ルビ：｜親文字《よみ》 または 漢字《よみ》（青空文庫式） */
  function renderText(src) {
    const KANJI = "[々〆〇ヶ\\u3400-\\u4DBF\\u4E00-\\u9FFF\\uF900-\\uFAFF]";
    const reBar = /｜([^｜《》\n]+?)《([^《》\n]+?)》/g;
    const reKanji = new RegExp("(" + KANJI + "+)《([^《》\\n]+?)》", "g");
    return src.replace(/\r\n?/g, "\n").replace(/\n+$/, "").split("\n").map((line) => {
      if (line.trim() === "") return '<p class="blank"></p>';
      let h = T.esc(line);
      h = h.replace(reBar, "<ruby>$1<rt>$2</rt></ruby>");
      h = h.replace(reKanji, "<ruby>$1<rt>$2</rt></ruby>");
      return "<p>" + h + "</p>";
    }).join("");
  }
})();
