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
        <el-card class="entry-card" shadow="hover" @click="router.push('/workbench')">
          <div class="entry-content">
            <span class="entry-icon">&#129302;</span>
            <div>
              <h3 class="entry-title">AI运营工作台</h3>
              <p class="entry-desc">进入智能推荐、机会分析、文案生成一站式工作台</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <TopRankingTable />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'
import { getHealth } from '@/api'
import TopRankingTable from '@/components/TopRankingTable.vue'
import CategoryChart from '@/components/CategoryChart.vue'
import PlatformChart from '@/components/PlatformChart.vue'

interface HealthInfo {
  status: string
  app: string
}

const router = useRouter()
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
</style>
