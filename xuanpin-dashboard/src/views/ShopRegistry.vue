<template>
  <div class="shop-registry">
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span style="font-size: 18px; font-weight: 600">店铺监控管理</span>
          <el-button type="primary" @click="showCreateDialog">添加店铺</el-button>
        </div>
      </template>

      <el-table :data="shops" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="platform" label="平台" width="90">
          <template #default="{ row }">
            <el-tag :type="platformTagType(row.platform)" size="small">{{ row.platform }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="shop_name" label="店铺名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="shop_id" label="店铺ID" width="140" show-overflow-tooltip />
        <el-table-column prop="category" label="品类" width="100">
          <template #default="{ row }">{{ row.category || '-' }}</template>
        </el-table-column>
        <el-table-column prop="fans" label="粉丝" width="90" align="right">
          <template #default="{ row }">{{ formatFans(row.fans) }}</template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="priorityTagType(row.priority)" size="small">{{ priorityLabel(row.priority) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="启用" width="70" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="toggleEnabled(row)" :loading="row._saving" />
          </template>
        </el-table-column>
        <el-table-column prop="monitor_strategy" label="策略" width="80" />
        <el-table-column prop="last_scan_at" label="最近扫描" width="160">
          <template #default="{ row }">{{ row.last_scan_at ? new Date(row.last_scan_at).toLocaleString() : '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="showEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create / Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑店铺' : '添加店铺'" width="520">
      <el-form :model="form" label-width="80">
        <el-form-item label="平台" required>
          <el-select v-model="form.platform" :disabled="isEdit" style="width: 100%">
            <el-option label="淘宝" value="taobao" />
            <el-option label="天猫" value="tmall" />
            <el-option label="京东" value="jd" />
            <el-option label="拼多多" value="pdd" />
            <el-option label="抖音" value="douyin" />
            <el-option label="快手" value="kuaishou" />
          </el-select>
        </el-form-item>
        <el-form-item label="店铺ID" required>
          <el-input v-model="form.shop_id" :disabled="isEdit" placeholder="平台店铺唯一标识" />
        </el-form-item>
        <el-form-item label="店铺名称" required>
          <el-input v-model="form.shop_name" placeholder="例：某某旗舰店" />
        </el-form-item>
        <el-form-item label="店铺链接">
          <el-input v-model="form.shop_url" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="品类">
          <el-input v-model="form.category" placeholder="例：数码、美妆" />
        </el-form-item>
        <el-form-item label="粉丝数">
          <el-input-number v-model="form.fans" :min="0" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-radio-group v-model="form.priority">
            <el-radio :value="1">低</el-radio>
            <el-radio :value="2">中</el-radio>
            <el-radio :value="3">高</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="监控策略">
          <el-select v-model="form.monitor_strategy" style="width: 100%">
            <el-option label="每日 (daily)" value="daily" />
            <el-option label="每小时 (hourly)" value="hourly" />
            <el-option label="手动 (manual)" value="manual" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Shop } from '@/types/shop'
import { getShops, createShop, updateShop, deleteShop } from '@/api/index'

const shops = ref<(Shop & { _saving?: boolean })[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editingId = ref<number | null>(null)
const submitting = ref(false)

const defaultForm = {
  platform: 'taobao',
  shop_id: '',
  shop_name: '',
  shop_url: '',
  category: '',
  fans: 0,
  priority: 1,
  enabled: true,
  monitor_strategy: 'daily',
}
const form = reactive({ ...defaultForm })

onMounted(() => {
  fetchShops()
})

async function fetchShops() {
  loading.value = true
  try {
    const resp = await getShops()
    shops.value = resp.data
  } catch {
    ElMessage.error('获取店铺列表失败')
  } finally {
    loading.value = false
  }
}

function showCreateDialog() {
  isEdit.value = false
  editingId.value = null
  Object.assign(form, defaultForm)
  dialogVisible.value = true
}

function showEditDialog(row: Shop) {
  isEdit.value = true
  editingId.value = row.id
  Object.assign(form, {
    platform: row.platform,
    shop_id: row.shop_id,
    shop_name: row.shop_name,
    shop_url: row.shop_url || '',
    category: row.category || '',
    fans: row.fans,
    priority: row.priority,
    enabled: row.enabled,
    monitor_strategy: row.monitor_strategy,
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!form.platform || !form.shop_id || !form.shop_name) {
    ElMessage.warning('请填写平台、店铺ID和店铺名称')
    return
  }
  submitting.value = true
  try {
    if (isEdit.value && editingId.value) {
      await updateShop(editingId.value, {
        shop_name: form.shop_name,
        shop_url: form.shop_url || undefined,
        category: form.category || undefined,
        fans: form.fans,
        priority: form.priority,
        enabled: form.enabled,
        monitor_strategy: form.monitor_strategy,
      })
      ElMessage.success('更新成功')
    } else {
      await createShop({
        platform: form.platform,
        shop_id: form.shop_id,
        shop_name: form.shop_name,
        shop_url: form.shop_url || undefined,
        category: form.category || undefined,
        fans: form.fans,
        priority: form.priority,
        enabled: form.enabled,
        monitor_strategy: form.monitor_strategy,
      })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchShops()
  } catch (err: any) {
    const detail = err?.response?.data?.detail || '操作失败'
    ElMessage.error(detail)
  } finally {
    submitting.value = false
  }
}

async function toggleEnabled(row: Shop & { _saving?: boolean }) {
  row._saving = true
  try {
    await updateShop(row.id, { enabled: row.enabled })
    ElMessage.success(row.enabled ? '已启用' : '已禁用')
  } catch {
    row.enabled = !row.enabled
    ElMessage.error('更新失败')
  } finally {
    row._saving = false
  }
}

async function handleDelete(row: Shop) {
  try {
    await ElMessageBox.confirm(`确定删除店铺「${row.shop_name}」吗？`, '确认删除', {
      type: 'warning',
    })
    await deleteShop(row.id)
    ElMessage.success('已删除')
    fetchShops()
  } catch {
    // cancelled
  }
}

function platformTagType(platform: string) {
  const map: Record<string, string> = {
    taobao: 'danger', tmall: 'danger', jd: 'warning',
    pdd: 'success', douyin: '', kuaishou: 'info',
  }
  return map[platform] || ''
}

function priorityTagType(p: number) {
  return p === 3 ? 'danger' : p === 2 ? 'warning' : 'info'
}

function priorityLabel(p: number) {
  return p === 3 ? '高' : p === 2 ? '中' : '低'
}

function formatFans(n: number) {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}
</script>

<style scoped>
.shop-registry {
  max-width: 1400px;
  margin: 0 auto;
}
</style>
