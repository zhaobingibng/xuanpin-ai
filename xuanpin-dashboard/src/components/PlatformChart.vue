<template>
  <el-card v-loading="loading" class="chart-card">
    <template #header>
      <span>平台商品分布</span>
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
import { BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  TitleComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { getPlatformStats } from '@/api'
import type { PlatformItem } from '@/types/stats'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, TitleComponent])

const loading = ref(false)
const items = ref<PlatformItem[]>([])

const chartOption = computed<EChartsCoreOption>(() => ({
  title: {
    text: '平台商品分布',
    left: 'center',
    textStyle: { fontSize: 14, fontWeight: 'bold' },
  },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
  },
  grid: { left: '3%', right: '10%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'value',
  },
  yAxis: {
    type: 'category',
    data: items.value.map(item => item.name),
  },
  series: [{
    type: 'bar',
    data: items.value.map(item => item.value),
    itemStyle: { color: '#409eff' },
    label: {
      show: true,
      position: 'right',
    },
    barMaxWidth: 40,
  }],
}))

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await getPlatformStats()
    items.value = Object.entries(data).map(([name, value]) => ({ name, value }))
  } catch {
    ElMessage.error('获取平台统计失败')
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
