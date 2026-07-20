<template>
  <div class="daily-report" v-loading="loading">
    <div class="page-header">
      <el-button text @click="router.push('/')">
        <el-icon><ArrowLeft /></el-icon>
        返回首页
      </el-button>
      <h2>AI 每日选品报告</h2>
      <p v-if="report" class="report-date">{{ report.date }}</p>
    </div>

    <!-- KPI 卡片 -->
    <el-row :gutter="20" class="kpi-row" v-if="report && report.total > 0">
      <el-col :span="6">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ report.total }}</div>
          <div class="kpi-label">今日商品数量</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="kpi-card kpi-hot">
          <div class="kpi-value">{{ report.hot_products }}</div>
          <div class="kpi-label">爆款数量</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="kpi-card kpi-potential">
          <div class="kpi-value">{{ report.potential_products }}</div>
          <div class="kpi-label">潜力商品数量</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-value">{{ report.average_score.toFixed(1) }}</div>
          <div class="kpi-label">平均评分</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 空数据 -->
    <el-empty
      v-if="report && report.total === 0"
      description="暂无选品数据"
    />

    <!-- 错误提示 -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 16px"
    />

    <!-- TOP20 商品列表 -->
    <el-table
      v-if="report && report.items.length > 0"
      :data="report.items"
      stripe
      row-class-name="clickable-row"
      @row-click="handleRowClick"
      class="report-table"
    >
      <el-table-column prop="rank" label="排名" width="80" align="center" />
      <el-table-column label="商品图片" width="80" align="center">
        <template #default="{ row }">
          <el-image
            v-if="(row as ReportItem).image"
            :src="(row as ReportItem).image"
            fit="cover"
            class="product-img"
          >
            <template #error>
              <div class="img-fallback">
                <el-icon><Picture /></el-icon>
              </div>
            </template>
          </el-image>
          <span v-else class="no-img">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="商品名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="platform" label="平台" width="100" align="center" />
      <el-table-column prop="price" label="价格" width="100" align="right">
        <template #default="{ row }">
          {{ (row as ReportItem).price.toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column prop="score" label="评分" width="80" align="center" />
      <el-table-column prop="level" label="等级" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="REPORT_LEVEL_TAG_TYPE[(row as ReportItem).level]">
            {{ (row as ReportItem).level }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="推荐理由" min-width="260">
        <template #default="{ row }">
          <div class="reasons">
            <el-tag
              v-for="(reason, idx) in (row as ReportItem).reasons.slice(0, 3)"
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Picture } from '@element-plus/icons-vue'
import { getDailyReport } from '@/api'
import { type ReportItem, type DailyReport, REPORT_LEVEL_TAG_TYPE } from '@/types/report'

const router = useRouter()

const loading = ref(false)
const error = ref<string | null>(null)
const report = ref<DailyReport | null>(null)

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    const { data } = await getDailyReport(20)
    report.value = data
  } catch {
    error.value = '获取每日选品报告失败'
    ElMessage.error('获取每日选品报告失败')
  } finally {
    loading.value = false
  }
})

function handleRowClick(row: ReportItem) {
  router.push(`/products/${row.product_id}`)
}
</script>

<style scoped>
.daily-report {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 8px 0 4px;
}

.report-date {
  color: #909399;
  margin: 0;
}

.kpi-row {
  margin-bottom: 20px;
}

.kpi-card {
  text-align: center;
}

.kpi-value {
  font-size: 32px;
  font-weight: 700;
  color: #303133;
}

.kpi-hot .kpi-value {
  color: #f56c6c;
}

.kpi-potential .kpi-value {
  color: #e6a23c;
}

.kpi-label {
  font-size: 14px;
  color: #909399;
  margin-top: 8px;
}

.report-table {
  margin-top: 20px;
}

.product-img {
  width: 50px;
  height: 50px;
  border-radius: 4px;
}

.img-fallback {
  width: 50px;
  height: 50px;
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

<style>
.clickable-row {
  cursor: pointer;
}
</style>
