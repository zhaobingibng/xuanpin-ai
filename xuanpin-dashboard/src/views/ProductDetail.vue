<template>
  <div v-loading="loading" class="product-detail">
    <el-button class="back-btn" @click="router.push('/')">
      &larr; 返回排行榜
    </el-button>

    <el-result
      v-if="notFound"
      icon="warning"
      title="商品不存在"
      sub-title="请检查商品ID是否正确"
    >
      <template #extra>
        <el-button type="primary" @click="router.push('/')">返回首页</el-button>
      </template>
    </el-result>

    <template v-else-if="product">
      <!-- 基本信息 -->
      <el-card class="info-card">
        <template #header>
          <span>商品基本信息</span>
        </template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="商品名称">{{ product.name }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ product.platform }}</el-descriptions-item>
          <el-descriptions-item label="分类">{{ product.category }}</el-descriptions-item>
          <el-descriptions-item label="当前价格">{{ product.price.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="AI评分">{{ product.history.length > 0 ? product.history[product.history.length - 1].ai_score ?? '-' : '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 趋势分析 -->
      <el-card v-if="trend" class="info-card">
        <template #header>
          <div class="trend-header">
            <span>趋势分析</span>
            <el-tag :type="trendLevelType">{{ trend.level }}</el-tag>
          </div>
        </template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="趋势评分">{{ trend.trend_score }}</el-descriptions-item>
          <el-descriptions-item label="销量增长">
            <span :style="{ color: trend.sales_growth >= 0 ? '#67c23a' : '#f56c6c' }">
              {{ trend.sales_growth >= 0 ? '+' : '' }}{{ trend.sales_growth }}%
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="浏览增长">
            <span :style="{ color: trend.view_growth >= 0 ? '#67c23a' : '#f56c6c' }">
              {{ trend.view_growth >= 0 ? '+' : '' }}{{ trend.view_growth }}%
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="价格变化">
            {{ trend.price_change }}%
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 趋势图表 -->
      <TrendChart :history="product.history" />

      <!-- 历史数据 -->
      <el-card class="info-card">
        <template #header>
          <span>历史数据</span>
        </template>
        <el-table :data="product.history" stripe>
          <el-table-column prop="record_time" label="日期" width="180" />
          <el-table-column prop="price" label="价格" width="120" align="right">
            <template #default="{ row }">
              {{ (row as ProductHistory).price.toFixed(2) }}
            </template>
          </el-table-column>
          <el-table-column prop="sales_24h" label="24小时销量" width="140" align="right" />
          <el-table-column prop="viewers" label="浏览人数" width="140" align="right" />
          <el-table-column prop="ai_score" label="AI评分" width="120" align="right">
            <template #default="{ row }">
              {{ (row as ProductHistory).ai_score ?? '-' }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getProduct, getProductTrend } from '@/api'
import type { Product, ProductHistory, TrendResult } from '@/types/product'
import TrendChart from '@/components/TrendChart.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const notFound = ref(false)
const product = ref<Product | null>(null)
const trend = ref<TrendResult | null>(null)

const trendLevelType = computed(() => {
  const level = trend.value?.level
  if (level === '爆发') return 'danger' as const
  if (level === '上涨') return 'success' as const
  if (level === '稳定') return '' as const
  return 'info' as const
})

onMounted(async () => {
  const id = Number(route.params.id)
  if (!id || Number.isNaN(id)) {
    notFound.value = true
    return
  }

  loading.value = true
  try {
    const [productRes, trendRes] = await Promise.all([
      getProduct(id),
      getProductTrend(id),
    ])
    product.value = productRes.data
    trend.value = trendRes.data
  } catch (err: unknown) {
    const error = err as { response?: { status: number } }
    if (error.response?.status === 404) {
      notFound.value = true
    } else {
      ElMessage.error('获取商品详情失败')
    }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.product-detail {
  max-width: 1200px;
  margin: 0 auto;
}

.back-btn {
  margin-bottom: 20px;
}

.info-card {
  margin-bottom: 20px;
}

.trend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
