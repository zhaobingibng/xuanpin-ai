<template>
  <div class="ai-analysis" v-loading="loading">
    <div class="page-header">
      <el-button text @click="router.push('/')">
        <el-icon><ArrowLeft /></el-icon>
        返回首页
      </el-button>
      <h2>AI 智能分析</h2>
      <p class="header-desc">基于 LLM 的商品深度分析与报告解读</p>
    </div>

    <!-- LLM 状态 -->
    <el-alert
      v-if="llmStatus && !llmStatus.available"
      title="LLM 服务暂不可用"
      type="warning"
      show-icon
      :closable="false"
      class="status-alert"
    >
      <template #default>
        {{ llmStatus.reason === 'no_api_key' ? 'API Key 未配置' : '服务暂时无法访问' }}
      </template>
    </el-alert>

    <!-- 商品分析区 -->
    <el-card class="analysis-section">
      <template #header>
        <div class="section-header">
          <span>商品深度分析</span>
          <div class="input-group">
            <el-input
              v-model="productIdInput"
              placeholder="输入商品 ID"
              type="number"
              style="width: 140px"
              @keyup.enter="analyzeProduct"
            />
            <el-button type="primary" :loading="analyzing" @click="analyzeProduct">
              分析
            </el-button>
          </div>
        </div>
      </template>

      <!-- 商品分析结果 -->
      <LLMInsightCard
        v-if="productAnalysis"
        :title="productAnalysis.product_name"
        :summary="productAnalysis.llm_analysis?.summary"
        :tags="productAnalysis.llm_analysis?.tags"
        :selling-points="productAnalysis.llm_analysis?.selling_points"
        :risks="productAnalysis.llm_analysis?.risks"
        :market-insight="productAnalysis.llm_analysis?.market_insight"
        :recommendation="productAnalysis.llm_analysis?.recommendation"
        :confidence="productAnalysis.llm_analysis?.confidence"
      />

      <!-- 降级提示 -->
      <el-alert
        v-if="productAnalysis?.fallback"
        title="LLM 分析暂不可用，显示基础信息"
        type="info"
        show-icon
        :closable="false"
        style="margin-top: 12px"
      />

      <!-- 空状态 -->
      <el-empty v-if="!productAnalysis && !analyzing" description="输入商品 ID 开始分析" />
    </el-card>

    <!-- 报告摘要区 -->
    <el-card class="analysis-section">
      <template #header>
        <div class="section-header">
          <span>每日报告 LLM 解读</span>
          <div class="input-group">
            <el-input
              v-model="reportIdInput"
              placeholder="输入报告 ID"
              type="number"
              style="width: 140px"
              @keyup.enter="summarizeReport"
            />
            <el-button type="primary" :loading="summarizing" @click="summarizeReport">
              解读
            </el-button>
          </div>
        </div>
      </template>

      <!-- 报告摘要结果 -->
      <LLMInsightCard
        v-if="reportSummary"
        :title="`报告日期: ${reportSummary.report_date}`"
        :summary="reportSummary.llm_summary?.summary"
        :highlights="reportSummary.llm_summary?.highlights"
        :warnings="reportSummary.llm_summary?.warnings"
        :action-items="reportSummary.llm_summary?.action_items"
        :market-trend="reportSummary.llm_summary?.market_trend"
      />

      <!-- 降级提示 -->
      <el-alert
        v-if="reportSummary?.fallback"
        title="LLM 摘要暂不可用，显示基础数据"
        type="info"
        show-icon
        :closable="false"
        style="margin-top: 12px"
      />

      <!-- 空状态 -->
      <el-empty v-if="!reportSummary && !summarizing" description="输入报告 ID 获取 LLM 解读" />
    </el-card>

    <!-- 错误提示 -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 16px"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getLLMStatus, analyzeProductWithLLM, summarizeReportWithLLM } from '@/api'
import LLMInsightCard from '@/components/LLMInsightCard.vue'

const router = useRouter()

const loading = ref(false)
const error = ref<string | null>(null)
const llmStatus = ref<{ available: boolean; model?: string; reason?: string } | null>(null)

// 商品分析
const productIdInput = ref('')
const analyzing = ref(false)
const productAnalysis = ref<any>(null)

// 报告摘要
const reportIdInput = ref('')
const summarizing = ref(false)
const reportSummary = ref<any>(null)

onMounted(async () => {
  await checkLLMStatus()
})

async function checkLLMStatus() {
  try {
    const { data } = await getLLMStatus()
    llmStatus.value = data
  } catch {
    llmStatus.value = { available: false, reason: 'unknown' }
  }
}

async function analyzeProduct() {
  const id = parseInt(productIdInput.value)
  if (!id || isNaN(id)) {
    ElMessage.warning('请输入有效的商品 ID')
    return
  }

  analyzing.value = true
  error.value = null
  productAnalysis.value = null

  try {
    const { data } = await analyzeProductWithLLM(id)
    productAnalysis.value = data
  } catch (e: any) {
    if (e.response?.status === 404) {
      error.value = '商品不存在'
    } else {
      error.value = '分析失败，请稍后重试'
    }
    ElMessage.error(error.value)
  } finally {
    analyzing.value = false
  }
}

async function summarizeReport() {
  const id = parseInt(reportIdInput.value)
  if (!id || isNaN(id)) {
    ElMessage.warning('请输入有效的报告 ID')
    return
  }

  summarizing.value = true
  error.value = null
  reportSummary.value = null

  try {
    const { data } = await summarizeReportWithLLM(id)
    reportSummary.value = data
  } catch (e: any) {
    if (e.response?.status === 404) {
      error.value = '报告不存在'
    } else {
      error.value = '解读失败，请稍后重试'
    }
    ElMessage.error(error.value)
  } finally {
    summarizing.value = false
  }
}
</script>

<style scoped>
.ai-analysis {
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 8px 0 4px;
}

.header-desc {
  color: #909399;
  margin: 0;
  font-size: 14px;
}

.status-alert {
  margin-bottom: 16px;
}

.analysis-section {
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.section-header span {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.input-group {
  display: flex;
  gap: 8px;
}
</style>
