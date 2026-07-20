<template>
  <el-card v-loading="loading" class="chart-card">
    <template #header>
      <span>商品分类分布</span>
    </template>

    <el-empty v-if="!loading && items.length === 0" description="暂无数据" />

    <v-chart
      v-else-if="items.length > 0"
      class="chart"
      :option="chartOption"
      autoresize
    />
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { use, type EChartsCoreOption } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import {
  TooltipComponent,
  LegendComponent,
  TitleComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { getCategoryStats } from '@/api'
import type { CategoryItem } from '@/types/stats'

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent, TitleComponent])

const loading = ref(false)
const items = ref<CategoryItem[]>([])

const chartOption = computed<EChartsCoreOption>(() => ({
  title: {
    text: '商品分类分布',
    left: 'center',
    textStyle: { fontSize: 14, fontWeight: 'bold' },
  },
  tooltip: {
    trigger: 'item',
    formatter: '{b}: {c} ({d}%)',
  },
  legend: {
    bottom: 0,
  },
  series: [{
    type: 'pie',
    radius: '55%',
    center: ['50%', '50%'],
    data: items.value,
    label: { show: true },
    emphasis: {
      itemStyle: {
        shadowBlur: 10,
        shadowOffsetX: 0,
        shadowColor: 'rgba(0, 0, 0, 0.5)',
      },
    },
  }],
}))

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await getCategoryStats()
    items.value = Object.entries(data).map(([name, value]) => ({ name, value }))
  } catch {
    ElMessage.error('获取分类统计失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.chart-card {
  border-radius: 12px;
}

.chart {
  height: 350px;
}
</style>
