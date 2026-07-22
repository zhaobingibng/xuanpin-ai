<template>
  <div class="recommendation-pool">
    <el-button text @click="router.push('/')" style="margin-bottom: 12px"
      >&larr; 返回首页</el-button
    >

    <div class="page-header">
      <h2>推荐池</h2>
      <span v-if="poolData?.report_date" class="report-date"
        >{{ poolData.report_date }}</span
      >
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="12" class="stats-row" v-loading="statsLoading">
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ totalCount }}</div>
          <div class="stat-label">Total</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card stat-new">
          <div class="stat-value">{{ stats?.status_counts?.NEW ?? 0 }}</div>
          <div class="stat-label">NEW</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card stat-reviewed">
          <div class="stat-value">{{ stats?.status_counts?.REVIEWED ?? 0 }}</div>
          <div class="stat-label">REVIEWED</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card stat-approved">
          <div class="stat-value">{{ stats?.status_counts?.APPROVED ?? 0 }}</div>
          <div class="stat-label">APPROVED</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card stat-rejected">
          <div class="stat-value">{{ stats?.status_counts?.REJECTED ?? 0 }}</div>
          <div class="stat-label">REJECTED</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card stat-published">
          <div class="stat-value">{{ totalReviewed }}</div>
          <div class="stat-label">PUBLISHED</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选 + 操作栏 -->
    <el-card shadow="never" class="filter-card">
      <el-row :gutter="12" align="middle">
        <el-col :span="4">
          <el-select
            v-model="filters.status"
            placeholder="状态"
            clearable
            style="width: 100%"
            @change="fetchPool"
          >
            <el-option
              v-for="s in statusOptions"
              :key="s.value"
              :label="s.label"
              :value="s.value"
            />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select
            v-model="filters.platform"
            placeholder="平台"
            clearable
            style="width: 100%"
            @change="fetchPool"
          >
            <el-option label="淘宝" value="taobao" />
            <el-option label="1688" value="1688" />
            <el-option label="小红书" value="xiaohongshu" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-input-number
            v-model="filters.minScore"
            :min="0"
            :max="100"
            placeholder="最低评分"
            controls-position="right"
            style="width: 100%"
            @change="fetchPool"
          />
        </el-col>
        <el-col :span="4" :offset="8" style="text-align: right">
          <el-button :loading="loading" @click="fetchPool">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 商品表格 -->
    <el-card shadow="never" class="table-card">
      <el-table
        :data="poolItems"
        v-loading="loading"
        stripe
        style="width: 100%"
        @row-click="openDetail"
        row-class-name="clickable-row"
      >
        <el-table-column label="" width="60">
          <template #default="{ row }">
            <el-avatar
              v-if="row.image"
              :src="row.image"
              shape="square"
              size="small"
              fit="cover"
            />
            <el-avatar v-else shape="square" size="small">
              {{ row.name?.charAt(0) ?? '?' }}
            </el-avatar>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="商品名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="90" />
        <el-table-column label="Score" width="80" align="center" sortable prop="score">
          <template #default="{ row }">
            <el-tag
              :type="scoreTagType(row.score)"
              size="small"
              effect="dark"
            >
              {{ row.score }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="利润" width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.estimated_profit" class="profit-text">
              &yen;{{ row.estimated_profit.toFixed(1) }}
            </span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="供应商" width="80" align="center">
          <template #default="{ row }">
            {{ row.supplier_count }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.review_status)" size="small">
              {{ statusLabel(row.review_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审核时间" width="110">
          <template #default="{ row }">
            <span class="time-text">{{ shortDate(row.reviewed_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click.stop="openDetail(row)">
              详情
            </el-button>
            <el-button
              v-if="canApprove(row.review_status)"
              size="small"
              type="success"
              link
              :loading="row._approving"
              @click.stop="handleApprove(row)"
            >
              通过
            </el-button>
            <el-button
              v-if="canReject(row.review_status)"
              size="small"
              type="danger"
              link
              :loading="row._rejecting"
              @click.stop="handleReject(row)"
            >
              驳回
            </el-button>
            <el-button
              v-if="canReset(row.review_status)"
              size="small"
              type="warning"
              link
              :loading="row._resetting"
              @click.stop="handleReset(row)"
            >
              重置
            </el-button>
            <el-button
              v-if="row.review_status === 'APPROVED'"
              size="small"
              type="primary"
              :loading="row._publishing"
              @click.stop="handlePublish(row)"
            >
              发布
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 详情 Drawer -->
    <PoolDetailDrawer
      v-model:visible="drawerVisible"
      :detail="detail"
      :loading="detailLoading"
      @status-updated="onStatusUpdated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getRecommendationPool,
  getRecommendationPoolStats,
  getRecommendationPoolDetail,
  updatePoolStatus,
  publishProduct,
} from '@/api'
import type {
  PoolItem,
  PoolStats,
  PoolDetail,
  PoolStatus,
} from '@/types/recommendation'
import {
  POOL_STATUS_LABELS,
  POOL_STATUS_TAG_TYPES,
} from '@/types/recommendation'
import PoolDetailDrawer from '@/components/PoolDetailDrawer.vue'

const router = useRouter()

// ── 状态 ──────────────────────────────────────────

const loading = ref(false)
const statsLoading = ref(false)
const detailLoading = ref(false)

const poolData = ref<{ report_date: string | null; total: number; items: PoolItem[] } | null>(null)
const poolItems = computed<PoolItem[]>(() => poolData.value?.items ?? [])
const totalCount = computed(() => poolData.value?.total ?? 0)

const stats = ref<PoolStats | null>(null)

const filters = reactive({
  status: undefined as string | undefined,
  platform: undefined as string | undefined,
  minScore: undefined as number | undefined,
})

const statusOptions = [
  { value: 'NEW', label: '待审核' },
  { value: 'REVIEWED', label: '已查看' },
  { value: 'APPROVED', label: '已通过' },
  { value: 'REJECTED', label: '已驳回' },
]

// ── Drawer ────────────────────────────────────────

const drawerVisible = ref(false)
const detail = ref<PoolDetail | null>(null)
const currentProductId = ref<number | null>(null)

// ── 计算 ──────────────────────────────────────────

const totalReviewed = computed(() => {
  if (!stats.value?.status_counts) return 0
  const sc = stats.value.status_counts
  return (sc.APPROVED ?? 0) + (sc.REJECTED ?? 0)
})

// ── Helpers ───────────────────────────────────────

function statusLabel(s: string): string {
  return POOL_STATUS_LABELS[s as PoolStatus] ?? s
}

function statusTagType(s: string): string {
  return POOL_STATUS_TAG_TYPES[s as PoolStatus] ?? 'info'
}

function scoreTagType(score: number): string {
  if (score >= 90) return 'danger'
  if (score >= 70) return 'warning'
  if (score >= 50) return ''
  return 'info'
}

function shortDate(iso: string | null): string {
  if (!iso) return ''
  return iso.slice(0, 10)
}

function canApprove(s: string): boolean {
  return s === 'NEW' || s === 'REVIEWED'
}

function canReject(s: string): boolean {
  return s === 'NEW' || s === 'REVIEWED' || s === 'APPROVED'
}

function canReset(s: string): boolean {
  return s === 'APPROVED' || s === 'REJECTED' || s === 'REVIEWED'
}

// ── Data Fetching ─────────────────────────────────

async function fetchPool() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {}
    if (filters.status) params.status = filters.status
    if (filters.platform) params.platform = filters.platform
    if (filters.minScore !== undefined) params.min_score = filters.minScore
    const { data } = await getRecommendationPool(params)
    poolData.value = data
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error(err?.response?.data?.detail ?? '获取推荐池失败')
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  statsLoading.value = true
  try {
    const { data } = await getRecommendationPoolStats()
    stats.value = data
  } catch {
    // ignore — stats are optional
  } finally {
    statsLoading.value = false
  }
}

async function openDetail(row: PoolItem) {
  currentProductId.value = row.product_id
  drawerVisible.value = true
  await fetchDetail(row.product_id)
}

async function fetchDetail(productId: number) {
  detailLoading.value = true
  try {
    const { data } = await getRecommendationPoolDetail(productId)
    detail.value = data
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error(err?.response?.data?.detail ?? '获取详情失败')
    drawerVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

// ── Actions ───────────────────────────────────────

async function handleApprove(row: PoolItem & { _approving?: boolean }) {
  row._approving = true
  try {
    await updatePoolStatus(row.product_id, { status: 'APPROVED' })
    ElMessage.success(`${row.name} 已通过`)
    await refreshAfterAction()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error(err?.response?.data?.detail ?? '操作失败')
  } finally {
    row._approving = false
  }
}

async function handleReject(row: PoolItem & { _rejecting?: boolean }) {
  row._rejecting = true
  try {
    await updatePoolStatus(row.product_id, { status: 'REJECTED' })
    ElMessage.success(`${row.name} 已驳回`)
    await refreshAfterAction()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error(err?.response?.data?.detail ?? '操作失败')
  } finally {
    row._rejecting = false
  }
}

async function handleReset(row: PoolItem & { _resetting?: boolean }) {
  row._resetting = true
  try {
    await updatePoolStatus(row.product_id, { status: 'NEW' })
    ElMessage.success(`${row.name} 已重置为待审核`)
    await refreshAfterAction()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error(err?.response?.data?.detail ?? '操作失败')
  } finally {
    row._resetting = false
  }
}

async function handlePublish(row: PoolItem & { _publishing?: boolean }) {
  try {
    await ElMessageBox.confirm(
      `确认将「${row.name}」发布到 ${row.platform}？`,
      '确认发布',
      { confirmButtonText: '发布', cancelButtonText: '取消', type: 'info' }
    )
  } catch {
    return // user cancelled
  }

  row._publishing = true
  try {
    const { data } = await publishProduct(row.product_id, {
      platform: row.platform,
    })
    if (data.success) {
      ElMessage.success(`${row.name} 发布成功`)
    } else {
      ElMessage.warning(`${row.name}: ${data.message}`)
    }
    await refreshAfterAction()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error(err?.response?.data?.detail ?? '发布失败')
  } finally {
    row._publishing = false
  }
}

async function refreshAfterAction() {
  await fetchPool()
  await fetchStats()
  // 如果 drawer 打开且是同一个商品，刷新详情
  if (currentProductId.value !== null && drawerVisible.value) {
    await fetchDetail(currentProductId.value)
  }
}

function onStatusUpdated() {
  refreshAfterAction()
}

// ── Init ──────────────────────────────────────────

onMounted(() => {
  fetchPool()
  fetchStats()
})
</script>

<style scoped>
.recommendation-pool {
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
}

.report-date {
  color: #909399;
  font-size: 14px;
}

/* 统计卡片 */
.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-new .stat-value { color: #909399; }
.stat-reviewed .stat-value { color: #e6a23c; }
.stat-approved .stat-value { color: #67c23a; }
.stat-rejected .stat-value { color: #f56c6c; }
.stat-published .stat-value { color: #409eff; }

/* 筛选 */
.filter-card {
  margin-bottom: 16px;
}

/* 表格 */
.table-card {
  margin-bottom: 16px;
}

.muted {
  color: #c0c4cc;
}

.profit-text {
  color: #67c23a;
  font-weight: 600;
}

.time-text {
  font-size: 13px;
  color: #909399;
}

.clickable-row {
  cursor: pointer;
}
</style>
