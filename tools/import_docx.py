#!/usr/bin/env python3
"""同人誌のWord原稿（.docx）を、サイト用の本文ファイルと作品データに変換する。

使い方:
  python3 tools/import_docx.py 原稿.docx --issue ana
  python3 tools/import_docx.py 原稿.docx --issue ana --dry-run     # 書き込まずに分割結果だけ確認

やること:
  - 作品ごとに texts/<issue>-01.txt, -02.txt … を書き出す（既存ファイルは上書き）
  - data/works.json の、その号（--issue）の作品をすべて置き換える（他の号の作品はそのまま）
    ※ 同じIDの作品がすでにあれば、著者名・制作年・ジャンル・あらすじ・公開範囲はそちらを引き継ぐ
      （仮の値「[...]」や空欄は引き継がない。作品名が仮の値のサンプル作品からは何も引き継がない）。
      本文と作品名は原稿から作り直す。並び順は元の位置を保ち、新しい作品は末尾に足す
    ※ 新しい作品のジャンルとあらすじは空で作る。あとで必ず埋めること（check.py がエラーにする）

作品の区切りの見つけ方:
  - 段落スタイル名が「タイトル」の段落＝作品名、その直後の「著者」スタイルの段落＝著者名
  - スタイルが使われていない原稿は --titles "作品A,作品B,…" で作品名を本文の登場順に指定する
    （この場合、作品名の次の段落を著者名とみなす。著者行がない作品は --no-author-line で指定）
  - 最後の作品は、奥付（改ページ後に「発行」を含む行が続く箇所）の手前で終わる

変換のきまり（サイトの本文形式に合わせる）:
  - 1段落＝1行。空段落は一行空き（連続していてもそのまま残す）
  - 段落の前後に一行分以上の空き（段落前後の間隔）があれば一行空きにする（章節見出しの前など）
  - 改ページは反映しない（紙面の都合の切れ目とみなす）。空きが必要な箇所は data/import_rules.json で作品ごとに指定する
  - 原稿で字下げされている段落は、字下げの文字数（左インデント＋1行目インデント）だけ行頭に全角スペースを付ける。章節見出しも同様。作品名・著者名の行は対象外
  - Wordのルビ（ルビ機能／EQフィールドの両方）は ｜親文字《よみ》 に変換する
  - 文字ボックスは、Wordが互換用に二重に持っている片方（Fallback）を無視して1回だけ取り出す
  - タブは全角スペースに置き換える
"""
import argparse, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
EQ_RUBY = re.compile(r"\\o\s*\\ad\s*\(\s*\\s\s*\\up\s*-?\d+\s*\((.*?)\)\s*,(.*)\)\s*$", re.S)
NOINDENT_STYLE_NAMES = {"タイトル", "著者"}


def load(docx):
    with zipfile.ZipFile(docx) as z:
        doc = ET.fromstring(z.read("word/document.xml"))
        styles = ET.fromstring(z.read("word/styles.xml")) if "word/styles.xml" in z.namelist() else None
    return doc, styles


def style_table(styles):
    table = {}
    if styles is None:
        return table
    for s in styles.iter(W + "style"):
        sid = s.get(W + "styleId")
        name = s.find(W + "name")
        base = s.find(W + "basedOn")
        ind = s.find(".//" + W + "ind")
        sp = s.find(".//" + W + "spacing")
        table[sid] = {
            "spacing": {k[len(W):]: v for k, v in sp.attrib.items()} if sp is not None else {},
            "name": name.get(W + "val") if name is not None else "",
            "base": base.get(W + "val") if base is not None else None,
            "ind": {k[len(W):]: v for k, v in ind.attrib.items()} if ind is not None else {},
        }
    return table


def style_attr(table, sid, group, keys):
    """スタイルを basedOn でさかのぼり、keys の属性値を集める（近いスタイルの値を優先）"""
    found = {}
    for _ in range(10):
        if not sid or sid not in table:
            break
        for k in keys:
            if k not in found and k in table[sid][group]:
                found[k] = table[sid][group][k]
        sid = table[sid]["base"]
    return found


IND_KEYS = ("left", "leftChars", "start", "startChars", "firstLine", "firstLineChars", "hanging", "hangingChars")


def indent_chars(ind):
    """段落の1行目の字下げ量を「文字数」で返す。
    1行目インデントは四捨五入して数える。左インデント（段落全体を下げる指定）は、文字数で指定されていれば四捨五入、
    mm などの長さで指定されていれば端数を切り捨てて足す
    （見出しの「左0.8字ぶんの長さ＋1行目1字」が2字下げにならず、Word上の見た目どおり1字下げになるように）"""
    def amount(chars_key, twips_key):
        if chars_key in ind:
            return int(ind[chars_key]) / 100
        if twips_key in ind:
            return int(ind[twips_key]) / 210  # 10.5pt 前後の本文を想定した概算
        return 0
    if amount("hangingChars", "hanging") > 0:
        return 0
    left = amount("leftChars", "left") or amount("startChars", "start")
    left_in_chars = "leftChars" in ind or "startChars" in ind
    first = amount("firstLineChars", "firstLine")
    return max(0, (round(left) if left_in_chars else int(left + 0.05)) + round(first))


def parents_of(root):
    return {c: p for p in root.iter() for c in p}


def ancestors(el, parent):
    while el in parent:
        el = parent[el]
        yield el


def plain(el):
    out = []
    for c in el.iter():
        if c.tag == W + "t":
            out.append(c.text or "")
        elif c.tag == W + "tab":
            out.append("\t")
        elif c.tag == W + "br" and c.get(W + "type") in (None, "textWrapping"):
            out.append("\n")
    return "".join(out)


def extract(doc, table):
    """本文の段落を、文字列・スタイル名・字下げ・段落前後の空き・改ページの情報とともに返す"""
    body = doc.find(W + "body")
    parent = parents_of(body)
    paras = []
    for p in body.iter(W + "p"):
        anc = list(ancestors(p, parent))
        if any(a.tag == MC + "Fallback" for a in anc):
            continue
        parts, fld = [], None
        for r in p.iter(W + "r"):
            ranc = list(ancestors(r, parent))
            nearest_p = next((a for a in ranc if a.tag == W + "p"), None)
            if nearest_p is not p or any(a.tag == W + "ruby" for a in ranc):
                continue
            rb = r.find(W + "ruby")
            if rb is not None:
                parts.append("｜" + plain(rb.find(W + "rubyBase")) + "《" + plain(rb.find(W + "rt")) + "》")
                continue
            for c in r:
                if c.tag == W + "fldChar":
                    t = c.get(W + "fldCharType")
                    if t == "begin":
                        fld = {"instr": "", "res": "", "mode": "instr"}
                    elif t == "separate" and fld:
                        fld["mode"] = "res"
                    elif t == "end" and fld:
                        ins = fld["instr"].strip()
                        m = EQ_RUBY.search(ins) if ins.startswith("EQ") else None
                        parts.append("｜" + m.group(2).strip() + "《" + m.group(1).strip() + "》" if m else fld["res"])
                        fld = None
                elif c.tag == W + "instrText" and fld:
                    fld["instr"] += c.text or ""
                elif c.tag == W + "t":
                    if fld and fld["mode"] == "res":
                        fld["res"] += c.text or ""
                    elif not fld:
                        parts.append(c.text or "")
                elif c.tag == W + "tab" and not fld:
                    parts.append("\t")
                elif c.tag == W + "br" and not fld:
                    if c.get(W + "type") in (None, "textWrapping"):
                        parts.append("\n")
        ppr = p.find(W + "pPr")
        sid = None
        explicit_ind, explicit_sp = {}, {}
        if ppr is not None:
            ps = ppr.find(W + "pStyle")
            sid = ps.get(W + "val") if ps is not None else None
            ind = ppr.find(W + "ind")
            if ind is not None:
                explicit_ind = {k[len(W):]: v for k, v in ind.attrib.items()}
            sp = ppr.find(W + "spacing")
            if sp is not None:
                explicit_sp = {k[len(W):]: v for k, v in sp.attrib.items()}
        ind = style_attr(table, sid, "ind", IND_KEYS)
        # 段落に直接書かれた値で上書きする。段落側が twips だけで指定していれば、スタイル側の「文字数」指定は使わない
        for k, v in explicit_ind.items():
            ind[k] = v
            if not k.endswith("Chars") and k + "Chars" not in explicit_ind:
                ind.pop(k + "Chars", None)
        sp = style_attr(table, sid, "spacing", ("before", "beforeLines", "after", "afterLines"))
        sp.update(explicit_sp)
        before = int(sp.get("before", 0)) if not sp.get("beforeLines") else int(sp["beforeLines"]) * 2.4
        after = int(sp.get("after", 0)) if not sp.get("afterLines") else int(sp["afterLines"]) * 2.4
        name = table.get(sid, {}).get("name", "") if sid else ""
        page_break = any(b.get(W + "type") == "page" for b in p.iter(W + "br")) or \
            (ppr is not None and ppr.find(W + "sectPr") is not None)
        break_before = ppr is not None and ppr.find(W + "pageBreakBefore") is not None
        paras.append({"text": "".join(parts), "style": name, "indent": indent_chars(ind),
                      "before": before, "after": after, "page_break": page_break, "break_before": break_before})
    return paras


def find_works(paras, titles=None, author_line=True):
    starts = []
    if titles:
        pos = 0
        for t in titles:
            cand = [k for k in range(pos, len(paras)) if paras[k]["text"].strip() == t]
            if not cand:
                sys.exit(f"作品名「{t}」が本文に見つかりません")
            # 目次の行と区別するため、直後の段落が別の作品名でない最初の出現を使う
            i = next((k for k in cand if not any(paras[k + d]["text"].strip() in titles for d in (1, 2, 3) if k + d < len(paras))), cand[0])
            nxt = next((j for j in range(i + 1, len(paras)) if paras[j]["text"].strip()), i + 1)
            author = paras[nxt]["text"].strip() if author_line else ""
            starts.append((i, t, author, (nxt - i + 1) if author_line else 1))
            pos = i + 1
    else:
        for i, para in enumerate(paras):
            txt = para["text"]
            if para["style"] == "タイトル" and txt.strip():
                j = i + 1
                while j < len(paras) and not paras[j]["text"].strip():
                    j += 1
                if j < len(paras) and paras[j]["style"] == "著者":
                    starts.append((i, txt.strip(), paras[j]["text"].strip(), j - i + 1))
                else:
                    starts.append((i, txt.strip(), "", 1))
        # 表紙の書名など、本文の作品でない「タイトル」は著者がないので除外
        starts = [s for s in starts if s[2]] or starts
    if not starts:
        sys.exit("作品の区切りが見つかりません。--titles で作品名を指定してください")
    # 奥付の位置：最後の作品のあと、改ページの直後数行に「発行」がある箇所
    end = len(paras)
    for k in range(starts[-1][0] + 1, len(paras)):
        if paras[k]["page_break"]:
            following = [p["text"] for p in paras[k + 1:k + 8] if p["text"].strip()]
            if any("発行" in t for t in following[:5]):
                end = k + 1 if paras[k]["text"].strip() else k
                break
    works = []
    for n, (i, title, author, skip) in enumerate(starts):
        e = starts[n + 1][0] if n + 1 < len(starts) else end
        works.append((title, author, paras[i + skip:e]))
    return works


LINE = 240        # 段落前後の空き（twips）がこれ以上なら一行空きとみなす
PAGE_BLANKS = 0   # 改ページは反映しない（必要な空きは data/import_rules.json で個別に指定する）


def to_text(chunk):
    lines = []

    def blank(n=1):
        for _ in range(n):
            lines.append("")

    def ensure_blank():
        if lines and lines[-1] != "":
            lines.append("")

    for para in chunk:
        txt = para["text"].replace("\t", "　").rstrip()
        if para["break_before"]:
            blank(PAGE_BLANKS)
        if para["before"] >= LINE * 0.9:
            ensure_blank()
        if not txt.strip():
            blank()   # 空段落はそのまま一行空き（連続しても詰めない）
        else:
            for k, line in enumerate(txt.split("\n")):
                line = line.rstrip()
                if k == 0 and para["indent"] and para["style"] not in NOINDENT_STYLE_NAMES:
                    lead = len(line) - len(line.lstrip("　 "))
                    if lead < para["indent"]:
                        line = "　" * (para["indent"] - lead) + line.lstrip("　 ")
                lines.append(line)
            if para["after"] >= LINE * 0.9:
                ensure_blank()
        if para["page_break"]:
            blank(PAGE_BLANKS)
    while lines and lines[-1] == "":
        lines.pop()
    while lines and lines[0] == "":
        lines.pop(0)
    return "\n".join(lines) + "\n"


def apply_rules(wid, text, rules):
    """data/import_rules.json の個別指定を本文に適用する。
    形式: {"ai-06": [{"after": "行に含まれる文字列", "blank": 30}, ...]}
    "after" を含む行（本文中で1行だけに一致すること）の直後の空行を、ちょうど "blank" 行にする。"""
    lines = text.rstrip("\n").split("\n")
    for rule in rules.get(wid, []):
        hits = [i for i, l in enumerate(lines) if rule["after"] in l]
        if len(hits) != 1:
            sys.exit(f"{wid}: 指定「{rule['after']}」に一致する行が {len(hits)} 行あります（1行だけに一致するよう指定してください）")
        i = hits[0] + 1
        while i < len(lines) and lines[i] == "":
            del lines[i]
        lines[i:i] = [""] * int(rule["blank"])
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx")
    ap.add_argument("--issue", required=True, help="data/issues.json の号ID（例: ana）")
    ap.add_argument("--year", type=int, default=None, help="制作年（省略時は号の発行年）")
    ap.add_argument("--titles", help="作品名をカンマ区切りで（スタイルが使われていない原稿用）")
    ap.add_argument("--no-author-line", action="store_true", help="--titles 使用時、作品名の次の行が著者名でない")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    issues = json.load(open(os.path.join(ROOT, "data", "issues.json"), encoding="utf-8"))
    issue = next((i for i in issues if i["id"] == a.issue), None)
    if not issue:
        sys.exit(f"号 '{a.issue}' が data/issues.json にありません。先に号を追加してください")
    year = a.year or int(issue["date"][:4])

    rules_path = os.path.join(ROOT, "data", "import_rules.json")
    rules = json.load(open(rules_path, encoding="utf-8")) if os.path.exists(rules_path) else {}

    doc, styles = load(a.docx)
    paras = extract(doc, style_table(styles))
    titles = [t.strip() for t in a.titles.split(",")] if a.titles else None
    works = find_works(paras, titles, not a.no_author_line)

    entries = []
    for n, (title, author, chunk) in enumerate(works, 1):
        # 著者名全体にルビ（｜親文字《よみ》）なら読みを authorRuby に、それ以外のルビは外す
        whole = re.fullmatch(r"｜([^｜《》]+)《([^《》]+)》", author)
        author_ruby = whole.group(2) if whole else ""
        author = whole.group(1) if whole else re.sub(r"｜([^《]+)《[^》]+》", r"\1", author)
        wid = f"{a.issue}-{n:02d}"
        text = apply_rules(wid, to_text(chunk), rules)
        rubies = len(re.findall(r"｜[^《]+《[^》]+》", text))
        print(f"{wid}  {title}  ／  {author or '（著者不明）'}  {len(text)}字  ルビ{rubies}")
        print("      先頭:", text.split("\n", 1)[0][:40])
        print("      末尾:", text.rstrip("\n").rsplit("\n", 1)[-1][:40])
        if not a.dry_run:
            with open(os.path.join(ROOT, "texts", wid + ".txt"), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        entries.append({"id": wid, "issue": a.issue, "title": title, "author": author, "year": year,
                        "genres": [], "synopsis": "", "body": f"texts/{wid}.txt", "bodyMode": "full"})
        if author_ruby:
            entries[-1]["authorRuby"] = author_ruby

    if a.dry_run:
        print("（dry-run：ファイルは書き込んでいません）")
        return
    path = os.path.join(ROOT, "data", "works.json")
    current = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    before = {w.get("id"): w for w in current}

    def real(v):
        """空欄や仮の値（[作品名] など）でなければ True"""
        if v in (None, "", []):
            return False
        items = v if isinstance(v, list) else [v]
        return not any(isinstance(x, str) and x.startswith("[") and x.endswith("]") for x in items)

    kept = []
    for e in entries:
        old = before.get(e["id"])
        if old and real(old.get("title")):  # 作品名が仮の値のサンプル作品からは何も引き継がない
            for k in ("author", "authorRuby", "year", "genres", "synopsis", "bodyMode"):
                if real(old.get(k)):
                    e[k] = old[k]
                    if e["id"] not in kept:
                        kept.append(e["id"])
            if e["bodyMode"] == "none":
                e["bodyMode"] = "full"  # 本文を取り込んだので本文ありにする
    if kept:
        print("既存の作品データ（著者名・ジャンル・あらすじなど）を引き継いだ作品:", ", ".join(kept))
    # 並び順を保つ：同じIDの作品は元の位置に置き換え、なくなった作品は外し、新しい作品は末尾に足す
    new_by_id = {e["id"]: e for e in entries}
    result, placed = [], set()
    for w in current:
        if w.get("issue") != a.issue:
            result.append(w)
        elif w.get("id") in new_by_id:
            result.append(new_by_id[w["id"]])
            placed.add(w["id"])
    result += [e for e in entries if e["id"] not in placed]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"data/works.json：{a.issue} の作品を {len(entries)} 件で更新しました。")
    todo = [e["id"] for e in entries if not real(e["genres"]) or not real(e["synopsis"])]
    if todo:
        print("ジャンルまたはあらすじが未記入の作品（埋めること）:", ", ".join(todo))


if __name__ == "__main__":
    main()
