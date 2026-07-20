<template>
  <el-card class="strategy-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">运营方案生成器</span>
        <el-tag type="warning" size="small">AI文案</el-tag>
      </div>
    </template>

    <!-- 输入区 -->
    <div class="input-area">
      <el-input-number
        v-model="productId"
        :min="1"
        placeholder="商品ID"
        controls-position="right"
        style="width: 180px"
      />
      <el-button type="primary" :loading="loading" :disabled="!productId" @click="fetchStrategy">
        查询方案
      </el-button>
      <el-button type="success" :loading="generating" :disabled="!productId" @click="handleGenerate">
        生成新方案
      </el-button>
    </div>

    <!-- 错误 -->
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" style="margin-top: 12px" />

    <!-- 方案展示 -->
    <div v-if="strategy" class="strategy-content">
      <!-- 标题 -->
      <div class="section">
        <div class="section-title">营销标题</div>
        <div class="strategy-title">{{ strategy.title }}</div>
      </div>

      <!-- 卖点 -->
      <div class="section">
        <div class="section-title">核心卖点</div>
        <div class="selling-points">
          <el-tag
            v-for="(point, idx) in strategy.selling_points"
            :key="idx"
            type="success"
            class="sp-tag"
          >
            {{ point }}
          </el-tag>
        </div>
      </div>

      <!-- 小红书文案 -->
      <div class="section">
        <div class="section-title">小红书文案</div>
        <div class="copy-block">{{ strategy.xiaohongshu_copy }}</div>
      </div>

      <!-- 闲语文案 -->
      <div class="section">
        <div class="section-title">闲语文案</div>
        <div class="copy-block">{{ strategy.xianyu_copy }}</div>
      </div>

      <!-- 价格策略 -->
      <div class="section">
        <div class="section-title">价格策略</div>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="成本价">
            <span class="price">￥{{ strategy.price_strategy.cost.toFixed(2) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="销售价">
            <span class="price">￥{{ strategy.price_strategy.sell.toFixed(2) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="单件利润">
            <span class="price profit">￥{{ strategy.price_strategy.profit.toFixed(2) }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 利润分析 -->
      <div class="section">
        <div class="section-title">利润分析</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="利润率">
            <el-tag type="success">{{ strategy.profit_analysis.profit_margin }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="单件利润">
            ￥{{ strategy.profit_analysis.profit_per_unit.toFixed(2) }}
          </el-descriptions-item>
          <el-descriptions-item label="日预估(10单)">
            ￥{{ strategy.profit_analysis.daily_estimate.toFixed(2) }}
          </el-descriptions-item>
          <el-descriptions-item label="月预估(300单)">
            <strong class="monthly">￥{{ strategy.profit_analysis.monthly_estimate.toFixed(2) }}</strong>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 生成时间 -->
      <div v-if="strategy.created_at" class="created-at">
        生成于 {{ strategy.created_at }}
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!strategy && !loading && !error && queried" description="暂无运营方案，请点击生成" />
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getStrategy, generateStrategy } from '@/api'
import type { StrategyRecord } from '@/types/workbench'

const productId = ref<number | undefined>(undefined)
const loading = ref(false)
const generating = ref(false)
const error = ref<string | null>(null)
const queried = ref(false)
const strategy = ref<StrategyRecord | null>(null)

async function fetchStrategy() {
  if (!productId.value) return

  loading.value = true
  error.value = null
  strategy.value = null
  queried.value = false

  try {
    const { data } = await getStrategy(productId.value)
    if (data.length > 0) {
      strategy.value = data[0]
    }
    queried.value = true
  } catch {
    error.value = '获取运营方案失败'
    queried.value = true
  } finally {
    loading.value = false
  }
}

async function handleGenerate() {
  if (!productId.value) return

  generating.value = true
  error.value = null
  strategy.value = null

  try {
    const { data } = await generateStrategy(productId.value)
    strategy.value = {
      id: 0,
      product_id: productId.value,
      title: data.title,
      selling_points: data.selling_points,
      xiaohongshu_copy: data.xiaohongshu_copy,
      xianyu_copy: data.xianyu_copy,
      price_strategy: data.price_strategy,
      profit_analysis: data.profit_analysis,
      created_at: null,
    }
    ElMessage.success('运营方案生成成功')
  } catch {
    error.value = '生成运营方案失败'
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.strategy-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.input-area {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.strategy-content {
  margin-top: 16px;
}

.section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.strategy-title {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
}

.selling-points {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.sp-tag {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.copy-block {
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  line-height: 1.8;
  white-space: pre-wrap;
  color: #303133;
  font-size: 14px;
}

.price {
  font-weight: 600;
}

.profit {
  color: #67c23a;
}

.monthly {
  color: #e6a23c;
  font-size: 16px;
}

.created-at {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
  text-align: right;
}
</style>
