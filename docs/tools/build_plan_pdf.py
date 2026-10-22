"""기획안 Markdown을 코디세이 공식 양식 모양의 PDF로 변환한다.

사용법:
    python docs/tools/build_plan_pdf.py            # docs/01_기획안.md -> docs/01_기획안.pdf
    python docs/tools/build_plan_pdf.py 입력.md 출력.pdf

외부 패키지 없이 동작하며, PDF 인쇄에는 설치된 Edge 또는 Chrome(headless)을 사용한다.
지원하는 Markdown 문법: 앞머리(front matter), ## 섹션, 문단, 목록(중첩), 표, **굵게**, `코드`.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SRC = DOCS_DIR / "01_기획안.md"

# Edge headless가 PDF를 만들지 못하는 환경이 있어 Chrome을 먼저 찾는다
BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]

LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return out


def render_table(rows: list[str]) -> str:
    def cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split("|")]

    head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    parts = ["<table class='inner'><thead><tr>"]
    parts += [f"<th>{inline(c)}</th>" for c in head]
    parts.append("</tr></thead><tbody>")
    for r in body:
        parts.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def render_list(items: list[tuple[int, str, str]]) -> str:
    """items: (indent, marker, text) 목록을 중첩 <ul>/<ol>로 변환."""
    out: list[str] = []
    stack: list[tuple[int, str]] = []  # (indent, tag)
    for indent, marker, text in items:
        tag = "ol" if marker[0].isdigit() else "ul"
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if stack and indent == stack[-1][0]:
            out.append("</li>")
        else:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        out.append(f"<li>{inline(text)}")
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out)


def render_blocks(lines: list[str]) -> str:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(render_table(rows))
        elif LIST_RE.match(line):
            items = []
            while i < len(lines) and (m := LIST_RE.match(lines[i])):
                items.append((len(m.group(1)), m.group(2), m.group(3)))
                i += 1
            out.append(render_list(items))
        elif line.startswith("### "):
            out.append(f"<h4>{inline(line[4:])}</h4>")
            i += 1
        else:
            para = []
            while (
                i < len(lines)
                and lines[i].strip()
                and not lines[i].lstrip().startswith("|")
                and not LIST_RE.match(lines[i])
            ):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def parse(md: str) -> tuple[dict[str, str], list[tuple[str, list[str]]]]:
    meta: dict[str, str] = {}
    lines = md.splitlines()
    if lines and lines[0].strip() == "---":
        end = lines.index("---", 1)
        for raw in lines[1:end]:
            key, _, value = raw.partition(":")
            meta[key.strip()] = value.strip().strip('"')
        lines = lines[end + 1 :]

    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:  # 첫 ## 이전(제목, 안내문)은 PDF에 넣지 않는다
            sections[-1][1].append(line)
    return meta, sections


def label_html(title: str) -> str:
    # "기대효과 및 활용방안"처럼 긴 라벨은 양식과 같이 두 줄로 나눈다
    if " 및 " in title:
        a, b = title.split(" 및 ", 1)
        return f"{html.escape(a)} 및<br>{html.escape(b)}"
    return html.escape(title)


def build_html(meta: dict[str, str], sections: list[tuple[str, list[str]]]) -> str:
    rows = "\n".join(
        f"<tr class='sec'><th class='label'>{label_html(t)}</th>"
        f"<td colspan='3' class='content'>{render_blocks(body)}</td></tr>"
        for t, body in sections
    )
    m = {k: html.escape(v) for k, v in meta.items()}
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 14mm 13mm 13mm 13mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
         font-size: 8.9pt; line-height: 1.42; color: #111; margin: 0; }}
  .badge {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
            border-top: 2px solid #1f2a6b; border-bottom: 2px solid #1f2a6b; padding: 3px 0; }}
  .badge span {{ background: #2b3a9b; color: #fff; font-weight: 800; padding: 2px 10px; font-size: 12pt; }}
  .badge b {{ font-size: 13pt; font-weight: 800; }}
  table.form {{ width: 100%; border-collapse: collapse; border: 1.2px solid #000; }}
  table.form > tbody > tr > th, table.form > tbody > tr > td {{ border: 1px solid #000; padding: 5px 8px; }}
  .title {{ background: #d9d9d9; text-align: center; font-size: 12.5pt; font-weight: 800; padding: 7px; }}
  .key {{ background: #f2f2f2; width: 15%; text-align: center; font-weight: 800; }}
  .val {{ text-align: center; }}
  th.label {{ background: #fff; width: 15%; text-align: center; font-weight: 800; vertical-align: middle; }}
  td.content {{ vertical-align: top; }}
  tr.sec {{ page-break-inside: auto; }}
  p {{ margin: 3px 0 4px; }}
  ul, ol {{ margin: 2px 0 4px; padding-left: 17px; }}
  li {{ margin: 1px 0; }}
  li > ul, li > ol {{ margin: 1px 0; }}
  h4 {{ margin: 6px 0 2px; font-size: 9.2pt; }}
  code {{ font-family: Consolas, monospace; font-size: 8.3pt; }}
  table.inner {{ width: 100%; border-collapse: collapse; margin: 4px 0 5px; font-size: 8.4pt; }}
  table.inner th, table.inner td {{ border: 1px solid #999; padding: 3px 5px; vertical-align: top; }}
  table.inner th {{ background: #eef1f8; font-weight: 800; }}
  table.inner td:first-child {{ white-space: nowrap; }}
  table.inner tr {{ page-break-inside: avoid; }}
</style></head><body>
<div class="badge"><span>붙임1</span><b>Final-Project 프로젝트 기획안</b></div>
<table class="form"><tbody>
<tr><th colspan="4" class="title">코디세이 AI 네이티브 응용 학습 Final-Project 기획안</th></tr>
<tr><th class="key">도메인</th><td class="val">{m.get('도메인', '')}</td>
    <th class="key">팀 명</th><td class="val">{m.get('팀명', '')}</td></tr>
<tr><th class="key">프로젝트명</th><td class="val">{m.get('프로젝트명', '')}</td>
    <th class="key">팀장 명</th><td class="val">{m.get('팀장명', '')}</td></tr>
{rows}
</tbody></table>
</body></html>"""


def find_browser() -> str:
    for cand in BROWSER_CANDIDATES:
        if Path(cand).exists():
            return cand
    for name in ("msedge", "google-chrome", "chromium", "chrome"):
        if found := shutil.which(name):
            return found
    sys.exit("Edge 또는 Chrome을 찾지 못했습니다. HTML만 생성합니다.")


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".pdf")
    meta, sections = parse(src.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        html_path = tmp_dir / "plan.html"
        pdf_tmp = tmp_dir / "plan.pdf"
        html_path.write_text(build_html(meta, sections), encoding="utf-8")
        subprocess.run(
            [
                find_browser(),
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                "--print-to-pdf-no-header",
                f"--user-data-dir={tmp_dir / 'profile'}",
                f"--print-to-pdf={pdf_tmp}",
                html_path.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        if not pdf_tmp.exists():
            sys.exit("PDF 생성에 실패했습니다.")
        shutil.copyfile(pdf_tmp, dst)
    print(f"생성 완료: {dst}")


if __name__ == "__main__":
    main()
