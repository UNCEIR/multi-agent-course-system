# -*- coding: utf-8 -*-
"""多科成绩合并 — 防信息丢失核心（零 LLM）。

- 键合并：主键 学号，回退 (班级,姓名)；冲突记告警不静默
- 跨文件差集校验：各文件学号集合与主索引 diff → 多出/缺失告警
- 中间形态 JSON：{batch_id, semester, students:[{student_id,class,name,score:[{subject,...}]}]}
- 完整性断言：学生数/每生科目数 == 文件数（渲染前置闸）
- Journal：逐文件合并即落盘，崩溃可续跑

Phase: 2 (implemented)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .contract import ERR_MERGE_CONFLICT, canonical_dimension, canonical_subject
from .parse_score_excels import ParsedFile


@dataclass
class MergedStudents:
    batch_id: str
    semester: str
    students: list[dict]  # {student_id, class, name, score: [{subject, ...grades}]}
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def _merge_key(student_id: str, class_name: str, name: str) -> tuple:
    """合并键：学号为主键（有则唯一标识学生）；学号缺失回退 (班级,姓名)。"""
    if student_id:
        return ("id", student_id)
    return ("name", class_name, name)


def _subject_grades(pf: ParsedFile, idx: int) -> dict:
    """单科成绩条目：{subject, <维度>: 等级...}（维度名归一为模板名）。"""
    grades = pf.students[idx].grades
    entry = {"subject": canonical_subject(pf.subject)}
    for dim, grade in grades.items():
        entry[canonical_dimension(dim)] = grade
    return entry


def merge_files(parsed_files: list[ParsedFile], *, semester: str = "", batch_id: str | None = None) -> MergedStudents:
    """按 (学号,班级,姓名) 键合并多科成绩 → 中间形态 JSON。"""
    if not parsed_files:
        return MergedStudents(batch_id=batch_id or _new_batch_id(), semester=semester, students=[])

    index: dict[tuple[str, str, str], dict] = {}  # key -> student dict
    order: list[tuple[str, str, str]] = []
    warnings: list[str] = []

    # 第一遍：建立学号集合（差集校验用）
    all_ids: dict[str, set[str]] = {}
    for pf in parsed_files:
        all_ids[pf.source_name] = {s.student_id for s in pf.students if s.student_id}

    # 第二遍：按键合并，逐文件 push score
    for fi, pf in enumerate(parsed_files):
        for si, stu in enumerate(pf.students):
            key = _merge_key(stu.student_id, pf.class_name, stu.name)
            if key in index:
                warnings.append(
                    f"{pf.source_name}: 学生 {stu.name} 与已有记录键冲突（学号={stu.student_id or '空'}），追加该科成绩"
                )
            else:
                index[key] = {
                    "student_id": stu.student_id,
                    "class": pf.class_name,
                    "name": stu.name,
                    "score": [],
                }
                order.append(key)
            index[key]["score"].append(_subject_grades(pf, si))

    # 差集校验：跨文件学号集合 diff
    ids_list = list(all_ids.items())
    for i in range(len(ids_list)):
        for j in range(i + 1, len(ids_list)):
            fname_i, set_i = ids_list[i]
            fname_j, set_j = ids_list[j]
            if set_i and set_j:
                only_i = set_i - set_j
                only_j = set_j - set_i
                if only_i:
                    warnings.append(f"{fname_i} 有 {fname_j} 没有的学号: {sorted(only_i)[:5]}")
                if only_j:
                    warnings.append(f"{fname_j} 有 {fname_i} 没有的学号: {sorted(only_j)[:5]}")

    semester = semester or parsed_files[0].semester
    return MergedStudents(
        batch_id=batch_id or _new_batch_id(),
        semester=semester,
        students=[index[k] for k in order],
        warnings=warnings,
    )


def assert_integrity(merged: MergedStudents, file_count: int) -> list[str]:
    """完整性断言（渲染前置闸）：学生数 > 0；每生科目数 == 文件数。

    返回错误清单（空 = 通过）。不满足 → 调用方不得进入渲染。
    """
    errors: list[str] = []
    if not merged.students:
        errors.append("解析结果为空：无学生数据")
    for stu in merged.students:
        if len(stu["score"]) != file_count:
            errors.append(
                f"{stu['name']}: 科目数 {len(stu['score'])} != 文件数 {file_count}（缺科，禁止渲染）"
            )
    return errors


def _new_batch_id() -> str:
    return f"b_{uuid.uuid4().hex[:8]}"


def journal_save(batch_dir: str | Path, merged: MergedStudents) -> Path:
    """合并中间态落盘（Journal）：<batch_dir>/merged.json。"""
    path = Path(batch_dir) / "merged.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def journal_load(batch_dir: str | Path) -> MergedStudents | None:
    """从 Journal 恢复（崩溃续跑）。"""
    path = Path(batch_dir) / "merged.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return MergedStudents(**data)


def merge_files_tool(parsed_files: list[dict], *, semester: str = "") -> dict:
    """@tool 用入口：dict 形态 ParsedFile → 中间形态 JSON。"""
    pfs = [
        ParsedFile(
            subject=f.get("subject", ""),
            class_name=f.get("class_name", ""),
            semester=f.get("semester", ""),
            source_name=f.get("source_name", f.get("file", "")),
            grade_columns=f.get("grade_columns", []),
            students=[_student_from_dict(s) for s in f.get("students", [])],
            warnings=list(f.get("warnings", [])),
        )
        for f in parsed_files
    ]
    merged = merge_files(pfs, semester=semester)
    return {"batch_id": merged.batch_id, "semester": merged.semester, "students": merged.students,
            "warnings": merged.warnings, "integrity_errors": assert_integrity(merged, len(pfs))}


def _student_from_dict(d: dict):
    from .parse_score_excels import ParsedStudent

    return ParsedStudent(student_id=d.get("student_id", ""), name=d.get("name", ""), grades=d.get("grades", {}))
