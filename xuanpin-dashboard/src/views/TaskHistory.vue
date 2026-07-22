<template>
  <div class="task-history">
    <el-button text @click="router.push('/tasks')" style="margin-bottom: 12px">&larr; 返回任务总览</el-button>

    <el-card shadow="never">
      <template #header>
        <div class="section-header">
          <span class="section-title">任务详情：{{ name }}</span>
          <el-button size="small" :loading="loading" @click="fetchHistory">刷新</el-button>
        </div>
      </template>

      <el-table :data="history" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="#" width="70" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="190">
          <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="190">
          <template #default="{ row }">{{ formatTime(row.end_time) }}</template>
        </el-table-column>
        <el-table-column label="耗时(s)" width="100" align="right">
          <template #default="{ row }">{{ row.duration != null ? row.duration.toFixed(2) : '-' }}</template>
        </el-table-column>
        <el-table-column label="错误信息" min-width="240">
          <template #default="{ row }">
            <span v-if="row.error" class="error-text">{{ row.error }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && history.length === 0" description="暂无执行记录" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTaskHistory, type TaskExecution } from '@/api/index'

const route = useRoute()
const router = useRouter()
const name = route.params.name as string
const loading = ref(false)
const history = ref<TaskExecution[]>([])

onMounted(() => {
  fetchHistory()
})

async function fetchHistory() {
  loading.value = true
  try {
    const resp = await getTaskHistory(name, 50)
    history.value = resp.data
  } catch {
    ElMessage.error('获取执行历史失败')
  } finally {
    loading.value = false
  }
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
.task-history {
  max-width: 1400px;
  margin: 0 auto;
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
}
.error-text {
  color: #f56c6c;
  word-break: break-all;
}
</style>
