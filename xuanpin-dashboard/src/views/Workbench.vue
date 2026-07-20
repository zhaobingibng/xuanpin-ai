<template>
  <div class="workbench" v-loading="loading">
    <div class="page-header">
      <el-button text @click="router.push('/')">
        <el-icon><ArrowLeft /></el-icon>
        返回首页
      </el-button>
      <h2>AI 运营工作台</h2>
      <p v-if="overview" class="workbench-date">{{ overview.date }}</p>
    </div>

    <!-- KPI 卡片 -->
    <el-row :gutter="16" class="kpi-row" v-if="overview">
      <el-col :span="5">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ overview.total }}</div>
          <div class="kpi-label">今日商品</div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover" class="kpi-card kpi-hot">
          <div class="kpi-value">{{ overview.hot_products }}</div>
          <div class="kpi-label">爆款数量</div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover" class="kpi-card kpi-potential">
          <div class="kpi-value">{{ overview.potential_products }}</div>
          <div class="kpi-label">潜力商品</div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ overview.average_score.toFixed(1) }}</div>
          <div class="kpi-label">平均评分</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="kpi-card kpi-accuracy">
          <div class="kpi-value">{{ reviewAccuracy ? reviewAccuracy.accuracy.toFixed(0) : '-' }}%</div>
          <div class="kpi-label">推荐准确率</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 错误 -->
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" style="margin-bottom: 16px" />

    <!-- 推荐列表 -->
    <RecommendationList />

    <!-- 双栏：机会商品 + AI助手 -->
    <el-row :gutter="16">
      <el-col :span="12">
        <OpportunityTable />
      </el-col>
      <el-col :span="12">
        <AIAssistant />
      </el-col>
    </el-row>

    <!-- 运营方案 -->
    <StrategyPanel />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getWorkbenchOverview, getReviewAccuracy } from '@/api'
import type { DashboardOverview, ReviewAccuracy as ReviewAccuracyType } from '@/types/workbench'
import RecommendationList from '@/components/RecommendationList.vue'
import OpportunityTable from '@/components/OpportunityTable.vue'
import AIAssistant from '@/components/AIAssistant.vue'
import StrategyPanel from '@/components/StrategyPanel.vue'

const router = useRouter()

const loading = ref(false)
const error = ref<string | null>(null)
const overview = ref<DashboardOverview | null>(null)
const reviewAccuracy = ref<ReviewAccuracyType | null>(null)

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    const [overviewRes, accuracyRes] = await Promise.all([
      getWorkbenchOverview(),
      getReviewAccuracy(),
    ])
    overview.value = overviewRes.data
    reviewAccuracy.value = accuracyRes.data
  } catch {
    error.value = '获取工作台数据失败'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.workbench {
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 8px 0 4px;
}

.workbench-date {
  color: #909399;
  margin: 0;
}

.kpi-row {
  margin-bottom: 20px;
}

.kpi-card {
  text-align: center;
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.kpi-hot .kpi-value {
  color: #f56c6c;
}

.kpi-potential .kpi-value {
  color: #e6a23c;
}

.kpi-accuracy .kpi-value {
  color: #67c23a;
}

.kpi-label {
  font-size: 13px;
  color: #909399;
  margin-top: 6px;
}
</style>
