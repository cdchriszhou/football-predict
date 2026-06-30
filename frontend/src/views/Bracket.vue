<template>
  <div class="bracket-page">
    <div class="page-header">
      <h2>{{ t('bracket.title') }}</h2>
      <p>{{ t('bracket.subtitle') }}</p>
    </div>

    <el-card class="bracket-card">
      <BracketPyramid />
    </el-card>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import BracketPyramid from '@/components/BracketPyramid.vue'

const { t } = useI18n()
</script>

<style scoped>
.bracket-card { border-radius: 12px; }
</style>
