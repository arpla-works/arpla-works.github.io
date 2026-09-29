# 短編一覧サイト

思想・哲学・文学・芸術の会の文芸同人誌に収録された短編を、1作品ずつ並べて見せる静的サイトです。
HTML・CSS・JavaScriptだけで動き、サーバー側の仕組みは不要です。

## 中身

```
index.html          作品一覧（絞り込み・選択中の作品・収録誌一覧）
work.html           作品ページ（work.html?id=作品ID）
assets/style.css    見た目（黒／白テーマの色もここ）
assets/common.js    共通処理
assets/list.js      一覧ページの処理
assets/work.js      作品ページの処理（本文の表示、横書き／縦書き切り替え）
data/site.json      サイト全体の設定（テーマ、並び順）
data/issues.json    収録誌（号）の一覧と、号ごとの2色
data/works.json     作品の一覧
texts/              作品の本文（1作品1ファイル、UTF-8のテキスト）
covers/             収録誌の表紙画像
tools/check.py      データの点検スクリプト
CLAUDE.md           Claude（Claude Code）向けの運営手順
```

**現在のデータはサンプルです。** 作品名・著者名・ジャンル・あらすじ・本文の多くは仮の値（`[作品名]` など）です。

## 公開のしかた（GitHub Pages）

1. GitHubで新しいリポジトリを作り、このフォルダの中身をすべて置く（`.nojekyll` も含める）。
2. リポジトリの Settings → Pages で、Source を「Deploy from a branch」、ブランチを `main`、フォルダを `/ (root)` にする。
3. 数分後に `https://<ユーザー名>.github.io/<リポジトリ名>/` で公開される。
4. 独自ドメインを使う場合は、同じ画面の Custom domain に設定する。

以後は、リポジトリに変更が入るたびに自動で公開ページが更新されます。

## 手元で確認する

データをファイルから読み込むため、`index.html` をダブルクリックで開くと表示されません。フォルダ内で次を実行し、ブラウザで `http://localhost:8000` を開いてください。

```
python3 -m http.server 8000
```

## 設定

`data/site.json`

- `theme`：`"dark"`（黒）または `"light"`（白）
- `order`：`"manual"`（works.json に書いた順）または `"random"`（表示のたびにシャッフル）

## 本文の書き方

- 1行が1段落になります。行頭の全角スペースはそのまま字下げになります。
- 空行はそのまま一行空きになります。
- ルビは青空文庫式です。`｜親文字《よみ》`、または漢字の直後に `《よみ》`。
