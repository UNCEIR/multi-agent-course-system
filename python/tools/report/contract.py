# -*- coding: utf-8 -*-
"""report 中间形态契约常量。

- 错误码枚举（各链路共用）
- 学科/维度别名映射：Excel 表头名 ↔ 模板锚点名（数值回填校验与锚点匹配的归一依据）

Phase: 2 (implemented)
"""

from __future__ import annotations

# ── 错误码 ───────────────────────────────────────────────────────────────
ERR_PARSE_FAILED = "parse_failed"  # Excel 解析失败（文件/表头/行级）
ERR_GRADE_INVALID = "grade_invalid"  # 等级值域非法
ERR_MERGE_CONFLICT = "merge_conflict"  # 合并键冲突
ERR_FILL_FAILED = "fill_failed"  # 模板填充失败（LLM 校验不过 / Jinja2 失败）
ERR_RENDER_FAILED = "render_failed"  # PDF 渲染失败（含 WeasyPrint 缺依赖）
ERR_UPLOAD_FAILED = "upload_failed"  # 存储上传失败

# ── 等级值域 ─────────────────────────────────────────────────────────────
GRADE_LETTERS = "ABCDEF"  # 合法等级字符集（容忍大小写，归一为大写）

# ── 学科/维度别名映射 ────────────────────────────────────────────────────
# Excel 侧名（行3 学科 / 子维度表头）→ 模板侧锚点名（1.html 学科名 / 子维度名）。
# 两侧都能取到原始名时以映射值为准做锚点匹配；映射未覆盖的按原名直配。
SUBJECT_ALIAS: dict[str, str] = {
    "道法": "道德与法治",
    "道德与法治": "道德与法治",
    "语文": "语文",
    "数学": "数学",
    "英语": "英语",
    "科学": "科学",
    "社团": "社团",
    "音乐": "音乐",
    "体育": "体育",
    "美术": "美术",
    "信息": "信息",
    "劳动": "劳动",
    "综实": "综实",
}

# Excel 子维度 → 模板子维度（1.html）
DIMENSION_ALIAS: dict[str, str] = {
    "过程性评价": "过程性评价",
    "综合答辩": "综合答辩",
    "学科实践": "学科实践",
    "考试性评价70分": "卷面成绩",  # Excel 维度名（含满分标注）→ 模板"卷面成绩"
    "考试性评价": "卷面成绩",
    "综合性评价100分": "期末总评",  # Excel 维度名 → 模板"期末总评"
    "综合性评价": "期末总评",
    "展示性评价（必选）": "必选",
    "展示性评价（自选）": "自选",
    "课程名称": "课程名称",
    "综合评价": "综合评价",
}

# 解析时可丢弃的列（子维度名命中即丢弃；"" 表示单列维度需单独处理）
DROPPED_SUB_LABELS = {"分数", "原始", "折算", "备注"}


def normalize_grade(value: str | None) -> str:
    """等级值归一：NFKC + 去空白 + 大写。空值保留为空串（不推断）。"""
    if value is None:
        return ""
    import unicodedata

    return unicodedata.normalize("NFKC", str(value)).strip().upper()


def is_valid_grade(value: str) -> bool:
    """等级值域校验：单字符 A-F 或空串（"没给到就留空"）。"""
    if value == "":
        return True
    return len(value) == 1 and value in GRADE_LETTERS


def canonical_subject(name: str) -> str:
    """学科名归一（Excel/模板两侧都归到模板名）。"""
    return SUBJECT_ALIAS.get(name, name)


def canonical_dimension(name: str) -> str:
    """维度名归一（Excel 子维度 → 模板子维度）。"""
    return DIMENSION_ALIAS.get(name, name)
