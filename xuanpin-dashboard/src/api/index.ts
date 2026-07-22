import axios from 'axios'
import type { RankingItem } from '@/types/ranking'
import type { Product, TrendResult } from '@/types/product'
import type { DailyReport } from '@/types/report'
import type {
  DashboardOverview,
  ReviewAccuracy,
  DailyRecommendationResponse,
  Opportunity,
  AssistantResponse,
  StrategyRecord,
  LLMProductAnalysis,
  LLMReportSummary,
} from '@/types/workbench'
import type { Shop, ShopCreateRequest, ShopUpdateRequest } from '@/types/shop'
import type { DailySelectionReport } from '@/types/workbench'

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── 健康检查 ──────────────────────────────────────
export function getHealth() {
  return api.get<{ status: string; app: string }>('/health')
}

// ── 商品 ──────────────────────────────────────────
export function getProducts() {
  return api.get('/products')
}

export function getProduct(id: number) {
  return api.get<Product>(`/products/${id}`)
}

export function getProductTrend(id: number) {
  return api.get<TrendResult>(`/products/${id}/trend`)
}

// ── 排行榜 ────────────────────────────────────────
export function getTop100() {
  return api.get<RankingItem[]>('/ranking/top100')
}

// ── 统计 ──────────────────────────────────────────
export function getCategoryStats() {
  return api.get<Record<string, number>>('/stats/category')
}

export function getPlatformStats() {
  return api.get<Record<string, number>>('/stats/platform')
}

// ── 日报 ──────────────────────────────────────────
export function getDailyReport(limit?: number) {
  const params = limit !== undefined ? { limit } : undefined
  return api.get<DailyReport>('/reports/daily', { params })
}

// ── 运营工作台 ─────────────────────────────────────
export function getWorkbenchOverview() {
  return api.get<DashboardOverview>('/dashboard/overview')
}

export function getReviewAccuracy() {
  return api.get<ReviewAccuracy>('/reviews/accuracy')
}

export function getDailyRecommendations() {
  return api.get<DailyRecommendationResponse>('/recommendations/daily')
}

export function getOpportunities() {
  return api.get<Opportunity[]>('/recommendations/opportunities')
}

export function askAssistant(question: string) {
  return api.post<AssistantResponse>('/assistant/ask', { question })
}

export function getStrategy(productId: number) {
  return api.get<StrategyRecord[]>(`/strategy/${productId}`)
}

export function generateStrategy(productId: number) {
  return api.post<{ title: string; selling_points: string[]; xiaohongshu_copy: string; xianyu_copy: string; price_strategy: { cost: number; sell: number; profit: number }; profit_analysis: { cost: number; sell: number; profit_per_unit: number; profit_margin: string; daily_estimate: number; monthly_estimate: number } }>('/strategy/generate', { product_id: productId })
}

// ── 店铺注册表 ─────────────────────────────────────
export function getShops() {
  return api.get<Shop[]>('/api/shops')
}

export function createShop(data: ShopCreateRequest) {
  return api.post<Shop>('/api/shops', data)
}

export function updateShop(id: number, data: ShopUpdateRequest) {
  return api.patch<Shop>(`/api/shops/${id}`, data)
}

export function deleteShop(id: number) {
  return api.delete<{ message: string }>(`/api/shops/${id}`)
}

// ── AI 分析 ─────────────────────────────────────────
export function getLLMStatus() {
  return api.get<{ available: boolean; model?: string; reason?: string }>('/api/ai-analysis/status')
}

export function analyzeProductWithLLM(productId: number) {
  return api.post<{
    product_id: number
    product_name: string
    ai_score: number
    llm_analysis?: LLMProductAnalysis
    error?: string
    fallback?: boolean
  }>(`/api/ai-analysis/product/${productId}`)
}

export function summarizeReportWithLLM(reportId: number) {
  return api.post<{
    report_id: number
    report_date: string
    llm_summary?: LLMReportSummary
    error?: string
    fallback?: boolean
  }>(`/api/ai-analysis/report/${reportId}/summary`)
}

// ── 每日选品报告（Pipeline + AI 分析）─────────────────────
export function getDailySelectionReport() {
  return api.get<DailySelectionReport>('/api/selection/daily')
}

// ── AI 自动选品开关 ─────────────────────────────────────
export function getSelectionStatus() {
  return api.get<{ enabled: boolean }>('/system/selection/status')
}

export function toggleSelection(enabled: boolean) {
  return api.post<{ enabled: boolean; message: string }>('/system/selection/toggle', { enabled })
}

export default api
