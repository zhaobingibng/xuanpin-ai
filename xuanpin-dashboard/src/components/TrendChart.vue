<template>
  <el-card class="trend-card">
    <template #header>
      <span>趋势图表</span>
    </template>

    <el-empty v-if="history.length === 0" description="暂无历史数据" />

    <template v-else>
      <div class="chart-wrapper">
        <v-chart class="chart" :option="priceOption" autoresize />
      </div>
      <div class="chart-wrapper">
        <v-chart class="chart" :option="salesOption" autoresize />
      </div>
      <div class="chart-wrapper chart-last">
        <v-chart class="chart" :option="viewersOption" autoresize />
      </div>
    </template>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { use, type EChartsCoreOption } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import type { ProductHistory } from '@/types/product'

use([
  CanvasRenderer,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
])

interface TrendChartProps {
  history: ProductHistory[]
}

const props = defineProps<TrendChartProps>()

function formatDate(recordTime: string): string {
  return recordTime.slice(0, 10)
}

function getSortedHistory(): ProductHistory[] {
  return [...props.history].sort(
    (a, b) => new Date(a.record_time).getTime() - new Date(b.record_time).getTime(),
  )
}

function buildOption(
  title: string,
  field: 'price' | 'sales_24h' | 'viewers',
  seriesName: string,
  yAxisName: string,
  color: string,
  valueFormatter: (v: number) => string,
): EChartsCoreOption {
  const sorted = getSortedHistory()
  const dates = sorted.map(h => formatDate(h.record_time))
  const values = sorted.map(h => h[field])

  return {
    title: {
      text: title,
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
    animation: true,
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      name: yAxisName,
    },
    series: [{
      name: seriesName,
      type: 'line',
      data: values,
      smooth: true,
      itemStyle: { color },
      valueFormatter: (v: number | null) => v != null ? valueFormatter(v) : '-',
    }],
  }
}

const priceOption = computed(() =>
  buildOption('价格趋势', 'price', '价格', '价格（元）', '#409eff', v => v.toFixed(2)),
)

const salesOption = computed(() =>
  buildOption('24小时销量趋势', 'sales_24h', '销量', '销量', '#67c23a', v => String(v)),
)

const viewersOption = computed(() =>
  buildOption('浏览人数趋势', 'viewers', '浏览人数', '浏览人数', '#e6a23c', v => String(v)),
)
</script>

<style scoped>
.trend-card {
  margin-bottom: 20px;
}

.chart-wrapper {
  margin-bottom: 24px;
}

.chart-last {
  margin-bottom: 0;
}

.chart {
  height: 300px;
}
</style>
