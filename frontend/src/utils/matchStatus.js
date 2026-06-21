/** Match status for display — aligns with backend resolve_public_match_status (Beijing kickoff). */

const FINISHED_ALIASES = new Set(['finished', '已结束'])
const LIVE_ALIASES = new Set(['live', '进行中'])
const UPCOMING_ALIASES = new Set(['upcoming', '未开始'])
const FINISH_BUFFER_MS = (2 * 60 + 45) * 60 * 1000

function normalizeStatus(status) {
  if (!status) return 'upcoming'
  if (FINISHED_ALIASES.has(status)) return 'finished'
  if (LIVE_ALIASES.has(status)) return 'live'
  if (UPCOMING_ALIASES.has(status)) return 'upcoming'
  return status
}

function kickoffMs(match) {
  if (!match?.match_time) return null
  const ms = new Date(match.match_time).getTime()
  return Number.isFinite(ms) ? ms : null
}

export function hasMatchScore(match) {
  return match?.result_a != null && match?.result_b != null
}

export function effectiveMatchStatus(match) {
  if (!match) return 'upcoming'
  const raw = normalizeStatus(match.status)
  if (raw === 'live') return 'live'
  if (hasMatchScore(match)) return 'finished'
  if (raw === 'finished') return 'finished'
  const start = kickoffMs(match)
  if (start != null) {
    const now = Date.now()
    if (now >= start + FINISH_BUFFER_MS) return 'finished'
    if (now >= start) return 'live'
  }
  return raw
}

export function isEffectiveMatchStatus(match, kind) {
  return effectiveMatchStatus(match) === kind
}
