const pptxgen = require("pptxgenjs");
const path = require("path");

let pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Multi-Agent E-Commerce Team";
pres.title = "多智能体电商推荐与营销系统";

// ============================================================
// COLOR PALETTE — Tech/AI Dark Theme
// ============================================================
const C = {
  darkBg: "0F172A",
  darkBg2: "1E293B",
  cyan: "06B6D4",
  cyanDark: "0891B2",
  cyanLight: "67E8F9",
  white: "FFFFFF",
  offWhite: "F8FAFC",
  lightBg: "F1F5F9",
  gray: "94A3B8",
  grayDark: "64748B",
  text: "1E293B",
  textLight: "F8FAFC",
  green: "10B981",
  orange: "F59E0B",
  red: "EF4444",
  purple: "8B5CF6",
  blue: "3B82F6",
  pink: "EC4899",
};

// ============================================================
// HELPERS
// ============================================================
const mkShadow = () => ({ type: "outer", blur: 6, offset: 2, angle: 135, color: "000000", opacity: 0.10 });
const mkShadowCard = () => ({ type: "outer", blur: 4, offset: 1, angle: 135, color: "000000", opacity: 0.08 });

function darkSlide(title) {
  let s = pres.addSlide();
  s.background = { color: C.darkBg };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.05, fill: { color: C.cyan } });
  if (title) {
    s.addText(title, {
      x: 0.7, y: 0.3, w: 8.6, h: 0.7,
      fontSize: 36, fontFace: "Arial Black",
      color: C.white, bold: true, align: "left", valign: "middle", margin: 0,
    });
  }
  return s;
}

function lightSlide(title) {
  let s = pres.addSlide();
  s.background = { color: C.white };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.05, fill: { color: C.cyan } });
  s.addText(title, {
    x: 0.7, y: 0.25, w: 8.6, h: 0.65,
    fontSize: 30, fontFace: "Arial Black",
    color: C.text, bold: true, align: "left", valign: "middle", margin: 0,
  });
  // subtle separator
  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 0.95, w: 1.2, h: 0.035, fill: { color: C.cyan } });
  return s;
}

function cardBg(slide, x, y, w, h, color) {
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color }, shadow: mkShadowCard() });
}

function iconCircle(slide, x, y, size, bgColor, symbol) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: size, h: size, fill: { color: bgColor } });
  slide.addText(symbol, {
    x, y, w: size, h: size,
    fontSize: size * 22, fontFace: "Segoe UI Symbol",
    color: C.white, align: "center", valign: "middle", margin: 0,
  });
}

// ============================================================
// SLIDE 1 — 封面 (Title)
// ============================================================
{
  let s = darkSlide();
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: C.cyan } });

  // decorative shapes
  s.addShape(pres.shapes.OVAL, { x: 7.8, y: 0.8, w: 3.0, h: 3.0, fill: { color: C.cyan, transparency: 92 } });
  s.addShape(pres.shapes.OVAL, { x: 7.0, y: 3.0, w: 2.0, h: 2.0, fill: { color: C.purple, transparency: 90 } });

  s.addText("多智能体电商\n推荐与营销系统", {
    x: 0.9, y: 0.9, w: 6.5, h: 2.4,
    fontSize: 42, fontFace: "Arial Black",
    color: C.white, bold: true, align: "left", valign: "middle", margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.9, y: 3.45, w: 2.4, h: 0.04, fill: { color: C.cyan } });

  s.addText("基于 Supervisor 模式的多智能体协作架构\nPython · Java · Go 三语言实现", {
    x: 0.9, y: 3.65, w: 6.0, h: 0.7,
    fontSize: 15, fontFace: "Calibri",
    color: C.gray, align: "left", valign: "top", margin: 0,
  });

  s.addText([
    { text: "LLM 驱动", options: { fontSize: 13, color: C.grayDark } },
    { text: "  ·  ", options: { fontSize: 13, color: C.cyanDark } },
    { text: "向量检索", options: { fontSize: 13, color: C.grayDark } },
    { text: "  ·  ", options: { fontSize: 13, color: C.cyanDark } },
    { text: "实时特征", options: { fontSize: 13, color: C.grayDark } },
    { text: "  ·  ", options: { fontSize: 13, color: C.cyanDark } },
    { text: "A/B 实验", options: { fontSize: 13, color: C.grayDark } },
    { text: "  ·  ", options: { fontSize: 13, color: C.cyanDark } },
    { text: "合规过滤", options: { fontSize: 13, color: C.grayDark } },
  ], { x: 0.9, y: 4.5, w: 8.0, h: 0.4, align: "left", valign: "middle", margin: 0 });
}

// ============================================================
// SLIDE 2 — 项目背景与目标
// ============================================================
{
  let s = lightSlide("项目背景与目标");

  // Three column cards
  const cards = [
    {
      title: "痛点分析", icon: "⚠", color: C.orange,
      items: [
        "传统推荐系统缺乏语义理解能力",
        "营销文案与推荐结果割裂",
        "库存信息未融入推荐链路",
        "缺乏实时用户行为反馈",
      ],
    },
    {
      title: "解决方案", icon: "✦", color: C.cyan,
      items: [
        "LLM 驱动的语义理解与生成",
        "多智能体协作，解耦关注点",
        "实时特征 + 向量检索混合召回",
        "A/B 实验驱动持续优化",
      ],
    },
    {
      title: "核心目标", icon: "★", color: C.green,
      items: [
        "个性化商品推荐 + 营销文案\n一站式生成",
        "三语言实现，覆盖不同技术栈团队",
        "生产级稳定性：重试 / 降级 / 熔断",
        "可观测性：全链路 Metrics",
      ],
    },
  ];

  const cw = 2.6, ch = 3.5, gap = 0.25, sx = 0.7;
  cards.forEach((card, i) => {
    let cx = sx + i * (cw + gap);
    let cy = 1.2;
    cardBg(s, cx, cy, cw, ch, C.offWhite);
    s.addShape(pres.shapes.RECTANGLE, { x: cx, y: cy, w: cw, h: 0.05, fill: { color: card.color } });

    s.addText(card.title, {
      x: cx + 0.2, y: cy + 0.2, w: cw - 0.4, h: 0.4,
      fontSize: 18, fontFace: "Arial", bold: true, color: C.text, align: "left", valign: "middle", margin: 0,
    });

    const bullets = card.items.map((item, j) => ({
      text: item,
      options: { bullet: true, breakLine: j < card.items.length - 1, fontSize: 12, color: C.grayDark, fontFace: "Calibri" },
    }));
    s.addText(bullets, {
      x: cx + 0.25, y: cy + 0.75, w: cw - 0.5, h: ch - 1.0,
      align: "left", valign: "top", margin: 0, paraSpaceAfter: 6,
    });
  });
}

// ============================================================
// SLIDE 3 — 系统架构全景
// ============================================================
{
  let s = darkSlide("系统架构全景");

  // Architecture layers as horizontal bars
  const layers = [
    { label: "接入层", desc: "FastAPI / Gin / Spring Boot  RESTful API", color: C.cyan, y: 1.1, w: 8.6 },
    { label: "编排层", desc: "Supervisor Orchestrator  并行调度 + 结果聚合", color: C.purple, y: 1.95, w: 8.2 },
    { label: "智能体层", desc: "User Profile · Product Rec · Marketing Copy · Inventory", color: C.blue, y: 2.8, w: 7.8 },
    { label: "AI 层", desc: "LangChain / Spring AI / go-openai  LLM 调用 + 向量检索", color: C.green, y: 3.65, w: 7.4 },
    { label: "数据层", desc: "Redis · Milvus · MySQL  实时特征 + 向量库 + 关系存储", color: C.orange, y: 4.5, w: 7.0 },
  ];

  layers.forEach((l) => {
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y: l.y, w: l.w, h: 0.7,
      fill: { color: l.color, transparency: 85 },
      shadow: mkShadow(),
    });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: l.y, w: 0.08, h: 0.7, fill: { color: l.color } });
    s.addText(l.label, {
      x: 0.95, y: l.y, w: 1.4, h: 0.7,
      fontSize: 13, fontFace: "Arial", bold: true, color: C.white, align: "left", valign: "middle", margin: 0,
    });
    s.addText(l.desc, {
      x: 2.4, y: l.y, w: l.w - 2.6, h: 0.7,
      fontSize: 11, fontFace: "Calibri", color: C.gray, align: "left", valign: "middle", margin: 0,
    });
  });

  // Right side: arrow annotations
  s.addText("← 请求 → 响应", {
    x: 0.7, y: 0.4, w: 2.0, h: 0.4,
    fontSize: 10, fontFace: "Calibri", color: C.cyan, align: "center", margin: 0,
  });
}

// ============================================================
// SLIDE 4 — Supervisor 编排模式
// ============================================================
{
  let s = lightSlide("Supervisor 编排模式 — 核心协作机制");

  // Phase flow diagram
  const phases = [
    { num: "P1", name: "并行阶段一", desc: "用户画像生成\n商品多路召回", time: "~300ms", agents: ["User Profile", "Product Rec"], colors: [C.blue, C.cyan] },
    { num: "P2", name: "并行阶段二", desc: "LLM 重排序\n库存校验与告警", time: "~500ms", agents: ["Product Rec", "Inventory"], colors: [C.cyan, C.orange] },
    { num: "P3", name: "串行阶段三", desc: "结果聚合\n营销文案生成", time: "~400ms", agents: ["Aggregator", "Marketing"], colors: [C.purple, C.pink] },
  ];

  const pw = 2.7, ph = 2.0, pgap = 0.2;
  phases.forEach((p, i) => {
    let px = 0.7 + i * (pw + pgap);
    let py = 1.3;
    cardBg(s, px, py, pw, ph, C.offWhite);
    s.addShape(pres.shapes.RECTANGLE, { x: px, y: py, w: pw, h: 0.05, fill: { color: p.colors[0] } });

    // Phase number circle
    s.addShape(pres.shapes.OVAL, { x: px + 0.15, y: py + 0.3, w: 0.45, h: 0.45, fill: { color: C.darkBg2 } });
    s.addText(p.num, { x: px + 0.15, y: py + 0.3, w: 0.45, h: 0.45, fontSize: 14, fontFace: "Arial", bold: true, color: C.cyan, align: "center", valign: "middle", margin: 0 });

    s.addText(p.name, { x: px + 0.7, y: py + 0.3, w: pw - 0.9, h: 0.45, fontSize: 13, fontFace: "Arial", bold: true, color: C.text, align: "left", valign: "middle", margin: 0 });
    s.addText(p.desc, { x: px + 0.3, y: py + 0.9, w: pw - 0.6, h: 0.55, fontSize: 11, fontFace: "Calibri", color: C.grayDark, align: "left", valign: "top", margin: 0 });
    s.addText(p.time, { x: px + 0.3, y: py + 1.5, w: pw - 0.6, h: 0.35, fontSize: 10, fontFace: "Calibri", color: C.cyanDark, align: "left", valign: "middle", margin: 0 });

    // arrow between phases
    if (i < 2) {
      s.addText("→", {
        x: px + pw, y: py + 0.7, w: pgap, h: 0.5,
        fontSize: 24, fontFace: "Segoe UI Symbol", color: C.cyanDark, align: "center", valign: "middle", margin: 0,
      });
    }
  });

  // Key insight box at bottom
  cardBg(s, 0.7, 3.7, 8.6, 1.2, C.darkBg2);
  s.addText([
    { text: "核心设计理念", options: { bold: true, fontSize: 15, color: C.cyan, breakLine: true } },
    { text: "• 阶段内并行：asyncio.gather / WaitGroup / CompletableFuture → 延迟 = max 非 sum", options: { fontSize: 12, color: C.gray, breakLine: true } },
    { text: "• 阶段间串行：前序阶段输出作为后续阶段输入，保证数据依赖正确", options: { fontSize: 12, color: C.gray, breakLine: true } },
    { text: "• Agent 之间不直接通信，全部通过 Supervisor 中转 → 低耦合、可独立演进", options: { fontSize: 12, color: C.gray } },
  ], { x: 1.0, y: 3.85, w: 8.0, h: 0.95, align: "left", valign: "top", margin: 0 });
}

// ============================================================
// SLIDE 5 — 四大智能体总览
// ============================================================
{
  let s = lightSlide("四大智能体总览");

  const agents = [
    { icon: "👤", name: "用户画像智能体", color: C.blue, desc: "实时特征提取\nRFM 分层评分\n5 类用户分群", time: "~150ms" },
    { icon: "📦", name: "商品推荐智能体", color: C.cyan, desc: "多路混合召回\nLLM 精排重排\n多样性控制", time: "~500ms" },
    { icon: "✏️", name: "营销文案智能体", color: C.purple, desc: "5 套分群模板\nLLM 文案生成\n广告法合规过滤", time: "~400ms" },
    { icon: "📋", name: "库存管理智能体", color: C.orange, desc: "实时库存查询\n缺货/低库存告警\n动态限购计算", time: "~100ms" },
  ];

  const aw = 2.0, ah = 2.8, agap = 0.2, asx = 0.7;
  agents.forEach((a, i) => {
    let ax = asx + i * (aw + agap);
    let ay = 1.2;
    cardBg(s, ax, ay, aw, ah, C.offWhite);
    s.addShape(pres.shapes.RECTANGLE, { x: ax, y: ay, w: aw, h: 0.05, fill: { color: a.color } });

    // icon circle
    s.addShape(pres.shapes.OVAL, { x: ax + (aw - 0.7) / 2, y: ay + 0.25, w: 0.7, h: 0.7, fill: { color: C.darkBg2 } });
    s.addText(a.icon, { x: ax + (aw - 0.7) / 2, y: ay + 0.25, w: 0.7, h: 0.7, fontSize: 24, align: "center", valign: "middle", margin: 0 });

    s.addText(a.name, { x: ax + 0.15, y: ay + 1.1, w: aw - 0.3, h: 0.4, fontSize: 13, fontFace: "Arial", bold: true, color: C.text, align: "center", valign: "middle", margin: 0 });
    s.addText(a.desc, { x: ax + 0.2, y: ay + 1.55, w: aw - 0.4, h: 0.75, fontSize: 11, fontFace: "Calibri", color: C.grayDark, align: "center", valign: "top", margin: 0 });
    s.addText(a.time, { x: ax + 0.2, y: ay + 2.4, w: aw - 0.4, h: 0.3, fontSize: 10, fontFace: "Calibri", color: a.color, align: "center", valign: "middle", margin: 0 });
  });

  // bottom note
  s.addText([
    { text: "数据源：", options: { bold: true, fontSize: 11, color: C.text } },
    { text: "Redis 实时特征 · Milvus 向量库 · MySQL 商品/库存 · LLM 语义理解", options: { fontSize: 11, color: C.grayDark } },
  ], { x: 0.7, y: 4.4, w: 8.6, h: 0.4, align: "left", valign: "middle", margin: 0 });
}

// ============================================================
// SLIDE 6 — 推荐链路详解
// ============================================================
{
  let s = darkSlide("推荐链路详解 — 两阶段混合推荐");

  // Stage 1: Multi-recall
  cardBg(s, 0.5, 1.15, 4.3, 3.8, C.darkBg2);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1.15, w: 4.3, h: 0.05, fill: { color: C.cyan } });
  s.addText("阶段一：多路召回", { x: 0.8, y: 1.3, w: 3.8, h: 0.4, fontSize: 18, fontFace: "Arial", bold: true, color: C.white, margin: 0 });

  const recalls = [
    { name: "协同过滤", desc: "基于用户行为相似度召回", color: C.blue },
    { name: "向量检索", desc: "Milvus 语义向量 Top-K 相似", color: C.green },
    { name: "热门召回", desc: "全站热榜 + 新品 boost", color: C.orange },
    { name: "偏好匹配", desc: "用户偏好品类精准匹配", color: C.purple },
  ];
  recalls.forEach((r, j) => {
    let ry = 1.9 + j * 0.7;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: ry, w: 3.7, h: 0.5, fill: { color: r.color, transparency: 80 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: ry, w: 0.06, h: 0.5, fill: { color: r.color } });
    s.addText(r.name, { x: 1.0, y: ry, w: 1.2, h: 0.5, fontSize: 12, fontFace: "Arial", bold: true, color: C.white, align: "left", valign: "middle", margin: 0 });
    s.addText(r.desc, { x: 2.2, y: ry, w: 2.2, h: 0.5, fontSize: 10, fontFace: "Calibri", color: C.gray, align: "left", valign: "middle", margin: 0 });
  });

  // Arrow
  s.addText("→", { x: 4.65, y: 2.6, w: 0.7, h: 0.6, fontSize: 32, fontFace: "Segoe UI Symbol", color: C.cyan, align: "center", valign: "middle", margin: 0 });

  // Stage 2: LLM Re-rank
  cardBg(s, 5.2, 1.15, 4.3, 3.8, C.darkBg2);
  s.addShape(pres.shapes.RECTANGLE, { x: 5.2, y: 1.15, w: 4.3, h: 0.05, fill: { color: C.pink } });
  s.addText("阶段二：LLM 精排", { x: 5.5, y: 1.3, w: 3.8, h: 0.4, fontSize: 18, fontFace: "Arial", bold: true, color: C.white, margin: 0 });

  const rerankSteps = [
    { name: "候选合并", desc: "去重 + 库存过滤 + 排序", color: C.pink },
    { name: "LLM 打分", desc: "结合用户画像语义重排", color: C.purple },
    { name: "多样性", desc: "品类分散 + 价位覆盖", color: C.blue },
    { name: "Top-N 输出", desc: "最终 10 条推荐结果", color: C.green },
  ];
  rerankSteps.forEach((r, j) => {
    let ry = 1.9 + j * 0.7;
    s.addShape(pres.shapes.RECTANGLE, { x: 5.5, y: ry, w: 3.7, h: 0.5, fill: { color: r.color, transparency: 80 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 5.5, y: ry, w: 0.06, h: 0.5, fill: { color: r.color } });
    s.addText(r.name, { x: 5.7, y: ry, w: 1.2, h: 0.5, fontSize: 12, fontFace: "Arial", bold: true, color: C.white, align: "left", valign: "middle", margin: 0 });
    s.addText(r.desc, { x: 6.9, y: ry, w: 2.2, h: 0.5, fontSize: 10, fontFace: "Calibri", color: C.gray, align: "left", valign: "middle", margin: 0 });
  });
}

// ============================================================
// SLIDE 7 — 稳定性与可靠性设计
// ============================================================
{
  let s = lightSlide("稳定性与可靠性设计");

  // Three-tier stability cards
  const tiers = [
    { name: "第一层：超时控制", color: C.green, items: ["每个 Agent 独立超时配置", "默认 5s，可配置", "防止单个 Agent 拖垮链路"], icon: "⏱" },
    { name: "第二层：指数退避重试", color: C.orange, items: ["tenacity 库实现 Python 版", "最大重试 3 次", "退避间隔 1s → 2s → 4s"], icon: "🔄" },
    { name: "第三层：优雅降级", color: C.red, items: ["LLM 失败 → 规则兜底", "Redis 不可用 → Context 降级", "部分 Agent 失败不影响整体"], icon: "🛡" },
  ];

  const tw = 2.6, th = 2.2, tx = 0.7, tgap = 0.25;
  tiers.forEach((t, i) => {
    let ty = 1.3;
    let px = tx + i * (tw + tgap);
    cardBg(s, px, ty, tw, th, C.offWhite);
    s.addShape(pres.shapes.RECTANGLE, { x: px, y: ty, w: tw, h: 0.05, fill: { color: t.color } });
    s.addText(t.icon + "  " + t.name, { x: px + 0.15, y: ty + 0.15, w: tw - 0.3, h: 0.45, fontSize: 13, fontFace: "Arial", bold: true, color: C.text, margin: 0 });
    const bullets = t.items.map((item, j) => ({
      text: item,
      options: { bullet: true, breakLine: j < t.items.length - 1, fontSize: 11, color: C.grayDark, fontFace: "Calibri" },
    }));
    s.addText(bullets, { x: px + 0.25, y: ty + 0.7, w: tw - 0.5, h: th - 0.9, align: "left", valign: "top", margin: 0, paraSpaceAfter: 4 });
  });

  // Bottom row: structured logging + metrics
  cardBg(s, 0.7, 3.8, 8.6, 1.2, C.offWhite);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 3.8, w: 0.06, h: 1.2, fill: { color: C.cyan } });
  s.addText([
    { text: "可观测性保障", options: { bold: true, fontSize: 14, color: C.text, breakLine: true } },
    { text: "• structlog 结构化日志：每次请求携带 trace_id，全链路追踪", options: { fontSize: 11, color: C.grayDark, breakLine: true } },
    { text: "• prometheus-client 暴露指标：Agent 调用次数 / 成功率 / 平均延迟 / P99", options: { fontSize: 11, color: C.grayDark, breakLine: true } },
    { text: "• 业务事件采集：CTR / CVR / GMV 等业务指标实时记录", options: { fontSize: 11, color: C.grayDark } },
  ], { x: 1.0, y: 3.9, w: 8.0, h: 1.0, align: "left", valign: "top", margin: 0 });
}

// ============================================================
// SLIDE 8 — A/B 实验引擎
// ============================================================
{
  let s = darkSlide("A/B 实验引擎");

  // Two experiment cards
  const exps = [
    {
      title: "实验一：推荐策略对比",
      items: ["对照组：传统规则排序", "实验组：LLM 语义重排序", "流量分配：50/50 → 动态调整"],
      color: C.cyan,
    },
    {
      title: "实验二：文案风格对比",
      items: ["对照组：正式商务风格", "实验组：轻松口语化风格", "分群差异化模板策略"],
      color: C.purple,
    },
  ];

  exps.forEach((exp, i) => {
    let ex = 0.5 + i * 4.6;
    cardBg(s, ex, 1.2, 4.2, 1.8, C.darkBg2);
    s.addShape(pres.shapes.RECTANGLE, { x: ex, y: 1.2, w: 4.2, h: 0.05, fill: { color: exp.color } });
    s.addText(exp.title, { x: ex + 0.3, y: 1.35, w: 3.6, h: 0.35, fontSize: 16, fontFace: "Arial", bold: true, color: C.white, margin: 0 });
    const bullets = exp.items.map((item, j) => ({
      text: item,
      options: { bullet: true, breakLine: j < exp.items.length - 1, fontSize: 12, color: C.gray, fontFace: "Calibri" },
    }));
    s.addText(bullets, { x: ex + 0.4, y: 1.8, w: 3.5, h: 1.0, align: "left", valign: "top", margin: 0, paraSpaceAfter: 4 });
  });

  // Thompson Sampling explanation
  cardBg(s, 0.5, 3.3, 9.0, 2.0, C.darkBg2);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 3.3, w: 0.06, h: 2.0, fill: { color: C.green } });
  s.addText("Thompson Sampling 动态流量分配", { x: 0.9, y: 3.4, w: 8.0, h: 0.4, fontSize: 16, fontFace: "Arial", bold: true, color: C.green, margin: 0 });

  // Flow of Thompson Sampling
  const tsSteps = [
    { label: "分桶", desc: "MD5 哈希\n一致分桶" },
    { label: "采样", desc: "Beta 分布\n随机采样" },
    { label: "比较", desc: "选最大采样值\n分配实验组" },
    { label: "更新", desc: "根据结果\n更新分布参数" },
  ];

  tsSteps.forEach((step, i) => {
    let sx = 0.9 + i * 2.1;
    s.addShape(pres.shapes.OVAL, { x: sx + 0.45, y: 3.95, w: 0.55, h: 0.55, fill: { color: C.cyan, transparency: 80 } });
    s.addText(String(i + 1), { x: sx + 0.45, y: 3.95, w: 0.55, h: 0.55, fontSize: 16, bold: true, color: C.white, align: "center", valign: "middle", margin: 0 });
    s.addText(step.label, { x: sx + 1.1, y: 3.95, w: 0.9, h: 0.55, fontSize: 12, bold: true, color: C.white, align: "left", valign: "middle", margin: 0 });
    if (i < 3) {
      s.addText("→", { x: sx + 1.85, y: 4.0, w: 0.25, h: 0.4, fontSize: 16, color: C.cyan, align: "center", valign: "middle", margin: 0 });
    }
  });

  s.addText("指标收集：曝光 / 点击 / 转化 / GMV  分组统计均值 / 标准差 / 最小值 / 最大值", {
    x: 0.9, y: 4.8, w: 8.2, h: 0.35, fontSize: 11, fontFace: "Calibri", color: C.gray, align: "left", valign: "middle", margin: 0,
  });
}

// ============================================================
// SLIDE 9 — 营销文案与合规
// ============================================================
{
  let s = lightSlide("营销文案生成与合规过滤");

  // Left: Template engine
  cardBg(s, 0.5, 1.2, 4.3, 2.6, C.offWhite);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1.2, w: 4.3, h: 0.05, fill: { color: C.purple } });
  s.addText("分群模板引擎（5 套）", { x: 0.8, y: 1.35, w: 3.8, h: 0.4, fontSize: 16, fontFace: "Arial", bold: true, color: C.text, margin: 0 });

  const templates = [
    { seg: "new_user", label: "新用户", style: "欢迎引导型", tone: "温暖亲切" },
    { seg: "active", label: "活跃用户", style: "新品尝鲜型", tone: "时尚前沿" },
    { seg: "high_value", label: "高价值", style: "尊享推荐型", tone: "品质优先" },
    { seg: "price_sensitive", label: "价格敏感", style: "促销紧迫型", tone: "划算实惠" },
    { seg: "churn_risk", label: "流失风险", style: "挽回激励型", tone: "诚意挽留" },
  ];

  templates.forEach((t, j) => {
    let ty = 1.9 + j * 0.35;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: ty, w: 0.6, h: 0.28, fill: { color: C.purple, transparency: 75 } });
    s.addText(t.label, { x: 0.8, y: ty, w: 0.6, h: 0.28, fontSize: 9, fontFace: "Arial", bold: true, color: C.white, align: "center", valign: "middle", margin: 0 });
    s.addText(t.style + "  ·  " + t.tone, { x: 1.5, y: ty, w: 3.0, h: 0.28, fontSize: 10, fontFace: "Calibri", color: C.grayDark, align: "left", valign: "middle", margin: 0 });
  });

  // Right: Compliance
  cardBg(s, 5.2, 1.2, 4.3, 2.6, C.offWhite);
  s.addShape(pres.shapes.RECTANGLE, { x: 5.2, y: 1.2, w: 4.3, h: 0.05, fill: { color: C.red } });
  s.addText("广告法合规过滤", { x: 5.5, y: 1.35, w: 3.8, h: 0.4, fontSize: 16, fontFace: "Arial", bold: true, color: C.text, margin: 0 });

  const forbidden = ["禁用词", "第一", "最好", "首选", "唯一", "顶级", "绝对", "最", "第一品牌"];
  s.addText("违禁词正则替换列表：", { x: 5.5, y: 1.85, w: 3.5, h: 0.3, fontSize: 11, fontFace: "Arial", bold: true, color: C.text, margin: 0 });

  // forbidden words as tags
  const cols = 4;
  const tagW = 0.85, tagH = 0.28, tagGapX = 0.12, tagGapY = 0.1;
  forbidden.forEach((word, k) => {
    let col = k % cols;
    let row = Math.floor(k / cols);
    let tx = 5.5 + col * (tagW + tagGapX);
    let ty = 2.25 + row * (tagH + tagGapY);
    s.addShape(pres.shapes.RECTANGLE, { x: tx, y: ty, w: tagW, h: tagH, fill: { color: C.red, transparency: 80 } });
    s.addText(word, { x: tx, y: ty, w: tagW, h: tagH, fontSize: 9, fontFace: "Calibri", color: C.red, align: "center", valign: "middle", margin: 0 });
  });

  // Bottom: LLM generation params
  cardBg(s, 0.5, 4.15, 9.0, 1.05, C.offWhite);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 4.15, w: 0.06, h: 1.05, fill: { color: C.cyan } });
  s.addText([
    { text: "LLM 生成参数", options: { bold: true, fontSize: 13, color: C.text, breakLine: true } },
    { text: "Temperature = 0.9（文案创意性）  |  Max Tokens = 512  |  自动拼接：用户名 + 商品卖点 + 优惠信息 → 完整营销文案", options: { fontSize: 11, color: C.grayDark } },
  ], { x: 0.8, y: 4.2, w: 8.3, h: 0.9, align: "left", valign: "top", margin: 0 });
}

// ============================================================
// SLIDE 10 — 三语言技术栈对比
// ============================================================
{
  let s = darkSlide("三语言技术栈对比");

  const stacks = [
    {
      lang: "Python", color: C.blue, icon: "🐍",
      items: ["LangChain / LangGraph", "FastAPI + Uvicorn", "asyncio.gather()", "Pydantic v2", "tenacity 重试", "structlog 日志"],
    },
    {
      lang: "Java", color: C.orange, icon: "☕",
      items: ["Spring Boot 3.4", "Spring AI 1.0", "CompletableFuture", "Spring Data JPA", "Jackson 序列化", "Lombok"],
    },
    {
      lang: "Go", color: C.cyan, icon: "🔷",
      items: ["Gin Web Framework", "go-openai 客户端", "goroutine + WaitGroup", "sync.Mutex 并发安全", "go-redis", "google/uuid"],
    },
  ];

  const scw = 2.8, sch = 3.3, scg = 0.2, scx = 0.5;
  stacks.forEach((st, i) => {
    let sx = scx + i * (scw + scg);
    let sy = 1.1;
    cardBg(s, sx, sy, scw, sch, C.darkBg2);
    s.addShape(pres.shapes.RECTANGLE, { x: sx, y: sy, w: scw, h: 0.05, fill: { color: st.color } });

    s.addText(st.icon + "  " + st.lang, { x: sx + 0.2, y: sy + 0.2, w: scw - 0.4, h: 0.5, fontSize: 20, fontFace: "Arial", bold: true, color: C.white, align: "left", valign: "middle", margin: 0 });

    const bullets = st.items.map((item, j) => ({
      text: item,
      options: { bullet: true, breakLine: j < st.items.length - 1, fontSize: 11, color: C.gray, fontFace: "Calibri" },
    }));
    s.addText(bullets, { x: sx + 0.3, y: sy + 0.85, w: scw - 0.55, h: sch - 1.1, align: "left", valign: "top", margin: 0, paraSpaceAfter: 4 });
  });

  // Bottom shared infrastructure
  cardBg(s, 0.5, 4.65, 9.0, 0.7, C.darkBg2);
  s.addText([
    { text: "共享基础设施", options: { bold: true, color: C.cyanLight } },
    { text: "  |  Redis · Milvus · MySQL · Docker Compose · OpenAI-compatible LLM API", options: { color: C.gray } },
  ], { x: 0.8, y: 4.75, w: 8.4, h: 0.5, fontSize: 12, fontFace: "Calibri", align: "left", valign: "middle", margin: 0 });
}

// ============================================================
// SLIDE 11 — 部署与基础设施
// ============================================================
{
  let s = lightSlide("部署与基础设施");

  // Docker services as cards
  const services = [
    { name: "API 服务", port: "8000", img: "python:3.12-slim", desc: "FastAPI 主服务\n5 个 RESTful 端点\nLifespan 生命周期管理", color: C.blue },
    { name: "Redis", port: "6379", img: "redis:7-alpine", desc: "实时特征存储\nSorted Set 滑动窗口\nRFM 计算引擎", color: C.red },
    { name: "Milvus", port: "19530", img: "milvusdb:v2.4.12", desc: "商品向量库\n语义相似检索\nStandalone 模式", color: C.green },
    { name: "MySQL", port: "3306", img: "mysql:8.0", desc: "商品基础信息\n订单与用户记录\n关系型数据存储", color: C.orange },
  ];

  const ssw = 2.0, ssh = 2.2, ssg = 0.2, ssx = 0.7;
  services.forEach((svc, i) => {
    let sx = ssx + i * (ssw + ssg);
    let sy = 1.2;
    cardBg(s, sx, sy, ssw, ssh, C.offWhite);
    s.addShape(pres.shapes.RECTANGLE, { x: sx, y: sy, w: ssw, h: 0.05, fill: { color: svc.color } });

    s.addText(svc.name, { x: sx + 0.15, y: sy + 0.15, w: ssw - 0.3, h: 0.35, fontSize: 14, fontFace: "Arial", bold: true, color: C.text, align: "center", valign: "middle", margin: 0 });
    s.addText(":" + svc.port, { x: sx + 0.15, y: sy + 0.45, w: ssw - 0.3, h: 0.25, fontSize: 10, fontFace: "Calibri", color: svc.color, align: "center", valign: "middle", margin: 0 });
    s.addText(svc.desc, { x: sx + 0.2, y: sy + 0.8, w: ssw - 0.4, h: 1.1, fontSize: 10, fontFace: "Calibri", color: C.grayDark, align: "center", valign: "top", margin: 0 });
  });

  // Deployment commands
  cardBg(s, 0.7, 3.7, 8.6, 0.55, C.darkBg2);
  s.addText("$ docker-compose up -d    # 一键启动全部服务", {
    x: 1.0, y: 3.78, w: 8.0, h: 0.4, fontSize: 13, fontFace: "Consolas", color: C.cyanLight, align: "left", valign: "middle", margin: 0,
  });

  // Environment variables
  cardBg(s, 0.7, 4.45, 8.6, 0.75, C.offWhite);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 4.45, w: 0.06, h: 0.75, fill: { color: C.cyan } });
  s.addText([
    { text: "环境变量", options: { bold: true, fontSize: 11, color: C.text, breakLine: true } },
    { text: "ECOM_LLM_API_KEY · ECOM_LLM_BASE_URL · ECOM_LLM_MODEL · ECOM_REDIS_URL · ECOM_MILVUS_HOST · ECOM_DATABASE_URL", options: { fontSize: 10, color: C.grayDark } },
  ], { x: 1.0, y: 4.5, w: 8.0, h: 0.65, align: "left", valign: "top", margin: 0 });
}

// ============================================================
// SLIDE 12 — 总结与展望 (Summary)
// ============================================================
{
  let s = darkSlide("总结与展望");

  // Key highlights
  const highlights = [
    { icon: "🚀", title: "架构优势", items: ["Supervisor 编排 · 并行执行", "Agent 解耦 · 可独立演进", "三语言实现 · 多团队适配"], color: C.cyan },
    { icon: "⚡", title: "性能指标", items: ["总延迟 ~1.2s（三阶段流水线）", "并行阶段延迟 = max 非 sum", "Redis 实时特征 ms 级响应"], color: C.green },
    { icon: "🔮", title: "未来方向", items: ["更多 Agent：客服 / 比价 / 物流", "多模态支持：图片 + 视频理解", "强化学习：长期 Reward 优化"], color: C.purple },
  ];

  const hw = 2.8, hh = 2.0, hx = 0.5, hg = 0.2;
  highlights.forEach((h, i) => {
    let px = hx + i * (hw + hg);
    let py = 1.2;
    cardBg(s, px, py, hw, hh, C.darkBg2);
    s.addShape(pres.shapes.RECTANGLE, { x: px, y: py, w: hw, h: 0.05, fill: { color: h.color } });
    s.addText(h.icon + "  " + h.title, { x: px + 0.15, y: py + 0.15, w: hw - 0.3, h: 0.4, fontSize: 15, fontFace: "Arial", bold: true, color: C.white, margin: 0 });
    const bullets = h.items.map((item, j) => ({
      text: item,
      options: { bullet: true, breakLine: j < h.items.length - 1, fontSize: 11, color: C.gray, fontFace: "Calibri" },
    }));
    s.addText(bullets, { x: px + 0.25, y: py + 0.65, w: hw - 0.45, h: hh - 0.8, align: "left", valign: "top", margin: 0, paraSpaceAfter: 4 });
  });

  // Bottom closing
  s.addShape(pres.shapes.RECTANGLE, { x: 2.5, y: 3.7, w: 5.0, h: 0.04, fill: { color: C.cyan } });
  s.addText("以 LLM 为大脑 · 以 Supervisor 为神经中枢 · 以多 Agent 为双手", {
    x: 0.5, y: 3.9, w: 9.0, h: 0.5,
    fontSize: 14, fontFace: "Calibri", color: C.gray, align: "center", valign: "middle", margin: 0,
  });
  s.addText("多智能体协同，构建下一代智能电商推荐系统", {
    x: 0.5, y: 4.3, w: 9.0, h: 0.6,
    fontSize: 18, fontFace: "Arial Black", bold: true, color: C.cyan, align: "center", valign: "middle", margin: 0,
  });

  s.addText("Q & A", {
    x: 3.5, y: 4.85, w: 3.0, h: 0.5,
    fontSize: 24, fontFace: "Arial Black", bold: true, color: C.white, align: "center", valign: "middle", margin: 0,
  });
}

// ============================================================
// EXPORT
// ============================================================
const outPath = path.join(__dirname, "multi-agent-ecommerce-system.pptx");
pres.writeFile({ fileName: outPath }).then(() => {
  console.log("Presentation saved to:", outPath);
}).catch(err => {
  console.error("Error:", err);
});
