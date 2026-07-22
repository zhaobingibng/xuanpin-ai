<template>
  <div class="task-center">
    <el-button text @click="router.push('/')" style="margin-bottom: 12px">&larr; 返回首页</el-button>

    <!-- 页面1：任务总览 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">任务总览</span>
          <el-button size="small" :loading="loading" @click="fetchAll">刷新</el-button>
        </div>
      </template>

      <el-table :data="overviewRows" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="name" label="任务名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="调度状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? '已启用' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Cron" width="140">
          <template #default="{ row }">{{ formatCron(row) }}</template>
        </el-table-column>
        <el-table-column label="最近执行" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.lastStatus" :type="statusTagType(row.lastStatus)" size="small">
              {{ row.lastStatus }}
            </el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="最近执行时间" width="180">
          <template #default="{ row }">{{ formatTime(row.lastRun) }}</template>
        </el-table-column>
        <el-table-column label="下次运行" width="180">
          <template #default="{ row }">{{ formatTime(row.nextRun) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="viewHistory(row.name)">详情</el-button>
            <el-button
              size="small"
              type="success"
              link
              :loading="row._running"
              @click="handleRun(row)"
            >运行</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 页面3：调度任务列表 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">调度任务列表 (Scheduler Jobs)</span>
          <span class="muted">共 {{ jobs.length }} 个</span>
        </div>
      </template>

      <el-table :data="jobs" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="Job ID" min-width="180" show-overflow-tooltip />
        <el-table-column label="下次运行时间" width="200">
          <template #default="{ row }">{{ formatTime(row.next_run) }}</template>
        </el-table-column>
        <el-table-column label="是否启用" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.next_run ? 'success' : 'info'" size="small">
              {{ row.next_run ? '启用' : '暂停' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trigger" label="触发器" min-width="220" show-overflow-tooltip />
      </el-table>
      <el-empty v-if="!loading && jobs.length === 0" description="调度器暂无任务（可能未启动）" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getTaskDefinitions,
  getSchedulerJobs,
  getTaskHistory,
  runTask,
  type SchedulerJob,
} from '@/api/index'

interface OverviewRow {
  name: string
  trigger: string
  trigger_kwargs: Record<string, number>
  enabled: boolean
  nextRun: string | null
  lastStatus: string | null
  lastRun: string | null
  _running?: boolean
}

const router = useRouter()
const loading = ref(false)
const overviewRows = ref<OverviewRow[]>([])
const jobs = ref<SchedulerJob[]>([])

onMounted(() => {
  fetchAll()
})

async function fetchAll() {
  loading.value = true
  try {
    const [defResp, jobResp] = await Promise.all([getTaskDefinitions(), getSchedulerJobs()])
    jobs.value = jobResp.data

    const jobMap = new Map(jobResp.data.map((j) => [j.id, j]))
    const rows: OverviewRow[] = defResp.data.map((d) => ({
      name: d.name,
      trigger: d.trigger,
      trigger_kwargs: d.trigger_kwargs,
      enabled: d.enabled,
      nextRun: jobMap.get(d.name)?.next_run ?? null,
      lastStatus: null,
      lastRun: null,
    }))

    // 拉取每个任务的最近一次执行状态
    await Promise.all(
      rows.map(async (row) => {
        try {
          const h = await getTaskHistory(row.name, 1)
          const last = h.data[0]
          if (last) {
            row.lastStatus = last.status
            row.lastRun = last.start_time
          }
        } catch {
          // 单个任务历史失败不影响整体
        }
      }),
    )

    overviewRows.value = rows
  } catch {
    ElMessage.error('获取任务列表失败')
  } finally {
    loading.value = false
  }
}

async function handleRun(row: OverviewRow) {
  try {
    await ElMessageBox.confirm(
      `确定立即执行任务「${row.name}」吗？该操作将真实触发一次任务。`,
      '手动运行',
      { type: 'warning' },
    )
  } catch {
    return
  }

  row._running = true
  try {
    const resp = await runTask(row.name)
    const status = resp.data?.result?.status
    if (status === 'FAILED') {
      ElMessage.warning(`任务已执行但返回失败：${row.name}`)
    } else {
      ElMessage.success(`任务已执行：${row.name}`)
    }
    await fetchAll()
  } catch (err: any) {
    const detail = err?.response?.data?.detail || err?.message || '执行失败'
    ElMessage.error(detail)
  } finally {
    row._running = false
  }
}

function viewHistory(name: string) {
  router.push(`/tasks/${name}`)
}

function formatCron(row: OverviewRow) {
  const kw = row.trigger_kwargs || {}
  if (kw.hour !== undefined || kw.minute !== undefined) {
    const h = String(kw.hour ?? 0).padStart(2, '0')
    const m = String(kw.minute ?? 0).padStart(2, '0')
    return `每天 ${h}:${m}`
  }
  return row.trigger || '-'
}

function formatTime(t: string | null) {
  return t ? new Date(t).toLocaleString() : '-'
}

function statusTagType(status: string) {
  const s = (status || '').toUpperCase()
  if (s === 'SUCCESS') return 'success'
  if (s === 'FAILED') return 'danger'
  if (s === 'RUNNING') return 'warning'
  return 'info'
}
</script>

<style scoped>
.task-center {
  max-width: 1400px;
  margin: 0 auto;
}
.section-card {
  margin-bottom: 16px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title {
  font-size: 18px;
  font-weight: 600;
}
.muted {
  color: #909399;
  font-size: 13px;
}
</style>
