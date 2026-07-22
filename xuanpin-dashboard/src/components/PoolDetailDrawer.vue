<template>
  <el-drawer
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="商品详情"
    size="600px"
    :before-close="() => $emit('update:visible', false)"
  >
    <template v-if="loading">
      <div class="drawer-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        加载中...
      </div>
    </template>

    <template v-else-if="detail">
      <!-- 商品基本信息 -->
      <el-descriptions :column="2" border size="small" class="detail-section">
        <el-descriptions-item label="商品图片" :span="2">
          <el-image
            v-if="detail.image"
            :src="detail.image"
            fit="cover"
            style="width: 120px; height: 120px; border-radius: 4px"
            :preview-src-list="[detail.image]"
            preview-teleported
          />
          <span v-else class="muted">无图片</span>
        </el-descriptions-item>
        <el-descriptions-item label="名称" :span="2">
          {{ detail.name }}
        </el-descriptions-item>
        <el-descriptions-item label="平台">{{ detail.platform }}</el-descriptions-item>
        <el-descriptions-item label="店铺">{{ detail.shop }}</el-descriptions-item>
        <el-descriptions-item label="价格">&yen;{{ detail.price }}</el-descriptions-item>
        <el-descriptions-item label="生命周期">
          <el-tag size="small">{{ detail.lifecycle_stage }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="排名">{{ detail.rank ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="评分">
          <el-tag
            v-if="detail.score !== null"
            :type="scoreTagType(detail.score)"
            size="small"
            effect="dark"
          >
            {{ detail.score }}
          </el-tag>
          <span v-else class="muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="等级">{{ detail.level ?? '-' }}</el-descriptions-item>
      </el-descriptions>

      <!-- 推荐原因 -->
      <el-card shadow="never" class="detail-section" v-if="parsedReasons.length">
        <template #header><span class="card-title">推荐原因</span></template>
        <el-tag
          v-for="(reason, idx) in parsedReasons"
          :key="idx"
          class="reason-tag"
          size="small"
        >
          {{ reason }}
        </el-tag>
      </el-card>

      <!-- 匹配供应商 -->
      <el-card shadow="never" class="detail-section" v-if="detail.supplier_matches?.length">
        <template #header>
          <span class="card-title">匹配供应商 ({{ detail.supplier_matches.length }})</span>
        </template>
        <el-table :data="detail.supplier_matches" size="small" stripe>
          <el-table-column prop="supplier_title" label="供应商" min-width="180" show-overflow-tooltip />
          <el-table-column label="价格" width="100" align="right">
            <template #default="{ row: sm }">&yen;{{ sm.supplier_price }}</template>
          </el-table-column>
          <el-table-column label="相似度" width="90" align="center">
            <template #default="{ row: sm }">
              {{ (sm.similarity_score * 100).toFixed(0) }}%
            </template>
          </el-table-column>
          <el-table-column label="预估利润" width="100" align="right">
            <template #default="{ row: sm }">
              <span class="profit-text">&yen;{{ sm.estimated_profit.toFixed(1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="利润率" width="80" align="center">
            <template #default="{ row: sm }">
              {{ (sm.profit_margin * 100).toFixed(0) }}%
            </template>
          </el-table-column>
          <el-table-column label="Rank" width="60" align="center" prop="rank" />
        </el-table>
      </el-card>

      <!-- 审核状态 -->
      <el-card shadow="never" class="detail-section">
        <template #header>
          <div class="card-header-row">
            <span class="card-title">审核状态</span>
            <el-tag :type="statusTagType(detail.review_status)" size="small">
              {{ statusLabel(detail.review_status) }}
            </el-tag>
          </div>
        </template>

        <el-form label-width="80px" size="small">
          <el-form-item label="审核备注">
            <span v-if="detail.review_notes" class="notes-text">{{ detail.review_notes }}</span>
            <span v-else class="muted">无</span>
          </el-form-item>
          <el-form-item label="审核时间">
            {{ detail.reviewed_at ? formatDateTime(detail.reviewed_at) : '-' }}
          </el-form-item>
        </el-form>

        <!-- 审核操作 -->
        <el-divider />
        <el-row :gutter="8">
          <el-col :span="8">
            <el-button
              type="success"
              :disabled="!canApprove(detail.review_status)"
              :loading="actionLoading"
              @click="handleAction('APPROVED')"
              style="width: 100%"
            >
              通过 (Approve)
            </el-button>
          </el-col>
          <el-col :span="8">
            <el-button
              type="danger"
              :disabled="!canReject(detail.review_status)"
              :loading="actionLoading"
              @click="handleAction('REJECTED')"
              style="width: 100%"
            >
              驳回 (Reject)
            </el-button>
          </el-col>
          <el-col :span="8">
            <el-button
              type="warning"
              :disabled="!canReset(detail.review_status)"
              :loading="actionLoading"
              @click="handleAction('NEW')"
              style="width: 100%"
            >
              重置 (Reset)
            </el-button>
          </el-col>
        </el-row>
      </el-card>

      <!-- 发布历史 -->
      <el-card shadow="never" class="detail-section" v-if="publishHistory.length > 0">
        <template #header>
          <span class="card-title">发布历史</span>
        </template>
        <el-timeline>
          <el-timeline-item
            v-for="record in publishHistory"
            :key="record.id"
            :timestamp="record.created_at?.substring(0, 16) ?? '-'"
            :type="record.status === 'SUCCESS' ? 'success' : record.status === 'FAILED' ? 'danger' : 'warning'"
            placement="top"
          >
            <el-tag
              :type="record.status === 'SUCCESS' ? 'success' : record.status === 'FAILED' ? 'danger' : 'warning'"
              size="small"
            >
              {{ record.status === 'SUCCESS' ? '成功' : record.status === 'FAILED' ? '失败' : '发布中' }}
            </el-tag>
            <span class="ml-2">{{ record.platform }}</span>
            <div v-if="record.error_message" class="error-msg mt-1">
              {{ record.error_message }}
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </template>

    <template v-else>
      <el-empty description="无法加载详情" />
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { updatePoolStatus, getPublishHistory } from '@/api'
import type { PoolDetail, PoolStatus, PublishHistoryRecord } from '@/types/recommendation'
import { POOL_STATUS_LABELS, POOL_STATUS_TAG_TYPES } from '@/types/recommendation'

const props = defineProps<{
  visible: boolean
  detail: PoolDetail | null
  loading: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'statusUpdated': []
}>()

const actionLoading = ref(false)

// ── Publish history ────────────────────────────────

const publishHistory = ref<PublishHistoryRecord[]>([])

watch(
  () => props.detail?.product_id,
  async (pid) => {
    if (pid) {
      try {
        const { data } = await getPublishHistory(pid, 10)
        publishHistory.value = data.records ?? []
      } catch {
        publishHistory.value = []
      }
    } else {
      publishHistory.value = []
    }
  }
)

// ── Computed ──────────────────────────────────────

const parsedReasons = computed<string[]>(() => {
  if (!props.detail?.reasons) return []
  try {
    const parsed = JSON.parse(props.detail.reasons)
    if (Array.isArray(parsed)) return parsed.map(String)
  } catch {
    // fallback — split by comma or return raw
  }
  return props.detail.reasons
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
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

function canApprove(s: string): boolean {
  return s === 'NEW' || s === 'REVIEWED'
}

function canReject(s: string): boolean {
  return s === 'NEW' || s === 'REVIEWED' || s === 'APPROVED'
}

function canReset(s: string): boolean {
  return s === 'APPROVED' || s === 'REJECTED' || s === 'REVIEWED'
}

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── Actions ───────────────────────────────────────

async function handleAction(status: PoolStatus) {
  if (!props.detail) return
  actionLoading.value = true
  try {
    await updatePoolStatus(props.detail.product_id, { status })
    ElMessage.success(
      `${props.detail.name} → ${POOL_STATUS_LABELS[status]}`
    )
    emit('statusUpdated')
    emit('update:visible', false)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error(err?.response?.data?.detail ?? '操作失败')
  } finally {
    actionLoading.value = false
  }
}
</script>

<style scoped>
.drawer-loading {
  text-align: center;
  padding: 40px;
  color: #909399;
}

.detail-section {
  margin-bottom: 16px;
}

.card-title {
  font-weight: 600;
  font-size: 14px;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.muted {
  color: #c0c4cc;
}

.profit-text {
  color: #67c23a;
  font-weight: 600;
}

.notes-text {
  color: #606266;
}

.reason-tag {
  margin-right: 8px;
  margin-bottom: 4px;
}
</style>
