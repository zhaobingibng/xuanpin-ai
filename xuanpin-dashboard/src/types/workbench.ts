/** Dashboard overview KPI data. */
export interface DashboardOverview {
  date: string
  total: number
  hot_products: number
  potential_products: number
  average_score: number
}

/** Review accuracy stats. */
export interface ReviewAccuracy {
  accuracy: number
  total: number
  success: number
}

/** Daily recommendation item. */
export interface Recommendation {
  rank: number
  product_id: number
  name: string
  image: string
  price: number
  recommend_score: number
  knowledge_score: number
  final_score: number
  score: number
  lifecycle: string
  action: string
  confidence: number
  competition_score: number | null
  market_level: string | null
  reasons: string[]
}

/** Daily recommendation response. */
export interface DailyRecommendationResponse {
  date: string
  total: number
  items: Recommendation[]
}

/** Opportunity item from competition analysis. */
export interface Opportunity {
  rank: number
  name: string
  price: number
  score: number
  recommend_score: number
  opportunity_score: number
  competition_score: number
  market_level: string
  action: string
  reasons: string[]
}

/** AI assistant response. */
export interface AssistantResponse {
  answer: string
  products: AssistantProduct[]
  insights: string[]
}

export interface AssistantProduct {
  name: string
  score: number
  reason: string[]
  tags: string[]
  strategy?: ProductStrategy
}

/** Product strategy from generator. */
export interface ProductStrategy {
  product_id: number
  title: string
  selling_points: string[]
  xiaohongshu_copy: string
  xianyu_copy: string
  price_strategy: PriceStrategy
  profit_analysis: ProfitAnalysis
}

export interface PriceStrategy {
  cost: number
  sell: number
  profit: number
}

export interface ProfitAnalysis {
  cost: number
  sell: number
  profit_per_unit: number
  profit_margin: string
  daily_estimate: number
  monthly_estimate: number
}

/** Strategy history record from API. */
export interface StrategyRecord {
  id: number
  product_id: number
  title: string
  selling_points: string[]
  xiaohongshu_copy: string
  xianyu_copy: string
  price_strategy: PriceStrategy
  profit_analysis: ProfitAnalysis
  created_at: string | null
}

/** Action tag type mapping for Element Plus. */
export const ACTION_TAG_TYPE: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
  SELL: 'danger',
  TEST: 'warning',
  WATCH: '',
  DROP: 'info',
}

/** Market level tag type mapping. */
export const MARKET_TAG_TYPE: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
  LOW: 'success',
  MEDIUM: 'warning',
  HIGH: 'danger',
}

/** LLM product analysis result. */
export interface LLMProductAnalysis {
  summary: string
  tags: string[]
  market_insight: string
  selling_points: string[]
  risks: string[]
  recommendation: 'SELL' | 'TEST' | 'WATCH' | 'DROP'
  confidence: number
}

/** LLM report summary result. */
export interface LLMReportSummary {
  summary: string
  highlights: string[]
  warnings: string[]
  action_items: string[]
  market_trend: string
}

/** AI Insights from DailySelectionAnalyzer (Phase 38). */
export interface AiInsights {
  ai_available: boolean
  overall_summary?: string
  highlights?: string[]
  warnings?: string[]
  action_suggestions?: string[]
  profit_insight?: string
  market_trend?: string
  top_pick_notes?: { product_name: string; note: string }[]
  error?: string
}

/** Daily selection report from /api/selection/daily (Phase 39). */
export interface DailySelectionReport {
  date: string
  generated_at: string
  status: string
  stats: {
    total_products: number
    matched_products: number
    total_matches: number
    match_errors: number
    duration: number
  }
  report: {
    top_products: DailySelectionProduct[]
    statistics: Record<string, unknown>
    summary: string
    ai_insights?: AiInsights
  }
}

export interface DailySelectionProduct {
  rank: number
  product_id: number
  name: string
  platform: string
  image: string
  price: number
  score: number
  level: string
  reasons: string[]
  supplier_info?: Record<string, unknown> | null
  estimated_profit?: number | null
  risks?: string[]
}
