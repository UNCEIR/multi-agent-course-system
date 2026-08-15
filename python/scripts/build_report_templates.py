# -*- coding: utf-8 -*-
"""生成 report 锚点模板（模板文件 = 契约，两种填充器共用）。

- grade4-6.html：自用户提供 `1.html` 结构化迁移——每个可填成绩格替换为
  `<span class="fill" data-slot="<学科>|<维度>|grade"></span>`，
  班级/姓名 input 替换为 data-slot 锚点，末尾追加评语区 data-slot="comment"。
- grade1-3.html：骨架占位（综合测评表风格：过程性/必选/自选/综合性评价），
  真实模板到达后整体替换文件即可。

学科维度布局（与 1.html 结构对齐）：
- 常规学科（道法/语文/数学/英语/科学）：过程性评价 / 综合答辩 / 学科实践 / 卷面成绩 / 期末总评
- 社团：课程名称 / 综合评价（标签格自身即填充目标）
- 艺体学科（音乐/体育/美术/信息/劳动/综实）：过程性评价 / 必选 / 自选 / 综合性评价

用法：cd python && python scripts/build_report_templates.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = REPO_ROOT / "python" / "templates" / "report"

REGULAR_SUBJECTS = {"道德与法治", "语文", "数学", "英语", "科学"}
ARTS_SUBJECTS = {"音乐", "体育", "美术", "信息", "劳动", "综实"}
CLUB_SUBJECTS = {"社团"}

_TR = re.compile(r"<tr(?:\s[^>]*)?>.*?</tr>", re.S)
_CELL = re.compile(r"<td(?:\s[^>]*)?>.*?</td>", re.S)
_TH_SUBJ = re.compile(r"<th[^>]*>([^<]+)</th>")

# 每个学科类型：块内数据行号（th 行后 0 起）→ 该行处理的维度；club 为 self（标签格即填充目标）。
# 注：club 的 rowspan（展示性评价跨 2 行）使其 综合评价 落在块内行号 3，而非 2。
ROW_DIMS = {
    "regular": {0: "过程性评价", 1: "综合答辩", 2: "学科实践", 3: "卷面成绩", 4: "期末总评"},
    "arts": {0: "过程性评价", 1: "必选", 2: "自选", 3: "综合性评价"},
    "club": {0: "课程名称", 3: "综合评价"},
}
ROW_COUNT = {"regular": 5, "arts": 4, "club": 4}


def _subject_type(subject: str) -> str:
    if subject in CLUB_SUBJECTS:
        return "club"
    if subject in ARTS_SUBJECTS:
        return "arts"
    return "regular"


def _inner_text(cell: str) -> str:
    return re.sub(r"<[^>]+>", "", cell).strip()


def _insert_anchor(cell: str, slot: str) -> str:
    """把单元格内容替换为锚点（空单元格或标签格均可）。"""
    inner = f'<span class="fill" data-slot="{slot}"></span>'
    return re.sub(r">.*?</td>$", f">{inner}</td>", cell, flags=re.S)


def _transform_block(data_rows: list[str], subjects: list[str]) -> list[str]:
    """变换一个学科块（th 行之后的全部数据行）。

    块内行号 → 维度映射：regular 5 行 / arts 4 行 / club 4 行（行号按块内 0 起）。
    """
    types = [_subject_type(s) for s in subjects]
    out: list[str] = []
    for ridx, row in enumerate(data_rows):
        dims_this_row = [ROW_DIMS[t].get(ridx) for t in types]
        cells = _CELL.findall(row)
        out_cells: list[str] = []
        ci = 0
        for si, dim in enumerate(dims_this_row):
            if dim is None:
                continue
            if types[si] == "club":
                # self：标签格自身即填充目标（保留标签格结构，内容替换为锚点）
                for j in range(ci, len(cells)):
                    if _inner_text(cells[j]) == dim:
                        out_cells.extend(cells[ci:j])  # 保留前置单元格
                        out_cells.append(_insert_anchor(cells[j], f"{subjects[si]}|{dim}|grade"))
                        ci = j + 1
                        break
                else:
                    ci = len(cells)
                continue
            # after_label：保留标签格，下一格为填充目标
            found_label = False
            for j in range(ci, len(cells)):
                if _inner_text(cells[j]) == dim:
                    out_cells.extend(cells[ci : j + 1])  # 标签格原样保留
                    ci = j + 1
                    found_label = True
                    break
            if found_label and ci < len(cells):
                out_cells.append(_insert_anchor(cells[ci], f"{subjects[si]}|{dim}|grade"))
                ci += 1
            else:
                ci = len(cells)
        if ci < len(cells):
            out_cells.extend(cells[ci:])
        out.append("<tr>" + "".join(out_cells) + "</tr>")
    return out


def _transform_table(html: str) -> str:
    """按学科块（th 行分隔）变换：块内数据行按行号→维度映射插锚点。

    保留非 <tr> 内容（head/班级行/评语区/</table> 等）；pending 缓冲保证
    数据行与交错片段（如 </table>）的顺序与原文档一致。
    """
    segments = re.split(r"(<tr(?:\s[^>]*)?>.*?</tr>)", html, flags=re.S)
    out: list[str] = []
    pending: list[str] = []  # 非 tr 片段 + 数据行，按原顺序缓冲
    data_rows: list[str] = []
    subjects: list[str] = []

    def _flush_pending() -> None:
        out.extend(pending)
        pending.clear()

    def _flush_block() -> None:
        if subjects:
            _flush_pending()
            out.extend(_transform_block(data_rows, subjects))
            data_rows.clear()
            subjects.clear()

    for seg in segments:
        if not seg.startswith("<tr"):
            pending.append(seg)
            continue
        ths = [_t for _t in _TH_SUBJ.findall(seg) if _t in REGULAR_SUBJECTS | ARTS_SUBJECTS | CLUB_SUBJECTS]
        if ths:
            _flush_block()
            _flush_pending()
            out.append(seg)
            subjects = ths
        else:
            data_rows.append(seg)
    _flush_block()
    _flush_pending()
    return "".join(out)


def build_grade4_6(source: Path, dest: Path) -> None:
    html = source.read_text(encoding="utf-8")
    # 班级/姓名 input → 锚点
    html = re.sub(
        r'<input[^>]*placeholder="填写班级"[^>]*>',
        '<span class="fill" data-slot="class|name"></span>',
        html,
    )
    html = re.sub(
        r'<input[^>]*placeholder="填写姓名"[^>]*>',
        '<span class="fill" data-slot="student|name"></span>',
        html,
    )
    # 学年度/学期标题 → 锚点
    html = re.sub(
        r"<h2>[^<]*</h2>",
        '<h2><span class="fill" data-slot="semester"></span></h2>',
        html,
    )
    html = _transform_table(html)
    # 评语区（模板尾部；综合评语 LLM 生成后填入，默认留空）
    comment_section = (
        '\n<div class="comment-section">\n  <h3>学生综合评价</h3>\n'
        '  <p class="fill" data-slot="comment"></p>\n</div>\n'
    )
    if "</body>" in html:
        html = html.replace("</body>", comment_section + "</body>")
    else:
        # 源模板可能未闭合（1.html 截断于表格后），补全收尾
        html = html + comment_section + "</body>\n</html>\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    print(f"grade4-6 template written: {dest} ({len(html)} chars)")


def build_grade1_3(dest: Path) -> None:
    """骨架占位：综合测评表风格（过程性/必选/自选/综合性评价），真实模板到后整体替换。"""
    subjects = ["道德与法治", "语文", "数学", "英语", "科学", "音乐", "体育", "美术", "信息", "劳动", "综实"]
    html = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '  <meta charset="UTF-8">',
        "  <title>学业质量评价学生成绩报告单（一至三年级）</title>",
        "  <style>",
        "    table { width: 100%; border-collapse: collapse; margin: 10px 0; }",
        "    th, td { border: 1px solid #000; padding: 8px; text-align: center; vertical-align: middle; }",
        "    th { background-color: #f2f2f2; }",
        "  </style>",
        "</head>",
        "<body>",
        '  <h2><span class="fill" data-slot="semester"></span></h2>',
        "  <h3>《南山区前海小学一至三年级学业质量评价学生成绩报告单》</h3>",
        '  <div class="info-line">',
        '    <span>班级：</span><span class="fill" data-slot="class|name"></span>',
        '    <span style="margin-left: 50px;">学生姓名：</span><span class="fill" data-slot="student|name"></span>',
        "  </div>",
    ]
    for i in range(0, len(subjects), 3):
        group = subjects[i : i + 3]
        html.append("  <table>")
        html.append("    <tr>" + "".join(f'<th colspan="4">{s}</th>' for s in group) + "</tr>")
        html.append("    <tr>" + "".join(f'<td colspan="1">过程性评价</td><td colspan="3"><span class="fill" data-slot="{s}|过程性评价|grade"></span></td>' for s in group) + "</tr>")
        html.append("    <tr>" + "".join(f'<td rowspan="2">展示性评价</td><td>必选</td><td colspan="2"><span class="fill" data-slot="{s}|必选|grade"></span></td>' for s in group) + "</tr>")
        html.append("    <tr>" + "".join(f'<td>自选</td><td colspan="2"><span class="fill" data-slot="{s}|自选|grade"></span></td>' for s in group) + "</tr>")
        html.append("    <tr>" + "".join(f'<td colspan="3">综合性评价</td><td><span class="fill" data-slot="{s}|综合性评价|grade"></span></td>' for s in group) + "</tr>")
        html.append("  </table>")
    html.append('  <div class="comment-section">')
    html.append("    <h3>学生综合评价</h3>")
    html.append('    <p class="fill" data-slot="comment"></p>')
    html.append("  </div>")
    html.append("</body>")
    html.append("</html>")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(html), encoding="utf-8")
    print(f"grade1-3 skeleton written: {dest}")


def main() -> None:
    source = REPO_ROOT / "1.html"
    if not source.is_file():
        print(f"ERROR: 未找到源模板 {source}")
        sys.exit(1)
    build_grade4_6(source, TEMPLATE_DIR / "grade4-6.html")
    build_grade1_3(TEMPLATE_DIR / "grade1-3.html")


if __name__ == "__main__":
    main()
