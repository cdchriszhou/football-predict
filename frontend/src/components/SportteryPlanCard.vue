<template>
  <el-card class="plan-card" shadow="hover">
    <div class="plan-card-head">
      <span class="match-num">{{ pick.match_num }}</span>
      <span class="kickoff">{{ formatKickoff(pick.kickoff) }}</span>
      <el-tag size="small" type="warning">{{ t('sportteryPlan.playCrs') }}</el-tag>
    </div>

    <div class="plan-card-teams">
      <div class="team-side">
        <TeamBadge :name="pick.team_a" :size="36" />
        <span class="team-name">{{ pick.team_a }}</span>
      </div>
      <span class="vs">VS</span>
      <div class="team-side">
        <TeamBadge :name="pick.team_b" :size="36" />
        <span class="team-name">{{ pick.team_b }}</span>
      </div>
    </div>

    <div class="score-picks-block">
      <div
        v-for="sp in scorePickList"
        :key="sp.score"
        class="score-pick-item"
        :class="sp.type === 'upset' ? 'pick-upset' : `pick-likely-${sp.rank}`"
      >
        <span class="pick-tag">
          <template v-if="sp.type === 'likely' && sp.rank === 1">{{ t('sportteryPlan.cardLikely1') }}</template>
          <template v-else-if="sp.type === 'likely' && sp.rank === 2">{{ t('sportteryPlan.cardLikely2') }}</template>
          <template v-else>{{ t('sportteryPlan.cardUpsetTag') }}</template>
        </span>
        <span class="pick-score">{{ sp.score }}</span>
        <span class="pick-odds">@ {{ formatCrsOdds(sp.odds) }}</span>
      </div>
      <div class="confidence">
        {{ t('sportteryPlan.cardConfidence') }} {{ (pick.confidence * 100).toFixed(0) }}%
      </div>
    </div>

    <p class="reason">{{ pick.reason }}</p>

    <div class="plan-card-foot">
      <router-link
        v-if="pick.match_id"
        :to="`${basePath}/matches/${pick.match_id}`"
        class="detail-link"
        @click.stop
      >
        {{ t('sportteryPlan.cardViewMatch') }}
      </router-link>
      <el-popover v-if="pick.references" placement="top" :width="360" trigger="click">
        <template #reference>
          <el-button link type="primary" size="small" @click.stop>{{ t('sportteryPlan.viewRefs') }}</el-button>
        </template>
        <div class="refs-popover">
          <p class="refs-title">{{ t('sportteryPlan.refsTitle') }}</p>
          <div class="refs-tags">
            <el-tag v-for="src in pick.data_sources" :key="src" size="small" style="margin:2px">{{ src }}</el-tag>
          </div>
          <template v-if="pick.references.teams">
            <p class="refs-sub">{{ t('sportteryPlan.refsTeams') }}</p>
            <div v-for="side in ['team_a', 'team_b']" :key="side" class="team-ref">
              <template v-if="pick.references.teams[side]?.available">
                <strong>{{ pick.references.teams[side].name }}</strong>
                <span>FIFA #{{ pick.references.teams[side].rank }}</span>
              </template>
            </div>
          </template>
          <template v-if="pick.references.alerts?.length">
            <p class="refs-sub">{{ t('sportteryPlan.refsAlerts') }}</p>
            <p v-for="(a, i) in pick.references.alerts" :key="i" class="alert-line">{{ a }}</p>
          </template>
        </div>
      </el-popover>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TeamBadge from '@/components/TeamBadge.vue'
import { useCompetitionStore } from '@/stores/competition'
import { formatCrsOdds } from '@/utils/sportteryCrs'

const { t } = useI18n()
const compStore = useCompetitionStore()

const props = defineProps({
  pick: { type: Object, required: true },
})

const basePath = computed(() => compStore.basePath)

const scorePickList = computed(() => {
  let list
  if (props.pick.score_picks?.length) {
    list = [...props.pick.score_picks]
  } else {
    list = [{
      score: props.pick.pick,
      odds: props.pick.odds,
      type: 'likely',
      rank: 1,
    }]
    for (const alt of props.pick.alt_scores || []) {
      list.push({
        score: alt.score,
        odds: alt.odds,
        type: alt.is_upset ? 'upset' : 'likely',
        rank: alt.is_upset ? 1 : (alt.rank || list.filter((x) => x.type === 'likely').length + 1),
      })
    }
  }
  const likely = list.filter((x) => x.type !== 'upset').slice(0, 2)
  const upset = list.find((x) => x.type === 'upset' || x.is_upset)
  const merged = [...likely]
  if (upset) merged.push(upset)
  return merged
})

function formatKickoff(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const mo = String(d.getMonth() + 1).padStart(2, '0')
    const da = String(d.getDate()).padStart(2, '0')
    return `${mo}/${da} ${hh}:${mm}`
  } catch {
    return iso
  }
}
</script>

<style scoped>
.plan-card {
  height: 100%;
  border-radius: 12px;
}
.plan-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}
.match-num {
  font-weight: 700;
  color: #1a237e;
  font-size: 15px;
}
.kickoff {
  color: #909399;
  font-size: 13px;
  flex: 1;
}
.plan-card-teams {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 16px;
}
.team-side {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.team-side:last-child .team-name {
  text-align: center;
}
.team-name {
  font-size: 14px;
  font-weight: 600;
  text-align: center;
  word-break: break-word;
}
.vs {
  color: #c0c4cc;
  font-weight: 700;
  font-size: 13px;
  flex-shrink: 0;
}
.score-picks-block {
  background: linear-gradient(135deg, #f0f4ff 0%, #f8fafc 100%);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
}
.score-pick-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 6px;
}
.score-pick-item:last-of-type {
  margin-bottom: 0;
}
.pick-likely-1 {
  background: #ecf5ff;
}
.pick-likely-2 {
  background: #f0f9eb;
}
.pick-upset {
  background: #fdf6ec;
  border: 1px dashed #e6a23c;
}
.pick-tag {
  font-size: 11px;
  font-weight: 600;
  color: #606266;
  min-width: 52px;
}
.pick-score {
  font-size: 22px;
  font-weight: 800;
  color: #1a237e;
  flex: 1;
}
.pick-odds {
  font-size: 14px;
  font-weight: 600;
  color: #e6a23c;
}
.confidence {
  font-size: 12px;
  color: #909399;
  text-align: center;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e4e7ed;
}
.reason {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  margin: 0 0 12px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.plan-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid #ebeef5;
  padding-top: 10px;
}
.detail-link {
  font-size: 13px;
  color: #1a237e;
  text-decoration: none;
}
.detail-link:hover {
  text-decoration: underline;
}
.refs-popover {
  font-size: 13px;
  line-height: 1.6;
}
.refs-title {
  font-weight: 600;
  margin: 0 0 8px;
}
.refs-sub {
  font-weight: 600;
  margin: 10px 0 4px;
  color: #606266;
}
.team-ref {
  margin-bottom: 4px;
}
.alert-line {
  color: #e6a23c;
  margin: 2px 0;
}
</style>
