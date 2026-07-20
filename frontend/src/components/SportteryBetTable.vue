<template>
  <div class="bet-table-wrap">
    <table class="bet-table">
      <thead>
        <tr>
          <th>{{ t('sportteryPlan.colBetScore') }}</th>
          <th>{{ t('sportteryPlan.colBetStake') }}</th>
          <th>{{ t('sportteryPlan.colBetReturn') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, i) in rows"
          :key="`${row.score}-${i}`"
          :class="{ 'row-main': row.main, 'row-upset': row.isUpset }"
        >
          <td class="col-score">
            <span v-if="row.pickType === 'likely' && row.likelyRank === 1" class="likely-tag">{{ t('sportteryPlan.cardLikely1') }}</span>
            <span v-else-if="row.pickType === 'likely' && row.likelyRank === 2" class="likely-tag likely-tag-2">{{ t('sportteryPlan.cardLikely2') }}</span>
            <span v-else-if="row.isUpset" class="upset-tag">{{ t('sportteryPlan.cardUpsetTag') }}</span>
            {{ row.score }}
          </td>
          <td class="col-stake">
            <div class="stake-input-wrap">
              <el-input-number
                v-model="row.stake"
                :min="1"
                :max="50000"
                :step="1"
                size="small"
                controls-position="right"
                class="stake-input"
              />
              <span class="yuan">{{ t('sportteryPlan.yuanUnit') }}</span>
            </div>
          </td>
          <td class="col-return">{{ formatPrize(row) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="hint" class="bet-hint">{{ hint }}</p>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { calcBetReturn, DEFAULT_STAKE_YUAN, formatReturnYuan } from '@/utils/sportteryBet'

const { t } = useI18n()

const props = defineProps({
  items: { type: Array, required: true },
  hint: { type: String, default: '' },
  initialStake: { type: Number, default: DEFAULT_STAKE_YUAN },
})

const rows = ref([])

watch(
  () => props.items,
  (items) => {
    const def = props.initialStake > 0 ? props.initialStake : DEFAULT_STAKE_YUAN
    rows.value = items.map((item, i) => ({
      score: item.score,
      odds: item.odds,
      main: !!item.main,
      isUpset: !!item.isUpset,
      stake: rows.value[i]?.stake ?? def,
      pickType: item.pickType,
      likelyRank: item.likelyRank,
    }))
  },
  { immediate: true, deep: true },
)

/** 体彩理论奖金 = 投注金额 × CRS 赔率（含本金返还） */
function formatPrize(row) {
  if (!row.stake || row.stake <= 0) return '-'
  const { returnAmount } = calcBetReturn(row.odds, row.stake)
  return formatReturnYuan(returnAmount)
}
</script>

<style scoped>
.bet-table-wrap {
  margin-bottom: 12px;
}
.bet-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: #fafafa;
  border-radius: 8px;
  overflow: hidden;
}
.bet-table th {
  background: #eef1f6;
  color: #606266;
  font-weight: 600;
  padding: 8px 10px;
  text-align: center;
}
.bet-table td {
  padding: 8px 6px;
  text-align: center;
  border-top: 1px solid #ebeef5;
  color: #303133;
  vertical-align: middle;
}
.bet-table tr.row-main td {
  background: #f0f4ff;
  font-weight: 600;
}
.bet-table tr.row-upset td {
  background: #fffbf0;
}
.col-score {
  font-weight: 700;
  color: #1a237e;
  font-size: 15px;
}
.col-stake {
  width: 108px;
}
.stake-input-wrap {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  justify-content: center;
}
.stake-input {
  width: 72px;
}
.yuan {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}
.col-return {
  color: #f56c6c;
  font-weight: 700;
}
.likely-tag {
  display: inline-block;
  font-size: 11px;
  color: #409eff;
  margin-right: 4px;
  font-weight: 500;
}
.likely-tag-2 {
  color: #67c23a;
}
.upset-tag {
  display: inline-block;
  font-size: 11px;
  color: #e6a23c;
  margin-right: 4px;
  font-weight: 500;
}
.bet-hint {
  margin: 6px 0 0;
  font-size: 11px;
  color: #909399;
  text-align: right;
}
</style>
