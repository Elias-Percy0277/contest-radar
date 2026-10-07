<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { Contest } from '../types'
import { api } from '../api/client'
import { errText } from '../utils/format'

const props = defineProps<{ contest: Contest }>()
const emit = defineEmits<{ (e: 'updated', contest: Contest): void }>()
const loading = ref(false)

async function set(value: 'joined' | 'ignored' | 'none') {
  loading.value = true
  try {
    const updated = await api.setMyStatus(props.contest.id, value)
    const tip =
      value === 'joined' ? '已加入「我的日程」' : value === 'ignored' ? '已忽略（列表默认隐藏）' : '已恢复为未标记'
    ElMessage.success(tip)
    emit('updated', updated)
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <span class="msb">
    <template v-if="contest.my_status === 'none'">
      <el-button link type="primary" size="small" :disabled="loading" @click="set('joined')">我要参加</el-button>
      <el-button link type="info" size="small" :disabled="loading" @click="set('ignored')">忽略</el-button>
    </template>
    <template v-else-if="contest.my_status === 'joined'">
      <el-button link type="warning" size="small" :disabled="loading" @click="set('none')">取消参加</el-button>
    </template>
    <template v-else>
      <el-button link type="success" size="small" :disabled="loading" @click="set('none')">恢复</el-button>
    </template>
  </span>
</template>

<style scoped>
.msb :deep(.el-button + .el-button) {
  margin-left: 8px;
}
</style>
