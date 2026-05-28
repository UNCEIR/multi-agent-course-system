# prompt-category-extraction Specification

## Purpose
TBD - created by archiving change fix-category-fuzzy-match. Update Purpose after archive.
## Requirements
### Requirement: Prompt fallback extracts B-scheme colloquial category keywords

When LLM hard-constraint JSON does not provide categories, `StudentProfileAgent._extract_prompt_hard_constraints` SHALL map colloquial prompt substrings to canonical `course_category` values and merge them into `HardConstraints.categories`.

Canonical categories MUST be:

- `自然科学与工程技术类`
- `人文与社会科学类`

In addition to existing rules for `自然科学`, `工程技术`, `人文`, `社会科学`, and `心理`, the following MUST map to `自然科学与工程技术类`: `理工`, `理工类`, `理工科`, `工科`, `工科类`, `理科类`.

The following MUST map to `人文与社会科学类`: `文科`, `文科类`, `社科`, `社科类`.

The bare substring `理科` (without 类) MUST NOT be added as a rule keyword, to avoid false matches on location text such as 理科楼.

#### Scenario: Prompt contains 理工类

- **WHEN** `_parse_hard_constraints` is called with empty LLM categories and prompt `我只要理工类的课`
- **THEN** `hard.categories` SHALL include `自然科学与工程技术类`

#### Scenario: Prompt contains 文科

- **WHEN** `_parse_hard_constraints` is called with empty LLM categories and prompt `想找文科的公选课`
- **THEN** `hard.categories` SHALL include `人文与社会科学类`

#### Scenario: Prompt contains 工科类

- **WHEN** `_parse_hard_constraints` is called with empty LLM categories and prompt `偏好工科类的选修`
- **THEN** `hard.categories` SHALL include `自然科学与工程技术类`

#### Scenario: Prompt contains 理科类

- **WHEN** `_parse_hard_constraints` is called with empty LLM categories and prompt `只要理科类课程`
- **THEN** `hard.categories` SHALL include `自然科学与工程技术类`

#### Scenario: Prompt contains 社科类

- **WHEN** `_parse_hard_constraints` is called with empty LLM categories and prompt `想选社科类公选课`
- **THEN** `hard.categories` SHALL include `人文与社会科学类`

#### Scenario: Existing 自然科学类 prompt still works

- **WHEN** `_parse_hard_constraints` is called with empty LLM categories and prompt containing `自然科学类`
- **THEN** `hard.categories` SHALL include `自然科学与工程技术类`

