<template>
  <el-card class="insight-card" shadow="hover">
    <template #header>
      <div class="card-header">
        <span class="card-title">{{ title }}</span>
        <el-tag v-if="recommendation" :type="recommendationTagType" size="small">
          {{ recommendationLabel }}
        </el-tag>
      </div>
    </template>

    <!-- 摘要 -->
    <p v-if="summary" class="insight-summary">{{ summary }}</p>

    <!-- 标签 -->
    <div v-if="tags && tags.length > 0" class="insight-tags">
      <el-tag
        v-for="(tag, idx) in tags.slice(0, 5)"
        :key="idx"
        size="small"
        type="info"
        class="tag-item"
      >
        {{ tag }}
      </el-tag>
    </div>

    <!-- 卖点 -->
    <div v-if="sellingPoints && sellingPoints.length > 0" class="insight-section">
      <div class="section-title">
        <el-icon><SuccessFilled /></el-icon>
        卖点
      </div>
      <ul class="insight-list">
        <li v-for="(point, idx) in sellingPoints" :key="idx">{{ point }}</li>
      </ul>
    </div>

    <!-- 风险 -->
    <div v-if="risks && risks.length > 0" class="insight-section">
      <div class="section-title risk-title">
        <el-icon><WarningFilled /></el-icon>
        风险
      </div>
      <ul class="insight-list">
        <li v-for="(risk, idx) in risks" :key="idx">{{ risk }}</li>
      </ul>
    </div>

    <!-- 市场洞察 -->
    <div v-if="marketInsight" class="insight-section">
      <div class="section-title">
        <el-icon><TrendCharts /></el-icon>
        市场洞察
      </div>
      <p class="insight-text">{{ marketInsight }}</p>
    </div>

    <!-- 置信度 -->
    <div v-if="confidence !== undefined" class="insight-confidence">
      <span>置信度:</span>
      <el-progress :percentage="confidence" :stroke-width="8" :show-text="false" />
      <span class="confidence-value">{{ confidence }}%</span>
    </div>

    <!-- 高亮/警告/行动项 (报告摘要用) -->
    <div v-if="highlights && highlights.length > 0" class="insight-section">
      <div class="section-title highlight-title">
        <el-icon><Star /></el-icon>
        亮点
      </div>
      <ul class="insight-list">
        <li v-for="(item, idx) in highlights" :key="idx">{{ item }}</li>
      </ul>
    </div>

    <div v-if="warnings && warnings.length > 0" class="insight-section">
      <div class="section-title risk-title">
        <el-icon><WarningFilled /></el-icon>
        风险提醒
      </div>
      <ul class="insight-list">
        <li v-for="(item, idx) in warnings" :key="idx">{{ item }}</li>
      </ul>
    </div>

    <div v-if="actionItems && actionItems.length > 0" class="insight-section">
      <div class="section-title">
        <el-icon><CircleCheck /></el-icon>
        建议操作
      </div>
      <ul class="insight-list">
        <li v-for="(item, idx) in actionItems" :key="idx">{{ item }}</li>
      </ul>
    </div>

    <!-- 市场趋势 (报告摘要用) -->
    <div v-if="marketTrend" class="insight-section">
      <div class="section-title">
        <el-icon><TrendCharts /></el-icon>
        市场趋势
      </div>
      <p class="insight-text">{{ marketTrend }}</p>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { SuccessFilled, WarningFilled, TrendCharts, Star, CircleCheck } from '@element-plus/icons-vue'

const props = defineProps<{
  title: string
  summary?: string
  tags?: string[]
  sellingPoints?: string[]
  risks?: string[]
  marketInsight?: string
  recommendation?: 'SELL' | 'TEST' | 'WATCH' | 'DROP'
  confidence?: number
  highlights?: string[]
  warnings?: string[]
  actionItems?: string[]
  marketTrend?: string
}>()

const recommendationTagType = computed(() => {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    SELL: 'danger',
    TEST: 'warning',
    WATCH: '',
    DROP: 'info',
  }
  return map[props.recommendation || 'WATCH'] || ''
})

const recommendationLabel = computed(() => {
  const map: Record<string, string> = {
    SELL: '建议销售',
    TEST: '建议测试',
    WATCH: '观望',
    DROP: '放弃',
  }
  return map[props.recommendation || 'WATCH'] || '观望'
})
</script>

<style scoped>
.insight-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.insight-summary {
  font-size: 14px;
  line-height: 1.6;
  color: #606266;
  margin: 0 0 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.insight-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.tag-item {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.insight-section {
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: #67c23a;
  margin-bottom: 6px;
}

.highlight-title {
  color: #e6a23c;
}

.risk-title {
  color: #f56c6c;
}

.insight-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}

.insight-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  margin: 0;
}

.insight-confidence {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
  font-size: 13px;
  color: #909399;
}

.insight-confidence .el-progress {
  flex: 1;
}

.confidence-value {
  font-weight: 600;
  color: #303133;
  min-width: 40px;
  text-align: right;
}
</style>
