from __future__ import annotations

import csv
import hashlib
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "public_elective_courses.csv"
TARGET_ROW_COUNT = 500
FLAGGED_COURSE_COUNT = 24


RAW_COURSES = [
    {"name": "啤酒游戏-漫谈供应链管理", "teacher": "范捷", "limit": 100, "enrolled": 101, "category": "自然科学与工程技术类"},
    {"name": "从科技预言到电动中国：锂电池、光伏与电动汽车", "teacher": "朱昌宝", "limit": 100, "enrolled": 101, "category": "自然科学与工程技术类"},
    {"name": "风景地貌学", "teacher": "杨雪强", "limit": 200, "enrolled": 200, "category": "自然科学与工程技术类"},
    {"name": "环境问题案例", "teacher": "钟胜", "limit": 160, "enrolled": 162, "category": "自然科学与工程技术类", "note": "前半段周三晚"},
    {"name": "基本乐理", "teacher": "傅强", "limit": 30, "enrolled": 30, "category": "人文与社会科学类"},
    {"name": "基本乐理", "teacher": "傅强", "limit": 30, "enrolled": 30, "category": "人文与社会科学类"},
    {"name": "基本乐理", "teacher": "傅强", "limit": 30, "enrolled": 30, "category": "人文与社会科学类"},
    {"name": "解读动漫流行文化", "teacher": "曾天然", "limit": 155, "enrolled": 154, "category": "人文与社会科学类"},
    {"name": "神话传说与中国文化", "teacher": "宋婷婷", "limit": 155, "enrolled": 155, "category": "人文与社会科学类"},
    {"name": "生物安全与现代生活", "teacher": "廖问陶", "limit": 100, "enrolled": 101, "category": "自然科学与工程技术类"},
    {"name": "食品营养与卫生", "teacher": "熊开容", "limit": 50, "enrolled": 50, "category": "自然科学与工程技术类", "note": "前半段周三晚"},
    {"name": "世界旅游地理", "teacher": "马小宁", "limit": 100, "enrolled": 100, "category": "自然科学与工程技术类"},
    {"name": "书法与篆刻", "teacher": "刘乐舟", "limit": 70, "enrolled": 61, "category": "人文与社会科学类"},
    {"name": "水资源概论", "teacher": "韩泽军", "limit": 60, "enrolled": 31, "category": "自然科学与工程技术类", "note": "张帆1/韩泽军2/彭斯格3-8"},
    {"name": "通俗歌曲演唱技法", "teacher": "王晶一", "limit": 20, "enrolled": 20, "category": "人文与社会科学类"},
    {"name": "现代犯罪与刑法总论", "teacher": "刘乐舟", "limit": 150, "enrolled": 150, "category": "人文与社会科学类"},
    {"name": "幸福来敲门-积极心理学", "teacher": "吴伟卿", "limit": 100, "enrolled": 100, "category": "人文与社会科学类"},
    {"name": "演讲与口才", "teacher": "韩亚楠", "limit": 30, "enrolled": 30, "category": "人文与社会科学类"},
    {"name": "音乐剧与音乐文化", "teacher": "李轶", "limit": 60, "enrolled": 60, "category": "人文与社会科学类"},
    {"name": "影视鉴赏", "teacher": "韩亚楠", "limit": 155, "enrolled": 155, "category": "人文与社会科学类"},
    {"name": "证券投资分析", "teacher": "钟映姣", "limit": 100, "enrolled": 99, "category": "自然科学与工程技术类"},
    {"name": "中国旅游地理", "teacher": "张春慧", "limit": 60, "enrolled": 59, "category": "自然科学与工程技术类"},
    {"name": "中外名建筑赏析", "teacher": "胡晓旻", "limit": 60, "enrolled": 59, "category": "人文与社会科学类"},
    {"name": "中外园林赏析", "teacher": "胡晓旻", "limit": 60, "enrolled": 60, "category": "自然科学与工程技术类"},
    {"name": "中国古建筑文化与鉴赏", "teacher": "贾菱华", "limit": 100, "enrolled": 73, "category": "自然科学与工程技术类"},
    {"name": "生命的环境演绎", "teacher": "杜青平", "limit": 108, "enrolled": 108, "category": "自然科学与工程技术类"},
    {"name": "机器学习", "teacher": "陈鹤峰", "limit": 60, "enrolled": 27, "category": "自然科学与工程技术类"},
    {"name": "文化地理", "teacher": "郭丽萍", "limit": 155, "enrolled": 155, "category": "自然科学与工程技术类"},
    {"name": "爱情心理学", "teacher": "冯博雅", "limit": 170, "enrolled": 169, "category": "人文与社会科学类", "note": "周一"},
    {"name": "爱情心理学", "teacher": "冯博雅", "limit": 170, "enrolled": 170, "category": "人文与社会科学类", "note": "周四"},
    {"name": "爱情心理学", "teacher": "谢忻雯", "limit": 170, "enrolled": 170, "category": "人文与社会科学类", "note": "周三"},
    {"name": "爱情心理学", "teacher": "吴江秋", "limit": 60, "enrolled": 60, "category": "人文与社会科学类"},
]

REFERENCE_COURSE_TOPICS = [
    "哲学导论",
    "西方哲学史",
    "逻辑与科学方法论",
    "国学经典导读",
    "法律经典案例解析",
    "重大刑事案件解读",
    "西方文明史",
    "古典诗词导读",
    "中国现代文学名著赏析",
    "中华历史人物评介",
    "跨文化交际",
    "媒介与社会",
    "大众传媒文化",
    "社会研究方法",
    "城市社会学",
    "文化人类学",
    "艺术史",
    "美术鉴赏",
    "音乐鉴赏",
    "戏剧鉴赏",
    "舞蹈鉴赏",
    "书法鉴赏",
    "公益广告赏析与设计",
    "中国电影艺术赏析",
    "摄影与美术设计",
    "朗读与演讲",
    "行政商务礼仪规范与训练",
    "中外音乐审美",
    "中国历史文化古迹鉴赏",
    "中外建筑艺术赏析",
    "大学生音乐修养",
    "电影文化与电影史",
    "京剧艺术与传统文化",
    "数字信息资源的检索与利用",
    "人际沟通与交流",
    "幸福心理学",
    "健康心理学",
    "学习心理学",
    "色彩心理学",
    "大学生心理健康教育",
    "社会心理学",
    "防灾减灾文化概论",
    "创意写作",
    "欧美文化面面观",
    "应用文写作",
    "公共演讲",
    "辩论进阶",
    "科学阅读与创想",
    "学术演讲技巧",
    "英美诗歌与戏剧",
    "社会企业与公益创业",
    "创新与中国区域经济发展",
    "商务沟通与谈判模拟",
    "企业经营管理决策模拟",
    "服务营销",
    "创业企业与风险投资",
    "理解职业生涯",
    "大学生就业法律风险防范",
    "Python商业数据分析",
    "创新创业教育",
    "粉丝经济学",
    "生活中的经济学",
    "零基础读懂宏观经济",
    "演讲中的情绪感染与表达自信",
    "财务报表分析与公司估值",
    "价值投资与财报阅读",
    "大学生社会实践理论与实务",
    "可持续发展目标与国际教育发展",
    "国际冲突与危机管理",
    "财富管理入门",
    "大学生职业素养提升",
    "求职与择业",
    "ESG投资",
    "数据商业分析",
]

SYNTHETIC_TOPIC_GROUPS = {
    "人文与社会科学类": [
        "中国传统节日文化",
        "唐诗宋词与现代生活",
        "中国古代礼仪文明",
        "世界文明交流史",
        "敦煌艺术导论",
        "非遗文化保护与传播",
        "现代小说与社会观察",
        "网络文学与青年文化",
        "新媒体写作",
        "短视频文化研究",
        "公共关系与沟通技巧",
        "大学生领导力训练",
        "谈判心理学",
        "性别与社会",
        "社会热点案例分析",
        "城市文化与社区治理",
        "公共政策入门",
        "民法典与日常生活",
        "知识产权与创新保护",
        "劳动权益与职场法律",
        "中国音乐文化",
        "世界电影赏析",
        "动画艺术与叙事",
        "现代设计美学",
        "博物馆与文化遗产",
        "书法基础与审美",
        "合唱艺术实践",
        "普通话表达训练",
        "大学生压力管理",
        "亲密关系与沟通",
        "积极情绪训练",
        "生涯规划与自我探索",
        "职业形象与商务礼仪",
        "创新创业案例分析",
        "公益创业与社会创新",
        "消费者行为心理学",
        "互联网商业模式赏析",
        "个人理财基础",
        "宏观经济与日常决策",
        "演讲表达与舞台呈现",
    ],
    "自然科学与工程技术类": [
        "人工智能通识",
        "机器学习入门",
        "Python数据分析基础",
        "大数据与社会治理",
        "区块链技术与应用",
        "云计算与数字生活",
        "网络安全与个人信息保护",
        "物联网技术概论",
        "智能制造导论",
        "新能源技术与低碳生活",
        "光伏技术与能源转型",
        "新能源汽车产业观察",
        "材料科学与现代生活",
        "食品安全与健康",
        "营养学与体重管理",
        "生命科学前沿",
        "基因技术与伦理",
        "生物多样性保护",
        "生态文明与绿色发展",
        "水资源保护与利用",
        "气候变化与人类未来",
        "地球科学导论",
        "灾害风险与应急管理",
        "地图阅读与空间思维",
        "旅游地理与区域文化",
        "建筑结构与城市安全",
        "园林植物与景观设计",
        "供应链管理模拟",
        "项目管理基础",
        "质量管理与生活实践",
        "证券投资基础",
        "金融科技导论",
        "数据可视化入门",
        "统计思维与社会调查",
        "科学实验设计",
        "科学传播与公众理解",
        "天文学与宇宙探索",
        "海洋科学导论",
        "环境监测技术",
        "健康大数据与公共卫生",
    ],
}

TEACHER_SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
    "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
]

TEACHER_GIVEN_NAMES = [
    "明", "华", "敏", "磊", "静", "芳", "强", "伟", "娜", "洋",
    "佳", "宁", "晨", "宇", "欣", "雪", "睿", "然", "博", "雅",
    "泽", "琪", "航", "怡", "楠", "越", "卓", "涵", "青", "源",
]


TIME_SLOTS = [
    "周一第9-10节",
    "周二第5-6节",
    "周三第9-10节",
    "周四第7-8节",
    "周五第3-4节",
    "周六第1-2节",
]

LOCATIONS = ["教学楼A203", "教学楼B305", "综合楼C101", "人文楼204", "理科楼308", "艺术楼102"]
CAMPUSES = ["主校区", "东校区", "西校区", "南校区"]


def stable_index(value: str, modulo: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


def stable_ratio(value: str) -> float:
    return stable_index(value, 10_000) / 10_000


def infer_category(name: str) -> str:
    humanities_keys = [
        "哲学", "国学", "法律", "刑事", "文明", "诗词", "文学", "历史", "文化",
        "社会", "媒介", "传媒", "艺术", "美术", "音乐", "戏剧", "舞蹈", "书法",
        "电影", "建筑艺术", "演讲", "礼仪", "心理", "写作", "口语", "辩论", "职业",
        "创业", "经济", "金融", "投资", "商务", "谈判", "公益", "管理",
    ]
    if any(key in name for key in humanities_keys):
        return "人文与社会科学类"
    return "自然科学与工程技术类"


def generate_teacher(name: str) -> str:
    first = TEACHER_SURNAMES[stable_index(f"{name}-surname", len(TEACHER_SURNAMES))]
    given_a = TEACHER_GIVEN_NAMES[stable_index(f"{name}-given-a", len(TEACHER_GIVEN_NAMES))]
    given_b = TEACHER_GIVEN_NAMES[stable_index(f"{name}-given-b", len(TEACHER_GIVEN_NAMES))]
    if given_a == given_b:
        return first + given_a
    return first + given_a + given_b


def generate_capacity(name: str) -> tuple[int, int]:
    capacity_options = [30, 40, 50, 60, 70, 80, 100, 120, 150, 155, 160, 170, 200]
    capacity = capacity_options[stable_index(f"{name}-capacity", len(capacity_options))]
    popularity = stable_ratio(f"{name}-popularity")
    if popularity >= 0.78:
        ratio = 0.96 + stable_ratio(f"{name}-hot") * 0.08
    elif popularity >= 0.52:
        ratio = 0.80 + stable_ratio(f"{name}-warm") * 0.15
    elif popularity >= 0.18:
        ratio = 0.50 + stable_ratio(f"{name}-normal") * 0.28
    else:
        ratio = 0.25 + stable_ratio(f"{name}-cold") * 0.24
    enrolled = round(capacity * min(ratio, 1.04))
    return capacity, max(0, enrolled)


def build_generated_courses(target_count: int) -> list[dict[str, object]]:
    courses: list[dict[str, object]] = [dict(course) for course in RAW_COURSES]
    seen = {f"{course['name']}|{course['teacher']}|{course.get('note', '')}" for course in courses}

    def add_course(name: str, source: str, note: str = "") -> None:
        if len(courses) >= target_count:
            return
        category = infer_category(name)
        teacher = generate_teacher(f"{name}-{source}")
        key = f"{name}|{teacher}|{note}"
        if key in seen:
            return
        limit, enrolled = generate_capacity(f"{name}-{source}-{len(courses)}")
        courses.append(
            {
                "name": name,
                "teacher": teacher,
                "limit": limit,
                "enrolled": enrolled,
                "category": category,
                "note": note,
            }
        )
        seen.add(key)

    for topic in REFERENCE_COURSE_TOPICS:
        add_course(topic, "公开通识/公选课目录参考")

    prefixes = ["", "大学生", "生活中的", "现代", "中外", "跨学科", "数字时代的", "案例导向的"]
    suffixes = ["", "导论", "赏析", "案例分析", "实践", "专题", "与现代生活", "与社会发展"]
    topic_entries: list[tuple[str, str]] = []
    max_topic_count = max(len(topics) for topics in SYNTHETIC_TOPIC_GROUPS.values())
    for topic_index in range(max_topic_count):
        for category, topics in SYNTHETIC_TOPIC_GROUPS.items():
            if topic_index < len(topics):
                topic_entries.append((category, topics[topic_index]))

    for prefix in prefixes:
        for suffix in suffixes:
            for category, topic in topic_entries:
                if len(courses) >= target_count:
                    return courses
                name = topic
                if prefix and not topic.startswith(prefix):
                    name = f"{prefix}{name}"
                if suffix and not name.endswith(suffix):
                    name = f"{name}{suffix}"
                if len(name) > 26:
                    continue
                add_course(name, f"{category}规则扩展")

    serial = 1
    while len(courses) < target_count:
        category = "人文与社会科学类" if serial % 2 else "自然科学与工程技术类"
        base_topics = SYNTHETIC_TOPIC_GROUPS[category]
        topic = base_topics[serial % len(base_topics)]
        name = f"{topic}专题研讨{serial:03d}"
        add_course(name, f"{category}补足扩展")
        serial += 1

    return courses


def enrollment_ratio(enrolled: int, limit: int) -> float:
    if limit <= 0:
        return 0.0
    return round(enrolled / limit, 4)


def popularity_level(ratio: float) -> tuple[int, str]:
    if ratio >= 1.0:
        return 4, "非常热门，选课阶段需要优先抢课"
    if ratio >= 0.95:
        return 3, "建议第一轮优先选择"
    if ratio >= 0.80:
        return 2, "有一定竞争，建议提前加入备选"
    if ratio >= 0.50:
        return 1, "选上概率相对稳定"
    return 0, "选上概率较高，可作为保底课程"


def infer_course_profile(name: str, category: str) -> dict[str, str]:
    text = name
    tags: list[str] = []

    if any(key in text for key in ["心理", "幸福"]):
        domain = "心理成长"
        description = f"{name}围绕大学生心理、亲密关系和自我成长展开，适合关注情绪管理、人际关系与个人发展的学生。"
        assessment = "平时参与40%;课程小论文40%;课堂互动20%;无闭卷考试"
        difficulty = "低"
        workload = "低"
        grade_friendly = "高"
        tags += ["心理", "成长", "无闭卷考试", "给分友好", "讨论"]
    elif any(key in text for key in ["音乐", "乐理", "歌曲", "影视", "动漫", "书法", "篆刻", "建筑", "园林", "文化", "神话"]):
        domain = "人文艺术"
        description = f"{name}以艺术、人文或文化赏析为核心，帮助学生拓展审美视野和文化理解能力。"
        assessment = "课堂参与30%;赏析报告40%;期末作品或论文30%;无闭卷考试"
        difficulty = "低"
        workload = "中"
        grade_friendly = "中高"
        tags += ["人文", "艺术", "赏析", "论文", "无闭卷考试"]
    elif any(key in text for key in ["环境", "水资源", "生物", "地貌", "地理", "生命"]):
        domain = "自然环境"
        description = f"{name}关注自然科学、生态环境与现实生活之间的联系，适合希望拓展科学素养的学生。"
        assessment = "平时作业30%;案例分析40%;期末报告30%"
        difficulty = "中"
        workload = "中"
        grade_friendly = "中"
        tags += ["自然科学", "环境", "案例分析", "报告"]
    elif any(key in text for key in ["机器学习", "锂电池", "光伏", "供应链"]):
        domain = "工程技术"
        description = f"{name}介绍工程技术、产业发展或管理决策中的基础概念，适合对科技应用和产业趋势感兴趣的学生。"
        assessment = "平时作业30%;案例作业30%;期末报告40%"
        difficulty = "中高" if "机器学习" in text else "中"
        workload = "中高" if "机器学习" in text else "中"
        grade_friendly = "中"
        tags += ["工程技术", "产业", "案例", "报告"]
    elif any(key in text for key in ["证券", "犯罪", "刑法", "演讲", "口才"]):
        domain = "社会实务"
        description = f"{name}面向社会生活、法律金融或表达沟通场景，强调知识理解与实际案例分析。"
        assessment = "课堂参与30%;案例分析30%;期末论文或展示40%"
        difficulty = "中"
        workload = "中"
        grade_friendly = "中"
        tags += ["社会科学", "案例分析", "展示", "实用"]
    else:
        domain = category
        description = f"{name}是一门公共选修课程，适合希望拓展跨学科知识面的学生。"
        assessment = "平时参与30%;课程作业30%;期末报告40%"
        difficulty = "中"
        workload = "中"
        grade_friendly = "中"
        tags += ["公共选修课", "跨学科", "报告"]

    suitable_for = f"适合对{domain}感兴趣、希望通过公共选修课拓展知识面的学生。"
    return {
        "domain": domain,
        "description": description,
        "assessment": assessment,
        "difficulty": difficulty,
        "workload": workload,
        "grade_friendly": grade_friendly,
        "suitable_for": suitable_for,
        "tags": ";".join(dict.fromkeys(tags + [category, "公共选修课"])),
    }


def infer_time_slot(course: dict[str, object], index: int) -> str:
    note = str(course.get("note", ""))
    if "周一" in note:
        return "周一第9-10节"
    if "周三晚" in note or "周三" in note:
        return "周三第9-10节"
    if "周四" in note:
        return "周四第7-8节"
    return TIME_SLOTS[index % len(TIME_SLOTS)]


def build_history(limit: int, enrolled: int, name: str) -> dict[str, int | float]:
    base_ratio = enrollment_ratio(enrolled, limit)
    offsets = [-0.04, 0.02, -0.01]
    ratios: list[float] = []
    for year, offset in zip([2025, 2024, 2023], offsets, strict=True):
        adjusted_limit = max(20, limit + (stable_index(f"{name}-{year}", 5) - 2) * 5)
        adjusted_ratio = min(1.05, max(0.25, base_ratio + offset))
        adjusted_enrolled = round(adjusted_limit * adjusted_ratio)
        ratios.append(enrollment_ratio(adjusted_enrolled, adjusted_limit))
    return {"avg_history_enrollment_ratio": round(sum(ratios) / len(ratios), 4)}


def build_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    courses = build_generated_courses(TARGET_ROW_COUNT)

    for index, course in enumerate(courses, start=1):
        name = str(course["name"])
        teacher = str(course["teacher"])
        limit = int(course["limit"])
        enrolled = int(course["enrolled"])
        category = str(course["category"])
        note = str(course.get("note", ""))

        course_id = f"GXK2026{index:03d}"

        ratio = enrollment_ratio(enrolled, limit)
        hot_level, rush_advice = popularity_level(ratio)
        profile = infer_course_profile(name, category)
        history = build_history(limit, enrolled, f"{name}-{teacher}-{index}")

        row = {
            "course_id": course_id,
            "course_name": name,
            "teacher": teacher,
            "credits": 1.5,
            "course_type": "公共选修课",
            "course_category": category,
            "domain": profile["domain"],
            "campus": CAMPUSES[stable_index(f"{name}-{teacher}-campus", len(CAMPUSES))],
            "time_slot": infer_time_slot(course, index),
            "location": LOCATIONS[index % len(LOCATIONS)],
            "capacity": limit,
            "current_enrolled": enrolled,
            "current_enrollment_ratio": ratio,
            "popularity_level": hot_level,
            "rush_advice": rush_advice,
            "description": profile["description"],
            "assessment": profile["assessment"],
            "difficulty": profile["difficulty"],
            "workload": profile["workload"],
            "grade_friendly": profile["grade_friendly"],
            "has_exam": 0,
            "group_work_required": 0,
            "suitable_for": profile["suitable_for"],
            "tags": profile["tags"],
            "screenshot_note": note,
        }
        row.update(history)
        rows.append(row)

    _apply_binary_flags(rows, flagged_count=FLAGGED_COURSE_COUNT)
    return rows


def _apply_binary_flags(rows: list[dict[str, object]], flagged_count: int) -> None:
    for row in rows:
        row["has_exam"] = 0
        row["group_work_required"] = 0

    def _pick_rows(category: str, count: int) -> list[dict[str, object]]:
        candidates = [
            row
            for row in rows
            if str(row.get("course_category", "")) == category
        ]
        ranked = sorted(
            candidates,
            key=lambda row: stable_index(f"{row.get('course_id', '')}:flag", 10_000_019),
        )
        return ranked[:count]

    engineering_count = flagged_count // 2
    humanities_count = flagged_count - engineering_count
    selected = _pick_rows("自然科学与工程技术类", engineering_count) + _pick_rows("人文与社会科学类", humanities_count)

    for index, row in enumerate(selected):
        has_exam = 1 if index % 3 != 2 else 0
        group_work_required = 1 if index % 3 != 0 else 0
        row["has_exam"] = has_exam
        row["group_work_required"] = group_work_required


def write_csv(rows: list[dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    print(f"generated {len(rows)} rows -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
