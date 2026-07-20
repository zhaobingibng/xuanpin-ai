<template>
  <el-card class="rec-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <span class="card-title">今日AI推荐</span>
        <el-tag v-if="recommendation" type="info" size="small">{{ recommendation.date }}</el-tag>
      </div>
    </template>

    <el-empty v-if="!loading && (!recommendation || recommendation.items.length === 0)" description="暂无推荐数据" />

    <el-table
      v-if="recommendation && recommendation.items.length > 0"
      :data="recommendation.items"
      stripe
      row-class-name="clickable-row"
      @row-click="handleRowClick"
      size="small"
    >
      <el-table-column prop="rank" label="#" width="50" align="center" />
      <el-table-column label="图片" width="60" align="center">
        <template #default="{ row }">
          <el-image
            v-if="(row as Recommendation).image"
            :src="(row as Recommendation).image"
            fit="cover"
            class="product-img"
          >
            <template #error>
              <div class="img-fallback"><el-icon><Picture /></el-icon></div>
            </template>
          </el-image>
          <span v-else class="no-img">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="商品名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="price" label="价格" width="80" align="right">
        <template #default="{ row }">
          ¥{{ (row as Recommendation).price.toFixed(0) }}
        </template>
      </el-table-column>
      <el-table-column prop="score" label="AI评分" width="70" align="center" />
      <el-table-column prop="action" label="动作" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="ACTION_TAG_TYPE[(row as Recommendation).action]" size="small">
            {{ (row as Recommendation).action }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="market_level" label="竞争" width="70" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="(row as Recommendation).market_level"
            :type="MARKET_TAG_TYPE[(row as Recommendation).market_level ?? 'MEDIUM']"
            size="small"
          >
            {{ (row as Recommendation).market_level ?? '-' }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="knowledge_score" label="知识分" width="70" align="center">
        <template #default="{ row }">
          <span :style="{ color: (row as Recommendation).knowledge_score > 0 ? '#67c23a' : (row as Recommendation).knowledge_score < 0 ? '#f56c6c' : '#909399' }">
            {{ (row as Recommendation).knowledge_score > 0 ? '+' : '' }}{{ (row as Recommendation).knowledge_score }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="final_score" label="最终分" width="70" align="center">
        <template #default="{ row }">
          <strong>{{ (row as Recommendation).final_score }}</strong>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { getDailyRecommendations } from '@/api'
import type { Recommendation, DailyRecommendationResponse } from '@/types/workbench'
import { ACTION_TAG_TYPE, MARKET_TAG_TYPE } from '@/types/workbench'

const router = useRouter()
const loading = ref(false)
const recommendation = ref<DailyRecommendationResponse | null>(null)

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await getDailyRecommendations()
    recommendation.value = data
  } catch {
    ElMessage.error('获取今日推荐失败')
  } finally {
    loading.value = false
  }
})

function handleRowClick(row: Recommendation) {
  router.push(`/products/${row.product_id}`)
}
</script>

<style scoped>
.rec-card {
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

.product-img {
  width: 40px;
  height: 40px;
  border-radius: 4px;
}

.img-fallback {
  width: 40px;
  height: 40px;
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
</style>

<style>
.clickable-row {
  cursor: pointer;
}
</style>
