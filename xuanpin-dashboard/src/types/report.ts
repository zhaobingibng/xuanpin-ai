import type { LevelType } from './ranking'

export interface ReportItem {
  rank: number
  product_id: number
  name: string
  platform: string
  image: string
  price: number
  score: number
  level: LevelType
  reasons: string[]
}

export interface DailyReport {
  date: string
  total: number
  hot_products: number
  potential_products: number
  average_score: number
  items: ReportItem[]
}

export const REPORT_LEVEL_TAG_TYPE: Record<LevelType, 'danger' | 'warning' | '' | 'info'> = {
  '爆款': 'danger',
  '潜力': 'warning',
  '一般': '',
  '低潜': 'info',
}
