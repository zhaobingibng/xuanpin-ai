export interface RankingItem {
  rank: number
  product_id: number
  name: string
  platform: string
  price: number
  ai_score: number
  trend_score: number
  final_score: number
  level: '爆款' | '潜力' | '一般' | '低潜'
}

export type LevelType = '爆款' | '潜力' | '一般' | '低潜'

export const LEVEL_TAG_TYPE: Record<LevelType, 'danger' | 'warning' | '' | 'info'> = {
  '爆款': 'danger',
  '潜力': 'warning',
  '一般': '',
  '低潜': 'info',
}
