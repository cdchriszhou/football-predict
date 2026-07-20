<template>
  <div class="team-compare">
    <div ref="chartRef" class="compare-chart"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts'

const props = defineProps({
  teamA: { type: Object, default: () => ({}) },
  teamB: { type: Object, default: () => ({}) }
})

const { t, locale } = useI18n()
const chartRef = ref(null)
let chart = null

function renderChart() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)

  const a = props.teamA || {}
  const b = props.teamB || {}
  const homeLabel = a.name || t('team.homeTeam')
  const awayLabel = b.name || t('team.awayTeam')

  const option = {
    tooltip: {},
    legend: {
      data: [homeLabel, awayLabel],
      bottom: 0
    },
    radar: {
      center: ['50%', '50%'],
      radius: '65%',
      indicator: [
        { name: t('team.attrAttack'), max: 100 },
        { name: t('team.attrDefend'), max: 100 },
        { name: t('team.attrMidfield'), max: 100 },
        { name: t('team.attrSpeed'), max: 100 },
        { name: t('team.attrPhysical'), max: 100 }
      ]
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: [a.attack || 0, a.defend || 0, a.midfield || 0, a.speed || 0, a.physical || 0],
          name: homeLabel,
          areaStyle: { color: 'rgba(26, 35, 126, 0.2)' },
          lineStyle: { color: '#1a237e', width: 2 },
          itemStyle: { color: '#1a237e' }
        },
        {
          value: [b.attack || 0, b.defend || 0, b.midfield || 0, b.speed || 0, b.physical || 0],
          name: awayLabel,
          areaStyle: { color: 'rgba(244, 67, 54, 0.15)' },
          lineStyle: { color: '#f44336', width: 2 },
          itemStyle: { color: '#f44336' }
        }
      ]
    }]
  }

  chart.setOption(option, true)
}

let resizeHandler = null

onMounted(() => {
  renderChart()
  resizeHandler = () => { if (chart) chart.resize() }
  window.addEventListener('resize', resizeHandler)
})

watch(() => [props.teamA, props.teamB, locale.value], renderChart, { deep: true })
onUnmounted(() => {
  if (chart) chart.dispose()
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
})
</script>

<style scoped>
.compare-chart { width: 100%; height: 360px; }

@media (max-width: 767px) {
  .compare-chart { height: 260px; }
}
</style>
