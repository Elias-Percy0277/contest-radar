<script setup lang="ts">
import { computed } from 'vue'
import type { ContestStatus } from '../types'
import { STATUS_TAG_TYPE, STATUS_TEXT } from '../utils/format'

const props = defineProps<{ status: ContestStatus }>()
const type = computed(() => STATUS_TAG_TYPE[props.status])
const text = computed(() => STATUS_TEXT[props.status])
</script>

<template>
  <el-tag :type="type" size="small" effect="light">{{ text }}</el-tag>
</template>
