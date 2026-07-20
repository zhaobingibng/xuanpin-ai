<template>
  <el-card class="assistant-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">AI运营助手</span>
        <el-tag type="primary" size="small">智能问答</el-tag>
      </div>
    </template>

    <!-- 输入区 -->
    <div class="input-area">
      <el-input
        v-model="question"
        placeholder="试试问我：今天卖什么？帮我写蓝牙耳机文案"
        clearable
        @keyup.enter="handleAsk"
        :disabled="asking"
      >
        <template #append>
          <el-button type="primary" :loading="asking" @click="handleAsk">
            发送
          </el-button>
        </template>
      </el-input>
    </div>

    <!-- 快捷问题 -->
    <div class="quick-questions" v-if="!response">
      <el-button
        v-for="q in quickQuestions"
        :key="q"
        size="small"
        text
        @click="askQuick(q)"
      >
        {{ q }}
      </el-button>
    </div>

    <!-- 回答区 -->
    <div v-if="response" class="response-area">
      <div class="answer-text">{{ response.answer }}</div>

      <!-- 洞察 -->
      <div v-if="response.insights.length > 0" class="insights">
        <el-tag
          v-for="(insight, idx) in response.insights"
          :key="idx"
          type="info"
          size="small"
          class="insight-tag"
        >
          {{ insight }}
        </el-tag>
      </div>

      <!-- 推荐商品 -->
      <div v-if="response.products.length > 0" class="products">
        <div
          v-for="(product, idx) in response.products"
          :key="idx"
          class="product-item"
        >
          <div class="product-name">{{ product.name }}</div>
          <el-tag size="small" type="warning">{{ product.score }}分</el-tag>
          <div class="product-reasons">
            <el-tag
              v-for="(r, rIdx) in product.reason.slice(0, 2)"
              :key="rIdx"
              size="small"
              class="reason-tag"
            >
              {{ r }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- 错误 -->
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" style="margin-top: 12px" />
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { askAssistant } from '@/api'
import type { AssistantResponse } from '@/types/workbench'

const question = ref('')
const asking = ref(false)
const error = ref<string | null>(null)
const response = ref<AssistantResponse | null>(null)

const quickQuestions = [
  '今天有什么爆款推荐？',
  '哪些商品趋势在上涨？',
  '哪些商品不要做？',
  '帮我写蓝牙耳机文案',
]

function askQuick(q: string) {
  question.value = q
  handleAsk()
}

async function handleAsk() {
  const q = question.value.trim()
  if (!q) return

  asking.value = true
  error.value = null
  response.value = null

  try {
    const { data } = await askAssistant(q)
    response.value = data
  } catch {
    error.value = 'AI回答失败，请稍后重试'
    ElMessage.error('AI回答失败')
  } finally {
    asking.value = false
  }
}
</script>

<style scoped>
.assistant-card {
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
  margin-bottom: 12px;
}

.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
}

.response-area {
  margin-top: 16px;
}

.answer-text {
  font-size: 15px;
  line-height: 1.6;
  color: #303133;
  white-space: pre-wrap;
  margin-bottom: 12px;
}

.insights {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.insight-tag {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.products {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.product-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.product-name {
  font-weight: 600;
  min-width: 120px;
}

.product-reasons {
  display: flex;
  gap: 4px;
}

.reason-tag {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
