/** Regulation + penalty shootout display helpers */

import { hasMatchScore } from '@/utils/matchStatus'

export function hasPenaltyScore(match) {
  return match?.penalty_a != null && match?.penalty_b != null
}

/** Main line: regulation / extra-time score */
export function formatRegulationScore(match) {
  if (!hasMatchScore(match)) return null
  return `${match.result_a} - ${match.result_b}`
}

/** Penalty shootout line, e.g. "4 - 5" */
export function formatPenaltyScore(match) {
  if (!hasPenaltyScore(match)) return null
  return `${match.penalty_a} - ${match.penalty_b}`
}

export function formatMatchScoreLines(match) {
  const regulation = formatRegulationScore(match)
  if (!regulation) return { regulation: null, penalty: null }
  return {
    regulation,
    penalty: formatPenaltyScore(match),
  }
}

export function matchWinnerSide(match) {
  if (!hasMatchScore(match)) return null
  const { result_a: ra, result_b: rb, team_a: ta, team_b: tb } = match
  if (ra > rb) return ta
  if (rb > ra) return tb
  if (hasPenaltyScore(match)) {
    if (match.penalty_a > match.penalty_b) return ta
    if (match.penalty_b > match.penalty_a) return tb
  }
  return null
}

export function isMatchWinner(match, team) {
  if (!team) return false
  return matchWinnerSide(match) === team
}
