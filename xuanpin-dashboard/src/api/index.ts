import axios from 'axios'
import type { RankingItem } from '@/types/ranking'

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
  return api.get(`/products/${id}`)
}

export function getProductTrend(id: number) {
  return api.get(`/products/${id}/trend`)
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

export default api
