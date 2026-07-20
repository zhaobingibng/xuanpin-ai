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
