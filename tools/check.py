#!/usr/bin/env python3
"""データの点検。更新のたびに実行する:  python3 tools/check.py
エラーがあれば終了コード1。警告は表示のみ。"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors, warnings = [], []
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def load(name):
    try:
        with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        errors.append(f"data/{name} を読めません: {e}")
        return None


def exists(rel):
    return os.path.isfile(os.path.join(ROOT, rel))


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def rgb_dist(a, b):
    return sum((int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) ** 2 for i in (1, 3, 5)) ** 0.5


site, issues, works = load("site.json"), load("issues.json"), load("works.json")

if site:
    if site.get("theme") not in ("dark", "light"):
        errors.append('site.json: theme は "dark" か "light"')
    if site.get("order") not in ("manual", "random"):
        errors.append('site.json: order は "manual" か "random"')

issue_ids = set()
if issues:
    for n, i in enumerate(issues):
        where = f"issues.json[{n}] ({i.get('id', '?')})"
        for k in ("id", "title", "number", "date", "bg", "fg", "cover"):
            if k not in i or i[k] in ("", None):
                errors.append(f"{where}: {k} がありません")
        if i.get("id") in issue_ids:
            errors.append(f"{where}: id が重複しています")
        issue_ids.add(i.get("id"))
        if i.get("id") and not ID.match(i["id"]):
            errors.append(f"{where}: id は半角英小文字・数字・ハイフンのみ")
        if i.get("date") and not DATE.match(i["date"]):
            errors.append(f"{where}: date は YYYY-MM-DD")
        for k in ("bg", "fg"):
            if i.get(k) and not HEX.match(i[k]):
                errors.append(f"{where}: {k} は #RRGGBB 形式")
        if i.get("cover") and not exists(i["cover"]):
            errors.append(f"{where}: 表紙画像 {i['cover']} がありません")
    # 号どうしの配色が似すぎていないか
    for a in range(len(issues)):
        for b in range(a + 1, len(issues)):
            A, B = issues[a], issues[b]
            if all(HEX.match(A.get(k, "")) and HEX.match(B.get(k, "")) for k in ("bg", "fg")):
                d = min(rgb_dist(A["bg"], B["bg"]) + rgb_dist(A["fg"], B["fg"]),
                        rgb_dist(A["bg"], B["fg"]) + rgb_dist(A["fg"], B["bg"]))
                if d < 120:
                    warnings.append(f"{A['id']} と {B['id']} の配色が近く、一覧で見分けにくい可能性があります（距離 {d:.0f}）")

work_ids = set()
if works:
    for n, w in enumerate(works):
        where = f"works.json[{n}] ({w.get('id', '?')})"
        for k in ("id", "issue", "title", "author", "year", "genres", "bodyMode"):
            if k not in w or w[k] in ("", None, []):
                errors.append(f"{where}: {k} がありません")
        if w.get("id") in work_ids:
            errors.append(f"{where}: id が重複しています")
        work_ids.add(w.get("id"))
        if w.get("id") and not ID.match(w["id"]):
            errors.append(f"{where}: id は半角英小文字・数字・ハイフンのみ")
        if w.get("issue") and w["issue"] not in issue_ids:
            errors.append(f"{where}: issue '{w['issue']}' は issues.json にありません")
        if not isinstance(w.get("genres", []), list):
            errors.append(f"{where}: genres は配列 [\"...\"]")
        if w.get("bodyMode") not in ("full", "excerpt", "none"):
            errors.append(f'{where}: bodyMode は "full" / "excerpt" / "none"')
        if w.get("bodyMode") in ("full", "excerpt"):
            if not w.get("body"):
                errors.append(f"{where}: body（本文ファイル）がありません")
            elif not exists(w["body"]):
                errors.append(f"{where}: 本文ファイル {w['body']} がありません")
        if "[" in str(w.get("title", "")) or "[" in str(w.get("author", "")) or "[" in str(w.get("synopsis", "")):
            warnings.append(f"{where}: 仮の値（[...]）が残っています")
    used = {w.get("issue") for w in works}
    for i in issue_ids - used:
        warnings.append(f"収録誌 {i} に作品が1つもありません")

for w in warnings:
    print("警告:", w)
for e in errors:
    print("エラー:", e)
print(f"作品 {len(work_ids)} 件 / 収録誌 {len(issue_ids)} 件 — エラー {len(errors)}、警告 {len(warnings)}")
sys.exit(1 if errors else 0)
