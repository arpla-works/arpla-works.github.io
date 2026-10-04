#!/usr/bin/env python3
"""同人誌のWord原稿（.docx）を、サイト用の本文ファイルと作品データに変換する。

使い方:
  python3 tools/import_docx.py 原稿.docx --issue ana
  python3 tools/import_docx.py 原稿.docx --issue ana --dry-run     # 書き込まずに分割結果だけ確認

やること:
  - 作品ごとに texts/<issue>-01.txt, -02.txt … を書き出す（既存ファイルは上書き）
  - data/works.json の、その号（--issue）の作品をすべて置き換える（他の号の作品はそのまま）
    ※ ジャンルとあらすじは空で作る。あとで必ず埋めること（check.py がエラーにする）

作品の区切りの見つけ方:
  - 段落スタイル名が「タイトル」の段落＝作品名、その直後の「著者」スタイルの段落＝著者名
  - スタイルが使われていない原稿は --titles "作品A,作品B,…" で作品名を本文の登場順に指定する
    （この場合、作品名の次の段落を著者名とみなす。著者行がない作品は --no-author-line で指定）
  - 最後の作品は、奥付（改ページ後に「発行」を含む行が続く箇所）の手前で終わる

変換のきまり（サイトの本文形式に合わせる）:
  - 1段落＝1行。空段落は一行空き（連続する空行は1つにまとめる）
  - 原稿で字下げされている段落（地の文など）は行頭に全角スペースを1つ付ける。字下げのない段落（会話文など）と章節見出しには付けない
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
NOINDENT_STYLE_NAMES = {"章節", "タイトル", "著者"}


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
        table[sid] = {
            "name": name.get(W + "val") if name is not None else "",
            "base": base.get(W + "val") if base is not None else None,
            "ind": {k[len(W):]: v for k, v in ind.attrib.items()} if ind is not None else {},
        }
    return table


def style_first_line(table, sid):
    for _ in range(10):
        if not sid or sid not in table:
            return 0
        ind = table[sid]["ind"]
        if "firstLineChars" in ind:
            return int(ind["firstLineChars"])
        if "firstLine" in ind:
            return int(ind["firstLine"])
        sid = table[sid]["base"]
    return 0


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
    """本文の段落を [(text, style_name, indent, page_break)] で返す"""
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
        explicit = {}
        if ppr is not None:
            ps = ppr.find(W + "pStyle")
            sid = ps.get(W + "val") if ps is not None else None
            ind = ppr.find(W + "ind")
            if ind is not None:
                explicit = {k[len(W):]: v for k, v in ind.attrib.items()}
        if "firstLineChars" in explicit:
            first = int(explicit["firstLineChars"])
        elif "firstLine" in explicit:
            first = int(explicit["firstLine"])
        else:
            first = style_first_line(table, sid)
        if "hanging" in explicit or "hangingChars" in explicit:
            first = 0
        name = table.get(sid, {}).get("name", "") if sid else ""
        page_break = any(b.get(W + "type") == "page" for b in p.iter(W + "br")) or \
            (ppr is not None and (ppr.find(W + "sectPr") is not None or ppr.find(W + "pageBreakBefore") is not None))
        paras.append(("".join(parts), name, first > 0 and name not in NOINDENT_STYLE_NAMES, page_break))
    return paras


def find_works(paras, titles=None, author_line=True):
    starts = []
    if titles:
        pos = 0
        for t in titles:
            cand = [k for k in range(pos, len(paras)) if paras[k][0].strip() == t]
            if not cand:
                sys.exit(f"作品名「{t}」が本文に見つかりません")
            # 目次の行と区別するため、直後の段落が別の作品名でない最初の出現を使う
            i = next((k for k in cand if not any(paras[k + d][0].strip() in titles for d in (1, 2, 3) if k + d < len(paras))), cand[0])
            nxt = next((j for j in range(i + 1, len(paras)) if paras[j][0].strip()), i + 1)
            author = paras[nxt][0].strip() if author_line else ""
            starts.append((i, t, author, (nxt - i + 1) if author_line else 1))
            pos = i + 1
    else:
        for i, (txt, name, _, _) in enumerate(paras):
            if name == "タイトル" and txt.strip():
                j = i + 1
                while j < len(paras) and not paras[j][0].strip():
                    j += 1
                if j < len(paras) and paras[j][1] == "著者":
                    starts.append((i, txt.strip(), paras[j][0].strip(), j - i + 1))
                else:
                    starts.append((i, txt.strip(), "", 1))
        # 表紙の書名など、本文の作品でない「タイトル」は著者がないので除外
        starts = [s for s in starts if s[2]] or starts
    if not starts:
        sys.exit("作品の区切りが見つかりません。--titles で作品名を指定してください")
    # 奥付の位置：最後の作品のあと、改ページの直後数行に「発行」がある箇所
    end = len(paras)
    for k in range(starts[-1][0] + 1, len(paras)):
        if paras[k][3]:
            following = [p[0] for p in paras[k + 1:k + 8] if p[0].strip()]
            if any("発行" in t for t in following[:5]):
                end = k + 1 if paras[k][0].strip() else k
                break
    works = []
    for n, (i, title, author, skip) in enumerate(starts):
        e = starts[n + 1][0] if n + 1 < len(starts) else end
        works.append((title, author, paras[i + skip:e]))
    return works


def to_text(chunk):
    lines = []
    for txt, name, indent, _ in chunk:
        txt = txt.replace("\t", "　").rstrip()
        if not txt.strip():
            if lines and lines[-1] != "":
                lines.append("")
            continue
        for k, line in enumerate(txt.split("\n")):
            line = line.rstrip()
            if k == 0 and indent and not line.startswith("　"):
                line = "　" + line
            lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    while lines and lines[0] == "":
        lines.pop(0)
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

    doc, styles = load(a.docx)
    paras = extract(doc, style_table(styles))
    titles = [t.strip() for t in a.titles.split(",")] if a.titles else None
    works = find_works(paras, titles, not a.no_author_line)

    entries = []
    for n, (title, author, chunk) in enumerate(works, 1):
        author = re.sub(r"｜([^《]+)《[^》]+》", r"\1", author)  # 著者名のルビは外す
        wid = f"{a.issue}-{n:02d}"
        text = to_text(chunk)
        rubies = len(re.findall(r"｜[^《]+《[^》]+》", text))
        print(f"{wid}  {title}  ／  {author or '（著者不明）'}  {len(text)}字  ルビ{rubies}")
        print("      先頭:", text.split("\n", 1)[0][:40])
        print("      末尾:", text.rstrip("\n").rsplit("\n", 1)[-1][:40])
        if not a.dry_run:
            with open(os.path.join(ROOT, "texts", wid + ".txt"), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        entries.append({"id": wid, "issue": a.issue, "title": title, "author": author, "year": year,
                        "genres": [], "synopsis": "", "body": f"texts/{wid}.txt", "bodyMode": "full"})

    if a.dry_run:
        print("（dry-run：ファイルは書き込んでいません）")
        return
    path = os.path.join(ROOT, "data", "works.json")
    current = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    keep = [w for w in current if w.get("issue") != a.issue]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(keep + entries, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"data/works.json：{a.issue} の作品を {len(entries)} 件で置き換えました。ジャンルとあらすじを埋めてください")


if __name__ == "__main__":
    main()
