<template>
  <div class="dashboard">
    <h2>今日爆款 TOP100</h2>

    <el-card class="status-card">
      <template #header>
        <span>API状态</span>
      </template>
      <div v-if="loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        检测中...
      </div>
      <div v-else-if="health">
        <el-tag :type="health.status === 'ok' ? 'success' : 'danger'" size="large">
          {{ health.status === 'ok' ? '正常' : '异常' }}
        </el-tag>
        <p style="margin-top: 12px; color: #666;">
          应用: {{ health.app }}
        </p>
      </div>
      <div v-else>
        <el-tag type="danger" size="large">无法连接后端</el-tag>
        <p style="margin-top: 12px; color: #999;">
          请确保后端服务运行在 http://127.0.0.1:8000
        </p>
      </div>
    </el-card>

    <el-row :gutter="20" class="chart-row">
      <el-col :span="12">
        <CategoryChart />
      </el-col>
      <el-col :span="12">
        <PlatformChart />
      </el-col>
    </el-row>

    <el-row :gutter="16" class="entry-row">
      <el-col :span="12">
        <el-card class="entry-card" shadow="hover" @click="router.push('/reports/daily')">
          <div class="entry-content">
            <span class="entry-icon">&#128293;</span>
            <div>
              <h3 class="entry-title">今日AI选品</h3>
              <p class="entry-desc">查看AI评分推荐的每日选品报告</p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="entry-card toggle-card" shadow="hover">
          <div class="entry-content">
            <span class="entry-icon">{{ selectionEnabled ? '&#128994;' : '&#128308;' }}</span>
            <div>
              <h3 class="entry-title">
                {{ selectionEnabled ? 'AI自动选品已开启' : 'AI自动选品已关闭' }}
              </h3>
              <p class="entry-desc">{{ selectionEnabled ? '每日自动运行选品流水线' : '定时选品任务已暂停' }}</p>
            </div>
            <el-switch
              v-model="selectionEnabled"
              :loading="selectionToggling"
              inline-prompt
              active-text="开"
              inactive-text="关"
              @change="handleSelectionToggle"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="entry-row">
      <el-col :span="12">
        <el-card class="entry-card" shadow="hover" @click="router.push('/tasks')">
          <div class="entry-content">
            <span class="entry-icon">&#9202;</span>
            <div>
              <h3 class="entry-title">任务调度中心</h3>
              <p class="entry-desc">查看定时任务状态、执行历史与手动运行</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Phase 42.6: 淘宝人工辅助采集面板 -->
    <el-card class="taobao-card">
      <template #header>
        <div class="taobao-header">
          <span>淘宝采集操控台</span>
          <el-tag
            :type="taobaoStateTagType"
            size="small"
          >
            {{ taobaoStateLabel }}
          </el-tag>
        </div>
      </template>

      <div v-if="taobaoLoading" class="taobao-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        加载中...
      </div>

      <div v-else class="taobao-body">
        <!-- 状态信息 -->
        <el-row :gutter="16" class="taobao-info-row">
          <el-col :span="6">
            <div class="info-item">
              <span class="info-label">登录状态</span>
              <el-tag :type="taobaoStatus?.is_logged_in ? 'success' : 'warning'" size="small">
                {{ taobaoStatus?.is_logged_in ? '已登录' : '未登录' }}
              </el-tag>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="info-item">
              <span class="info-label">风控状态</span>
              <el-tag :type="taobaoStatus?.is_blocked ? 'danger' : 'success'" size="small">
                {{ taobaoStatus?.is_blocked ? '已拦截' : '正常' }}
              </el-tag>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="info-item">
              <span class="info-label">淘宝商品</span>
              <strong>{{ taobaoStatus?.product_count ?? '-' }}</strong>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="info-item">
              <span class="info-label">最近采集</span>
              <span class="info-value">{{ taobaoStatus?.last_crawl_keyword || '无' }}</span>
            </div>
          </el-col>
        </el-row>

        <!-- 消息 -->
        <el-alert
          v-if="taobaoStatus?.message"
          :title="taobaoStatus.message"
          :type="taobaoAlertType"
          :closable="false"
          class="taobao-alert"
          show-icon
        />

        <!-- 操控按钮 -->
        <el-row :gutter="12" class="taobao-actions">
          <el-col :span="4">
            <el-button
              v-if="!taobaoActive"
              type="primary"
              :loading="taobaoActionLoading"
              @click="handleTaobaoStart"
            >
              启动会话
            </el-button>
            <el-button
              v-else
              type="danger"
              :loading="taobaoActionLoading"
              @click="handleTaobaoStop"
            >
              关闭会话
            </el-button>
          </el-col>
          <el-col :span="4">
            <el-button
              :disabled="!taobaoActive"
              :loading="taobaoActionLoading"
              @click="handleTaobaoCheck"
            >
              检测状态
            </el-button>
          </el-col>
          <el-col :span="8">
            <el-input
              v-model="taobaoKeyword"
              placeholder="输入关键词"
              :disabled="!taobaoCanCrawl"
              size="default"
            >
              <template #prepend>关键词</template>
            </el-input>
          </el-col>
          <el-col :span="4">
            <el-button
              type="success"
              :disabled="!taobaoCanCrawl"
              :loading="taobaoActionLoading"
              @click="handleTaobaoCrawl"
            >
              采集 ({{ taobaoLimit }}条)
            </el-button>
          </el-col>
          <el-col :span="4">
            <el-button
              v-if="taobaoStatus?.is_blocked"
              type="warning"
              :loading="taobaoActionLoading"
              @click="handleTaobaoWaitHuman"
            >
              等待人工
            </el-button>
          </el-col>
        </el-row>

        <!-- 最近采集结果 -->
        <div v-if="taobaoStatus?.last_crawl" class="taobao-result">
          <span>
            最近采集: <strong>{{ taobaoStatus.last_crawl_keyword }}</strong>
            → {{ taobaoStatus.last_crawl_count }} 条
            ({{ formatTime(taobaoStatus.last_crawl) }})
          </span>
        </div>
      </div>
    </el-card>

    <TopRankingTable />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'
import {
  getHealth,
  getSelectionStatus,
  toggleSelection,
  getTaobaoStatus,
  startTaobaoSession,
  stopTaobaoSession,
  checkTaobaoSession,
  crawlTaobao,
  waitHumanTaobao,
  type TaobaoStatus,
} from '@/api'
import TopRankingTable from '@/components/TopRankingTable.vue'
import CategoryChart from '@/components/CategoryChart.vue'
import PlatformChart from '@/components/PlatformChart.vue'
import { ElMessage } from 'element-plus'

interface HealthInfo {
  status: string
  app: string
}

const router = useRouter()
const loading = ref(true)
const health = ref<HealthInfo | null>(null)
const selectionEnabled = ref(false)
const selectionToggling = ref(false)

// ── 淘宝操控台 (Phase 42.6) ──────────────────────────
const taobaoLoading = ref(true)
const taobaoStatus = ref<TaobaoStatus | null>(null)
const taobaoActionLoading = ref(false)
const taobaoKeyword = ref('海苔卷')
const taobaoLimit = ref(10)

const taobaoActive = computed(() => {
  const s = taobaoStatus.value?.state
  return s && s !== 'idle' && s !== 'error' && s !== 'stopping'
})

const taobaoCanCrawl = computed(() => {
  const s = taobaoStatus.value?.state
  return s === 'logged_in'
})

const taobaoStateLabel = computed(() => {
  const labels: Record<string, string> = {
    idle: '未启动',
    starting: '启动中',
    logged_in: '已登录',
    crawling: '采集中',
    blocked: '风控拦截',
    waiting_human: '等待人工',
    stopping: '关闭中',
    error: '异常',
  }
  return labels[taobaoStatus.value?.state ?? 'idle'] ?? '未知'
})

const taobaoStateTagType = computed(() => {
  const types: Record<string, string> = {
    idle: 'info',
    starting: 'warning',
    logged_in: 'success',
    crawling: 'warning',
    blocked: 'danger',
    waiting_human: 'warning',
    stopping: 'info',
    error: 'danger',
  }
  return types[taobaoStatus.value?.state ?? 'idle'] ?? 'info'
})

const taobaoAlertType = computed(() => {
  if (taobaoStatus.value?.is_blocked) return 'error'
  if (taobaoStatus.value?.state === 'logged_in') return 'success'
  if (taobaoStatus.value?.state === 'crawling') return 'warning'
  return 'info'
})

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function fetchTaobaoStatus() {
  try {
    const { data } = await getTaobaoStatus()
    taobaoStatus.value = data
  } catch {
    // ignore
  } finally {
    taobaoLoading.value = false
  }
}

async function handleTaobaoStart() {
  taobaoActionLoading.value = true
  try {
    const { data } = await startTaobaoSession()
    taobaoStatus.value = data as unknown as TaobaoStatus
    ElMessage.success(data.message || '会话已启动')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '启动失败')
  } finally {
    taobaoActionLoading.value = false
  }
}

async function handleTaobaoStop() {
  taobaoActionLoading.value = true
  try {
    const { data } = await stopTaobaoSession()
    taobaoStatus.value = data as unknown as TaobaoStatus
    ElMessage.info(data.message || '会话已关闭')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '关闭失败')
  } finally {
    taobaoActionLoading.value = false
  }
}

async function handleTaobaoCheck() {
  taobaoActionLoading.value = true
  try {
    const { data } = await checkTaobaoSession()
    taobaoStatus.value = { ...taobaoStatus.value!, ...data }
    ElMessage.success(data.message || '检测完成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '检测失败')
  } finally {
    taobaoActionLoading.value = false
  }
}

async function handleTaobaoCrawl() {
  if (!taobaoKeyword.value.trim()) {
    ElMessage.warning('请输入关键词')
    return
  }
  taobaoActionLoading.value = true
  try {
    const { data } = await crawlTaobao(taobaoKeyword.value, taobaoLimit.value)
    taobaoStatus.value = { ...taobaoStatus.value!, ...data }
    if (data.success) {
      ElMessage.success(`采集完成: ${data.count} 条商品`)
    } else {
      ElMessage.warning(data.message || '未采集到商品')
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '采集失败')
  } finally {
    taobaoActionLoading.value = false
  }
}

async function handleTaobaoWaitHuman() {
  taobaoActionLoading.value = true
  try {
    ElMessage.info('开始等待人工处理风控，最长5分钟...')
    const { data } = await waitHumanTaobao()
    taobaoStatus.value = { ...taobaoStatus.value!, ...data }
    if (!data.is_blocked) {
      ElMessage.success(data.message || '风控已解除')
    } else {
      ElMessage.warning(data.message || '等待超时')
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '等待失败')
  } finally {
    taobaoActionLoading.value = false
  }
}

onMounted(async () => {
  try {
    const { data } = await getHealth()
    health.value = data
  } catch {
    health.value = null
  } finally {
    loading.value = false
  }
  // Fetch selection status
  try {
    const { data } = await getSelectionStatus()
    selectionEnabled.value = data.enabled
  } catch {
    // ignore — toggle disabled if API unreachable
  }
  // Fetch taobao status
  fetchTaobaoStatus()
})

async function handleSelectionToggle(val: boolean) {
  selectionToggling.value = true
  try {
    await toggleSelection(val)
  } catch {
    // Revert on failure
    selectionEnabled.value = !val
  } finally {
    selectionToggling.value = false
  }
}
</script>

<style scoped>
.dashboard {
  max-width: 1200px;
  margin: 0 auto;
}

.status-card {
  margin-top: 20px;
}

.chart-row {
  margin-top: 20px;
  margin-bottom: 0;
}

.entry-row {
  margin-top: 20px;
  margin-bottom: 0;
}

.entry-card {
  cursor: pointer;
  transition: border-color 0.2s;
  height: 100%;
}

.entry-card:hover {
  border-color: #409eff;
}

.entry-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.entry-icon {
  font-size: 36px;
}

.entry-title {
  margin: 0 0 4px;
  font-size: 18px;
  color: #303133;
}

.entry-desc {
  margin: 0;
  font-size: 14px;
  color: #909399;
}

.toggle-card :deep(.entry-content) {
  justify-content: space-between;
}

/* Phase 42.6: 淘宝操控台 */
.taobao-card {
  margin-top: 20px;
}

.taobao-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.taobao-loading {
  text-align: center;
  padding: 24px;
}

.taobao-info-row {
  margin-bottom: 12px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-label {
  color: #909399;
  font-size: 13px;
}

.info-value {
  color: #303133;
  font-size: 13px;
}

.taobao-alert {
  margin-bottom: 12px;
}

.taobao-actions {
  margin-top: 8px;
}

.taobao-result {
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  color: #606266;
}
</style>
