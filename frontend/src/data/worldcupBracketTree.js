/**
 * FIFA 2026 knockout bracket slot order (match_no 73–104).
 * Left / right wings converge at center final (104); third place (103) below.
 */

import { matchWinnerSide } from '@/utils/matchScore'

export const KNOCKOUT_FIXTURES = [
  { match_no: 73, stage: '1/16决赛', team_a: '南非', team_b: '加拿大', kickoff: '2026-06-29T03:00:00' },
  { match_no: 74, stage: '1/16决赛', team_a: '德国', team_b: '巴拉圭', kickoff: '2026-06-30T04:30:00' },
  { match_no: 75, stage: '1/16决赛', team_a: '荷兰', team_b: '摩洛哥', kickoff: '2026-06-30T09:00:00' },
  { match_no: 76, stage: '1/16决赛', team_a: '巴西', team_b: '日本', kickoff: '2026-06-30T01:00:00' },
  { match_no: 77, stage: '1/16决赛', team_a: '法国', team_b: '瑞典', kickoff: '2026-07-01T06:00:00' },
  { match_no: 78, stage: '1/16决赛', team_a: '科特迪瓦', team_b: '挪威', kickoff: '2026-07-01T01:00:00' },
  { match_no: 79, stage: '1/16决赛', team_a: '墨西哥', team_b: '厄瓜多尔', kickoff: '2026-07-01T10:00:00' },
  { match_no: 80, stage: '1/16决赛', team_a: '英格兰', team_b: '刚果(金)', kickoff: '2026-07-02T00:00:00' },
  { match_no: 81, stage: '1/16决赛', team_a: '美国', team_b: '波黑', kickoff: '2026-07-02T09:00:00' },
  { match_no: 82, stage: '1/16决赛', team_a: '比利时', team_b: '塞内加尔', kickoff: '2026-07-02T04:00:00' },
  { match_no: 83, stage: '1/16决赛', team_a: '葡萄牙', team_b: '克罗地亚', kickoff: '2026-07-03T07:00:00' },
  { match_no: 84, stage: '1/16决赛', team_a: '西班牙', team_b: '奥地利', kickoff: '2026-07-03T03:00:00' },
  { match_no: 85, stage: '1/16决赛', team_a: '瑞士', team_b: '阿尔及利亚', kickoff: '2026-07-03T11:00:00' },
  { match_no: 86, stage: '1/16决赛', team_a: '阿根廷', team_b: '佛得角', kickoff: '2026-07-04T06:00:00' },
  { match_no: 87, stage: '1/16决赛', team_a: '哥伦比亚', team_b: '加纳', kickoff: '2026-07-04T09:30:00' },
  { match_no: 88, stage: '1/16决赛', team_a: '澳大利亚', team_b: '埃及', kickoff: '2026-07-04T02:00:00' },
  { match_no: 89, stage: '1/8决赛', team_a: '第74场胜者', team_b: '第77场胜者', kickoff: '2026-07-05T05:00:00' },
  { match_no: 90, stage: '1/8决赛', team_a: '加拿大', team_b: '第75场胜者', kickoff: '2026-07-05T00:00:00' },
  { match_no: 91, stage: '1/8决赛', team_a: '第76场胜者', team_b: '第78场胜者', kickoff: '2026-07-06T04:00:00' },
  { match_no: 92, stage: '1/8决赛', team_a: '第79场胜者', team_b: '第80场胜者', kickoff: '2026-07-06T08:00:00' },
  { match_no: 93, stage: '1/8决赛', team_a: '第83场胜者', team_b: '第84场胜者', kickoff: '2026-07-07T02:00:00' },
  { match_no: 94, stage: '1/8决赛', team_a: '第81场胜者', team_b: '第82场胜者', kickoff: '2026-07-07T05:00:00' },
  { match_no: 95, stage: '1/8决赛', team_a: '第86场胜者', team_b: '第88场胜者', kickoff: '2026-07-08T00:00:00' },
  { match_no: 96, stage: '1/8决赛', team_a: '第85场胜者', team_b: '第87场胜者', kickoff: '2026-07-08T01:00:00' },
  { match_no: 97, stage: '1/4决赛', team_a: '第89场胜者', team_b: '第90场胜者', kickoff: '2026-07-10T04:00:00' },
  { match_no: 98, stage: '1/4决赛', team_a: '第93场胜者', team_b: '第94场胜者', kickoff: '2026-07-11T00:00:00' },
  { match_no: 99, stage: '1/4决赛', team_a: '第91场胜者', team_b: '第92场胜者', kickoff: '2026-07-12T05:00:00' },
  { match_no: 100, stage: '1/4决赛', team_a: '第95场胜者', team_b: '第96场胜者', kickoff: '2026-07-12T08:00:00' },
  { match_no: 101, stage: '半决赛', team_a: '第97场胜者', team_b: '第98场胜者', kickoff: '2026-07-15T02:00:00' },
  { match_no: 102, stage: '半决赛', team_a: '第99场胜者', team_b: '第100场胜者', kickoff: '2026-07-16T03:00:00' },
  { match_no: 103, stage: '季军赛', team_a: '第101场负者', team_b: '第102场负者', kickoff: '2026-07-19T05:00:00' },
  { match_no: 104, stage: '决赛', team_a: '第101场胜者', team_b: '第102场胜者', kickoff: '2026-07-20T03:00:00' },
]

const FIXTURE_BY_NO = Object.fromEntries(KNOCKOUT_FIXTURES.map((f) => [f.match_no, f]))

const KICKOFF_TOLERANCE_MS = 3600 * 1000

function kickoffMs(value) {
  if (!value) return null
  const ms = new Date(value).getTime()
  return Number.isFinite(ms) ? ms : null
}

function findRowForFixture(fx, pool, byTeams) {
  const target = kickoffMs(fx.kickoff)
  if (target != null) {
    let best = null
    let bestDelta = KICKOFF_TOLERANCE_MS + 1
    for (const m of pool) {
      const mt = kickoffMs(m.match_time)
      if (mt == null) continue
      const delta = Math.abs(mt - target)
      if (delta <= KICKOFF_TOLERANCE_MS && delta < bestDelta) {
        best = m
        bestDelta = delta
      }
    }
    if (best) return best
  }

  const exact = pool.find((m) => m.team_a === fx.team_a && m.team_b === fx.team_b)
  if (exact) return exact

  if (!fx.team_a.startsWith('第') && !fx.team_b.startsWith('第')) {
    return byTeams.get(teamKey(fx.team_a, fx.team_b)) || null
  }

  if (!fx.team_a.startsWith('第')) {
    return pool.find(
      (m) => m.team_a === fx.team_a && (m.team_b === fx.team_b || m.team_b?.startsWith('第')),
    ) || null
  }
  if (!fx.team_b.startsWith('第')) {
    return pool.find(
      (m) => m.team_b === fx.team_b && (m.team_a === fx.team_a || m.team_a?.startsWith('第')),
    ) || null
  }
  return null
}

/** Vertical slot order (top → bottom) per wing / round */
export const BRACKET_LAYOUT = {
  left: {
    '1/16决赛': [74, 77, 73, 75, 83, 84, 81, 82],
    '1/8决赛': [89, 90, 93, 94],
    '1/4决赛': [97, 98],
    半决赛: [101],
  },
  right: {
    '1/16决赛': [76, 78, 79, 80, 85, 87, 88, 86],
    '1/8决赛': [91, 92, 96, 95],
    '1/4决赛': [99, 100],
    半决赛: [102],
  },
  center: { final: 104, third: 103 },
}

export const WING_ROUND_STAGES = ['1/16决赛', '1/8决赛', '1/4决赛', '半决赛']

function teamKey(a, b) {
  return [a, b].sort().join('|')
}

function dedupeMatches(rows) {
  const seen = new Map()
  for (const m of rows || []) {
    const key = `${m.stage}|${m.team_a}|${m.team_b}`
    const prev = seen.get(key)
    if (!prev || m.id > prev.id) seen.set(key, m)
  }
  return [...seen.values()]
}

/** Index loaded API rows for bracket slot lookup */
export function buildMatchIndex(stageRows) {
  const flat = dedupeMatches(Object.values(stageRows || {}).flat())
  const byTeams = new Map()
  for (const m of flat) {
    const k = teamKey(m.team_a, m.team_b)
    const prev = byTeams.get(k)
    if (!prev || m.id > prev.id) byTeams.set(k, m)
  }

  const byStageSlot = {}

  for (const side of ['left', 'right']) {
    for (const [stage, nos] of Object.entries(BRACKET_LAYOUT[side])) {
      if (!byStageSlot[stage]) byStageSlot[stage] = {}
      const pool = dedupeMatches(stageRows?.[stage] || [])

      for (const no of nos) {
        if (byStageSlot[stage][no]) continue
        const fx = FIXTURE_BY_NO[no]
        if (!fx) continue
        let hit = findRowForFixture(fx, pool, byTeams)
        if (!hit && !fx.team_a.startsWith('第') && !fx.team_b.startsWith('第')) {
          hit = byTeams.get(teamKey(fx.team_a, fx.team_b)) || null
        }
        byStageSlot[stage][no] = hit
      }
    }
  }

  for (const [stage, no] of [
    ['决赛', BRACKET_LAYOUT.center.final],
    ['季军赛', BRACKET_LAYOUT.center.third],
  ]) {
    if (!byStageSlot[stage]) byStageSlot[stage] = {}
    const pool = dedupeMatches(stageRows?.[stage] || [])
    byStageSlot[stage][no] = pool[0] || null
  }

  return { byTeams, byStageSlot, flat }
}

export function resolveBracketMatch(matchNo, index) {
  const fx = FIXTURE_BY_NO[matchNo]
  if (!fx) return null
  const hit = index.byStageSlot[fx.stage]?.[matchNo]
  const teams = resolveDisplayTeams(matchNo, index, hit)
  if (hit) {
    return { ...hit, team_a: teams.team_a, team_b: teams.team_b }
  }
  return {
    id: null,
    stage: fx.stage,
    team_a: teams.team_a,
    team_b: teams.team_b,
    result_a: undefined,
    result_b: undefined,
  }
}

export function chunkPairs(matchNos) {
  const groups = []
  for (let i = 0; i < matchNos.length; i += 2) {
    groups.push(matchNos.slice(i, i + 2))
  }
  return groups
}

const FEEDER_WIN = /^第(\d+)场胜者$/
const FEEDER_LOSE = /^第(\d+)场负者$/

function parseFeeder(name) {
  if (!name) return { kind: 'team' }
  let m = name.match(FEEDER_WIN)
  if (m) return { kind: 'winner', no: Number(m[1]) }
  m = name.match(FEEDER_LOSE)
  if (m) return { kind: 'loser', no: Number(m[1]) }
  return { kind: 'team', name }
}

function matchLoser(m) {
  const w = matchWinnerSide(m)
  if (!w || !m) return null
  return w === m.team_a ? m.team_b : m.team_a
}

function getSlotMatch(matchNo, index) {
  const fx = FIXTURE_BY_NO[matchNo]
  if (!fx) return null
  return index.byStageSlot[fx.stage]?.[matchNo] || null
}

function resolveFeederTeam(name, index, cache) {
  if (!name) return ''
  if (cache.has(name)) return cache.get(name) || ''
  const p = parseFeeder(name)
  if (p.kind === 'team') {
    const out = name.startsWith('第') ? '' : name
    cache.set(name, out)
    return out
  }
  const feeder = getSlotMatch(p.no, index)
  const out = p.kind === 'winner' ? (matchWinnerSide(feeder) || '') : (matchLoser(feeder) || '')
  cache.set(name, out)
  return out
}

function resolveDisplayTeams(matchNo, index, base) {
  const fx = FIXTURE_BY_NO[matchNo]
  if (!fx) {
    return {
      team_a: base?.team_a?.startsWith('第') ? '' : (base?.team_a || ''),
      team_b: base?.team_b?.startsWith('第') ? '' : (base?.team_b || ''),
    }
  }
  const cache = new Map()
  const fromFixture = (slot, dbVal) => {
    const seed = fx[slot]
    if (seed?.startsWith('第')) return resolveFeederTeam(seed, index, cache)
    return seed || dbVal || ''
  }
  return {
    team_a: fromFixture('team_a', base?.team_a),
    team_b: fromFixture('team_b', base?.team_b),
  }
}
