<template>
  <el-card class="parlay-card" shadow="hover">
    <div class="parlay-head">
      <el-tag type="danger" effect="dark">{{ parlayTypeLabel(parlay.type) }}</el-tag>
      <strong class="parlay-name">{{ t(`sportteryPlan.parlayNames.${parlay.name_key}`) }}</strong>
    </div>
    <p class="parlay-reason">{{ t(`sportteryPlan.parlayReasons.${parlay.reason_key}`) }}</p>

    <ul class="parlay-picks">
      <li v-for="(p, i) in parlay.picks" :key="i">
        <div class="pick-row-top">
          <span class="pick-num">{{ p.match_num }}</span>
          <span class="pick-teams">{{ p.team_a }} vs {{ p.team_b }}</span>
        </div>
        <div class="pick-row-score">
          <el-tag size="small" type="warning">{{ t('sportteryPlan.playCrs') }}</el-tag>
          <span class="score-pick">{{ formatPick(p.pick) }}</span>
          <span class="score-odds">@ {{ p.odds }}</span>
        </div>
      </li>
    </ul>

    <div class="parlay-footer">
      <div class="footer-item">
        <span class="footer-label">{{ t('sportteryPlan.combinedOdds') }}</span>
        <strong class="footer-value odds-value">{{ parlay.combined_odds }}</strong>
      </div>
      <div class="footer-item">
        <span class="footer-label">{{ t('sportteryPlan.avgConfidence') }}</span>
        <strong class="footer-value">{{ (parlay.avg_confidence * 100).toFixed(0) }}%</strong>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({
  parlay: { type: Object, required: true },
})

function parlayTypeLabel(type) {
  const map = {
    '2串1': 'type2x1',
    '3串1': 'type3x1',
    '4串1': 'type4x1',
    '5串1': 'type5x1',
  }
  const key = map[type]
  return key ? t(`sportteryPlan.${key}`) : type
}

function formatPick(pick) {
  if (typeof pick === 'string' && pick.includes(':')) return pick
  return pick
}
</script>

<style scoped>
.parlay-card {
  height: 100%;
  border-radius: 12px;
  border: 1px solid #fde2e2;
  background: linear-gradient(180deg, #fff 0%, #fff8f8 100%);
}
.parlay-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.parlay-name {
  font-size: 15px;
  color: #303133;
}
.parlay-reason {
  font-size: 13px;
  color: #909399;
  margin: 0 0 14px;
  line-height: 1.5;
}
.parlay-picks {
  list-style: none;
  padding: 0;
  margin: 0 0 14px;
}
.parlay-picks li {
  padding: 10px 0;
  border-bottom: 1px dashed #ebeef5;
}
.parlay-picks li:last-child {
  border-bottom: none;
}
.pick-row-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.pick-num {
  font-weight: 700;
  color: #1a237e;
  font-size: 13px;
  min-width: 52px;
}
.pick-teams {
  font-size: 13px;
  color: #303133;
  flex: 1;
}
.pick-row-score {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 60px;
}
.score-pick {
  font-size: 20px;
  font-weight: 800;
  color: #1a237e;
}
.score-odds {
  font-size: 15px;
  font-weight: 600;
  color: #e6a23c;
}
.parlay-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid #fde2e2;
}
.footer-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.footer-label {
  font-size: 12px;
  color: #909399;
}
.footer-value {
  font-size: 18px;
  color: #303133;
}
.odds-value {
  color: #f56c6c;
}
</style>
