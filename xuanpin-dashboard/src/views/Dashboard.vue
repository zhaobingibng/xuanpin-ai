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

    <TopRankingTable />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { getHealth } from '@/api'
import TopRankingTable from '@/components/TopRankingTable.vue'

interface HealthInfo {
  status: string
  app: string
}

const loading = ref(true)
const health = ref<HealthInfo | null>(null)

onMounted(async () => {
  try {
    const { data } = await getHealth()
    health.value = data
  } catch {
    health.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dashboard {
  max-width: 1200px;
  margin: 0 auto;
}

.status-card {
  margin-top: 20px;
}
</style>
