<template>
  <el-card class="opp-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <span class="card-title">高机会商品</span>
        <el-tag v-if="opportunities.length > 0" type="success" size="small">
          {{ opportunities.length }} 个
        </el-tag>
      </div>
    </template>

    <el-empty v-if="!loading && opportunities.length === 0" description="暂无机会商品数据" />

    <el-table
      v-if="opportunities.length > 0"
      :data="opportunities"
      stripe
      size="small"
      :default-sort="{ prop: 'opportunity_score', order: 'descending' }"
    >
      <el-table-column prop="name" label="商品名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="opportunity_score" label="机会评分" width="100" align="center" sortable>
        <template #default="{ row }">
          <strong>{{ (row as Opportunity).opportunity_score }}</strong>
        </template>
      </el-table-column>
      <el-table-column prop="competition_score" label="竞争评分" width="100" align="center" />
      <el-table-column prop="market_level" label="市场等级" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="MARKET_TAG_TYPE[(row as Opportunity).market_level]" size="small">
            {{ (row as Opportunity).market_level }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="推荐理由" min-width="200">
        <template #default="{ row }">
          <div class="reasons">
            <el-tag
              v-for="(reason, idx) in (row as Opportunity).reasons.slice(0, 3)"
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
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getOpportunities } from '@/api'
import type { Opportunity } from '@/types/workbench'
import { MARKET_TAG_TYPE } from '@/types/workbench'

const loading = ref(false)
const opportunities = ref<Opportunity[]>([])

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await getOpportunities()
    opportunities.value = data
  } catch {
    ElMessage.error('获取机会商品失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.opp-card {
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
