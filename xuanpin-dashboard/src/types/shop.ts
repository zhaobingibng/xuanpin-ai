export interface Shop {
  id: number
  platform: string
  shop_id: string
  shop_name: string
  shop_url: string | null
  category: string | null
  fans: number
  priority: number
  enabled: boolean
  last_scan_at: string | null
  monitor_strategy: string
  created_at: string | null
  updated_at: string | null
}

export interface ShopCreateRequest {
  platform: string
  shop_id: string
  shop_name: string
  shop_url?: string
  category?: string
  fans?: number
  priority?: number
  enabled?: boolean
  monitor_strategy?: string
}

export interface ShopUpdateRequest {
  shop_name?: string
  shop_url?: string
  category?: string
  fans?: number
  priority?: number
  enabled?: boolean
  monitor_strategy?: string
}
