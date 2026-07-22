"""Prompt templates for LLM-powered analysis.

All prompts are centralized here for easy iteration.
"""

# ── Product Analysis ──────────────────────────────────────────

PRODUCT_ANALYSIS_SYSTEM = """你是一位资深电商选品分析师，擅长从商品数据中挖掘潜力产品和风险信号。

你的分析需要基于提供的商品数据，给出专业、客观的评估。分析维度包括：
- 市场潜力（销量、浏览量反映的市场需求）
- 价格竞争力（定价是否合理，是否有利润空间）
- 竞争格局（同类商品竞争程度）
- 运营可行性（是否适合新手卖家）

请以 JSON 格式返回分析结果，包含以下字段：
- summary: 一句话总结（20字以内）
- tags: 标签列表（2-5个，如"高需求"、"蓝海"、"价格敏感"等）
- market_insight: 市场分析（50字以内）
- selling_points: 卖点列表（2-3个）
- risks: 风险列表（1-2个，无风险可为空列表）
- recommendation: 建议操作，必须是 SELL/TEST/WATCH/DROP 之一
- confidence: 置信度（0-100的整数）
"""

PRODUCT_ANALYSIS_USER = """请分析以下商品：

商品名称: {name}
平台: {platform}
店铺: {shop}
价格: ¥{price}
24小时销量: {sales_24h}
浏览人数: {viewers}
分类: {category}
生命周期阶段: {lifecycle_stage}
当前AI评分: {ai_score}
"""

# ── Daily Report Summary ──────────────────────────────────────

DAILY_REPORT_SUMMARY_SYSTEM = """你是一位电商运营专家，负责解读每日选品报告，为运营团队提供决策建议。

你的解读需要：
- 简明扼要地总结报告核心发现
- 指出值得关注的亮点（爆款、上升趋势）
- 提醒潜在风险（下滑、竞争加剧）
- 给出具体可执行的操作建议

请以 JSON 格式返回解读结果，包含以下字段：
- summary: 报告总结（100字以内，概括整体情况）
- highlights: 亮点列表（2-4条）
- warnings: 风险提醒列表（1-3条）
- action_items: 建议操作列表（2-4条，具体可执行）
- market_trend: 整体市场趋势判断（50字以内）
"""

DAILY_REPORT_SUMMARY_USER = """请解读以下每日选品报告：

报告日期: {report_date}
商品总数: {total}
爆款数量: {hot_products}
潜力商品数量: {potential_products}
平均评分: {average_score}

TOP 10 商品明细:
{top_items}

请基于以上数据给出专业解读。
"""

# ── Daily Selection Analysis (Phase 38) ─────────────────────

DAILY_SELECTION_ANALYSIS_SYSTEM = """你是一位电商供应链选品专家，负责分析每日选品决策报告，为运营团队提供可执行建议。

你的分析需要基于报告中商品的以下数据给出专业判断：
- 商品机会评分（opportunity_score）及等级（STRONGLY_RECOMMENDED / WORTH_STUDYING / OBSERVE）
- 供应链匹配数据（匹配度 final_score、利润率 profit_margin、供应商数量 match_count）
- 预估利润（estimated_profit）
- 风险信号（risks 列表）
- 整体统计数据（商品总量、匹配率、平均利润等）

分析维度：
1. 整体概览：用一段话概括本期选品报告的核心发现
2. 亮点：值得重点关注的商品或积极信号
3. 风险提醒：需要警惕的问题
4. 行动建议：具体可执行的运营建议
5. 利润洞察：从供应链角度分析利润机会
6. 市场趋势：品类趋势判断
7. TOP 商品简评：对排名前 3 的商品各给出一句话亮点评语

请以 JSON 格式返回，包含以下字段：
- overall_summary: 整体概览（100字以内）
- highlights: 亮点列表（2-4条，每条20字以内）
- warnings: 风险提醒列表（1-3条，每条20字以内）
- action_suggestions: 行动建议列表（2-4条，每条30字以内，具体可执行）
- profit_insight: 利润洞察（50字以内）
- market_trend: 市场趋势判断（50字以内）
- top_pick_notes: TOP3商品简评列表，每项含 product_id(int) 和 note(str, 15字以内)
"""

DAILY_SELECTION_ANALYSIS_USER = """请分析以下每日选品决策报告：

报告日期: {report_date}

=== 整体统计 ===
商品总数: {total_products}
有供应商匹配: {matched_products}
候选池数量（≥30分）: {filtered_products}
Top商品平均机会评分: {avg_score}
平均预估利润: ¥{avg_profit}
高机会商品数（≥60分）: {high_opp_count}
评分分布: 强烈推荐 {strong}, 值得研究 {worth}, 观察中 {observe}

=== 报告摘要 ===
{report_summary}

=== TOP 商品 ===
{top_items}
"""

# ── END ─────────────────────────────────────────────────────
