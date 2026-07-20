export interface ProductHistory {
  price: number
  sales_24h: number
  viewers: number
  ai_score: number | null
  record_time: string
}

export interface Product {
  id: number
  name: string
  platform: string
  price: number
  category: string
  history: ProductHistory[]
}

export interface TrendResult {
  trend_score: number
  sales_growth: number
  view_growth: number
  price_change: number
  level: string
}
