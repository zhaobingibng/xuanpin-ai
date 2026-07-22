/** Recommendation Pool 类型定义 (Phase 46.2). */

// ── 审核状态 ──────────────────────────────────────────

export type PoolStatus = 'NEW' | 'REVIEWED' | 'APPROVED' | 'REJECTED' | 'PUBLISHED'

export const POOL_STATUS_LABELS: Record<PoolStatus, string> = {
  NEW: '待审核',
  REVIEWED: '已查看',
  APPROVED: '已通过',
  REJECTED: '已驳回',
  PUBLISHED: '已发布',
}

export const POOL_STATUS_TAG_TYPES: Record<PoolStatus, string> = {
  NEW: 'info',
  REVIEWED: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
  PUBLISHED: 'primary',
}

// ── 推荐池列表项 ──────────────────────────────────────

export interface PoolItem {
  product_id: number
  rank: number
  name: string
  platform: string
  shop: string
  image: string
  price: number
  score: number
  level: string
  reasons: string
  action: string
  best_supplier_title: string
  best_supplier_price: number | null
  best_supplier_url: string
  estimated_profit: number
  profit_margin: number
  match_score: number | null
  supplier_count: number
  review_status: string
  review_notes: string | null
  reviewed_at: string | null
}

// ── 推荐池列表响应 ────────────────────────────────────

export interface PoolListResponse {
  report_date: string | null
  total: number
  items: PoolItem[]
}

// ── 推荐池统计 ────────────────────────────────────────

export interface PoolStats {
  report_date: string | null
  status_counts: Record<string, number>
}

// ── 供应商匹配（详情中的子对象） ──────────────────────

export interface SupplierMatchDetail {
  supplier_product_id: number
  supplier_title: string
  supplier_price: number
  supplier_url: string
  similarity_score: number
  estimated_profit: number
  profit_margin: number
  rank: number
}

// ── 推荐池详情 ────────────────────────────────────────

export interface PoolDetail {
  product_id: number
  name: string
  platform: string
  shop: string
  image: string
  price: number
  url: string
  lifecycle_stage: string
  rank: number | null
  score: number | null
  level: string | null
  reasons: string | null
  supplier_matches: SupplierMatchDetail[]
  review_status: string
  review_notes: string | null
  reviewed_at: string | null
}

// ── 审核状态更新请求 ──────────────────────────────────

export interface UpdateStatusRequest {
  status: PoolStatus
  notes?: string
  report_date?: string
}

// ── 审核状态更新响应 ──────────────────────────────────

export interface UpdateStatusResponse {
  success: boolean
  product_id: number
  status: string
  previous_status: string
  reviewed_at: string | null
  report_date: string
}

// ── 发布相关 (Phase 46.4) ─────────────────────────────

export interface PublishResponse {
  success: boolean
  publish_status: string
  message: string
  record_id: number
  product_id: number
  published_at?: string
}

export interface PublishHistoryRecord {
  id: number
  product_id: number
  status: string
  platform: string
  error_message: string | null
  retry_count: number
  created_at: string | null
  published_at: string | null
}

export interface PublishHistoryResponse {
  product_id: number
  total: number
  records: PublishHistoryRecord[]
}

export const PUBLISH_STATUS_LABELS: Record<string, string> = {
  PENDING: '发布中',
  SUCCESS: '成功',
  FAILED: '失败',
}

export const PUBLISH_STATUS_TAG_TYPES: Record<string, string> = {
  PENDING: 'warning',
  SUCCESS: 'success',
  FAILED: 'danger',
}
