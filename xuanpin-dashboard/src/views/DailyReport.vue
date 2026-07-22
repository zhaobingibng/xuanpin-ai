<template>
  <div class="daily-report" v-loading="loading">
    <div class="page-header">
      <el-button text @click="router.push('/')">
        <el-icon><ArrowLeft /></el-icon>
        返回首页
      </el-button>
      <h2>AI 每日选品报告</h2>
      <p v-if="selectionReport" class="report-date">
        {{ selectionReport.date }}
        <span class="generated-at">生成时间: {{ selectionReport.generated_at }}</span>
      </p>
    </div>

    <!-- 尚未生成报告 -->
    <el-alert
      v-if="notFound"
      title="选品报告尚未生成"
      type="info"
      show-icon
      :closable="false"
      description="请等待定时任务执行或手动触发 daily_selection_job。"
      style="margin-bottom: 16px"
    />

    <!-- KPI 卡片 -->
    <el-row :gutter="20" class="kpi-row" v-if="selectionReport && topProducts.length > 0">
      <el-col :span="6">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ selectionReport.stats.total_products }}</div>
          <div class="kpi-label">候选商品</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="kpi-card kpi-matched">
          <div class="kpi-value">{{ selectionReport.stats.matched_products }}</div>
          <div class="kpi-label">有供应商匹配</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="kpi-card kpi-matches">
          <div class="kpi-value">{{ selectionReport.stats.total_matches }}</div>
          <div class="kpi-label">匹配总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ avgScore }}</div>
          <div class="kpi-label">平均机会评分</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- AI 综合分析卡片 -->
    <LLMInsightCard
      v-if="aiInsights?.ai_available"
      title="AI 综合分析"
      :summary="aiInsights.overall_summary"
      :highlights="aiInsights.highlights"
      :warnings="aiInsights.warnings"
      :action-items="aiInsights.action_suggestions"
      :market-trend="profitAndTrend"
      class="ai-insight-card"
    />

    <!-- AI 降级提示 -->
    <el-alert
      v-if="aiInsights && !aiInsights.ai_available"
      title="AI 分析暂不可用"
      :description="aiInsights.error || 'LLM 服务暂时无法访问，显示基础数据。'"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    />

    <!-- 错误提示 -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 16px"
    />

    <!-- TOP 商品列表 -->
    <el-table
      v-if="topProducts.length > 0"
      :data="topProducts"
      stripe
      row-class-name="clickable-row"
      @row-click="handleRowClick"
      class="report-table"
    >
      <el-table-column prop="rank" label="排名" width="80" align="center" />
      <el-table-column label="商品图片" width="80" align="center">
        <template #default="{ row }">
          <el-image
            v-if="(row as any).image"
            :src="(row as any).image"
            fit="cover"
            class="product-img"
          >
            <template #error>
              <div class="img-fallback">
                <el-icon><Picture /></el-icon>
              </div>
            </template>
          </el-image>
          <span v-else class="no-img">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="商品名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="platform" label="平台" width="100" align="center" />
      <el-table-column prop="price" label="价格" width="100" align="right">
        <template #default="{ row }">
          ¥{{ (row as any).price.toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column label="预估利润" width="110" align="right">
        <template #default="{ row }">
          <span v-if="(row as any).estimated_profit != null" class="profit-value">
            ¥{{ (row as any).estimated_profit.toFixed(2) }}
          </span>
          <span v-else class="no-profit">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="score" label="评分" width="80" align="center" />
      <el-table-column prop="level" label="等级" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="levelTagType((row as any).level)" size="small">
            {{ (row as any).level }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="推荐理由" min-width="260">
        <template #default="{ row }">
          <div class="reasons">
            <el-tag
              v-for="(reason, idx) in ((row as any).reasons || []).slice(0, 3)"
              :key="idx"
              size="small"
              class="reason-tag"
            >
              {{ reason }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空数据 -->
    <el-empty
      v-if="selectionReport && topProducts.length === 0"
      description="暂无选品数据"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Picture } from '@element-plus/icons-vue'
import { getDailySelectionReport } from '@/api'
import LLMInsightCard from '@/components/LLMInsightCard.vue'
import type { DailySelectionReport, AiInsights, DailySelectionProduct } from '@/types/workbench'

const router = useRouter()

const loading = ref(false)
const error = ref<string | null>(null)
const notFound = ref(false)
const selectionReport = ref<DailySelectionReport | null>(null)

const topProducts = computed<DailySelectionProduct[]>(() => {
  return selectionReport.value?.report?.top_products || []
})

const aiInsights = computed<AiInsights | null>(() => {
  return selectionReport.value?.report?.ai_insights || null
})

const avgScore = computed(() => {
  const products = topProducts.value
  if (products.length === 0) return '0.0'
  const sum = products.reduce((acc, p) => acc + (p.score || 0), 0)
  return (sum / products.length).toFixed(1)
})

const profitAndTrend = computed(() => {
  const insights = aiInsights.value
  if (!insights) return undefined
  const parts: string[] = []
  if (insights.profit_insight) parts.push(`💰 利润洞察：${insights.profit_insight}`)
  if (insights.market_trend) parts.push(`📈 市场趋势：${insights.market_trend}`)
  return parts.join('\n\n') || undefined
})

function levelTagType(level: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    '强烈推荐': 'danger',
    '值得研究': 'warning',
    '观察中': '',
    '爆款': 'danger',
    '潜力': 'warning',
    '一般': '',
    '低潜': 'info',
  }
  return map[level] || ''
}

onMounted(async () => {
  loading.value = true
  error.value = null
  notFound.value = false
  try {
    const { data } = await getDailySelectionReport()
    selectionReport.value = data
    if (data.report?.top_products?.length > 0) {
      ElMessage.success(`已加载 ${data.report.top_products.length} 个选品结果`)
    }
  } catch (e: any) {
    if (e.response?.status === 404) {
      notFound.value = true
    } else {
      error.value = '获取每日选品报告失败'
      ElMessage.error('获取每日选品报告失败')
    }
  } finally {
    loading.value = false
  }
})

function handleRowClick(row: DailySelectionProduct) {
  router.push(`/products/${row.product_id}`)
}
</script>

<style scoped>
.daily-report {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 8px 0 4px;
}

.report-date {
  color: #909399;
  margin: 0;
}

.generated-at {
  margin-left: 12px;
  font-size: 12px;
  color: #c0c4cc;
}

.kpi-row {
  margin-bottom: 20px;
}

.kpi-card {
  text-align: center;
}

.kpi-value {
  font-size: 32px;
  font-weight: 700;
  color: #303133;
}

.kpi-matched .kpi-value {
  color: #67c23a;
}

.kpi-matches .kpi-value {
  color: #409eff;
}

.kpi-label {
  font-size: 14px;
  color: #909399;
  margin-top: 8px;
}

.ai-insight-card {
  margin-bottom: 20px;
}

.report-table {
  margin-top: 0;
}

.product-img {
  width: 50px;
  height: 50px;
  border-radius: 4px;
}

.img-fallback {
  width: 50px;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 4px;
  color: #c0c4cc;
}

.no-img {
  color: #c0c4cc;
}

.profit-value {
  color: #67c23a;
  font-weight: 500;
}

.no-profit {
  color: #c0c4cc;
}

.reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.reason-tag {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

<style>
.clickable-row {
  cursor: pointer;
}
</style>
