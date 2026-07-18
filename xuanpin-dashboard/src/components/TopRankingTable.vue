<template>
  <div class="top-ranking">
    <div class="toolbar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索商品名称"
        clearable
        style="width: 300px"
      />
    </div>

    <el-table
      v-loading="loading"
      :data="pagedData"
      stripe
      @sort-change="handleSortChange"
    >
      <el-table-column prop="rank" label="排名" width="80" align="center" />
      <el-table-column prop="name" label="商品名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="platform" label="平台" width="100" align="center" />
      <el-table-column prop="price" label="价格" width="100" align="right">
        <template #default="{ row }">
          {{ (row as RankingItem).price.toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column prop="ai_score" label="AI评分" width="100" align="right" sortable />
      <el-table-column prop="trend_score" label="趋势评分" width="100" align="right" sortable />
      <el-table-column prop="final_score" label="综合评分" width="100" align="right" sortable />
      <el-table-column prop="level" label="等级" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="LEVEL_TAG_TYPE[(row as RankingItem).level]">
            {{ (row as RankingItem).level }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 16px"
    />

    <div class="pagination">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="filteredSorted.length"
        layout="prev, pager, next"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getTop100 } from '@/api'
import { type RankingItem, LEVEL_TAG_TYPE } from '@/types/ranking'

type SortableField = 'ai_score' | 'trend_score' | 'final_score'
type SortDirection = 'ascending' | 'descending'

interface SortState {
  field: SortableField | null
  direction: SortDirection
}

const loading = ref(false)
const error = ref<string | null>(null)
const items = ref<RankingItem[]>([])
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = 20
const sort = ref<SortState>({ field: null, direction: 'ascending' })

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    const { data } = await getTop100()
    items.value = data
  } catch {
    error.value = '获取排行榜失败'
  } finally {
    loading.value = false
  }
})

const filteredSorted = computed(() => {
  const query = searchQuery.value.toLowerCase()
  let result = query
    ? items.value.filter(item => item.name.toLowerCase().includes(query))
    : [...items.value]

  if (sort.value.field) {
    const field = sort.value.field
    const dir = sort.value.direction === 'ascending' ? 1 : -1
    result = result.sort((a, b) => (a[field] - b[field]) * dir)
  }

  return result
})

const pagedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredSorted.value.slice(start, start + pageSize)
})

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  currentPage.value = 1
  if (order && (prop === 'ai_score' || prop === 'trend_score' || prop === 'final_score')) {
    sort.value = {
      field: prop,
      direction: order as SortDirection,
    }
  } else {
    sort.value = { field: null, direction: 'ascending' }
  }
}
</script>

<style scoped>
.top-ranking {
  margin-top: 20px;
}

.toolbar {
  margin-bottom: 16px;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}
</style>
