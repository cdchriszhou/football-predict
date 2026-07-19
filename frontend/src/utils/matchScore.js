/** Regulation + final (AET) + penalty shootout display helpers */

import { hasMatchScore } from '@/utils/matchStatus'

export function hasPenaltyScore(match) {
  return match?.penalty_a != null && match?.penalty_b != null
}

export function hasRegulationOverlay(match) {
  return (
    !!match?.extra_time
    && match?.regulation_a != null
    && match?.regulation_b != null
  )
}

/** Final score line (includes extra-time goals when played). */
export function formatFinalScore(match) {
  if (!hasMatchScore(match)) return null
  return `${match.result_a} - ${match.result_b}`
}

/** 90-minute regulation score when distinct from the final AET score. */
export function formatNinetyScore(match) {
  if (!hasRegulationOverlay(match)) return null
  return `${match.regulation_a} - ${match.regulation_b}`
}

/** @deprecated use formatFinalScore — kept for call sites expecting "regulation" as main line */
export function formatRegulationScore(match) {
  return formatFinalScore(match)
}

/** Penalty shootout line, e.g. "4 - 5" */
export function formatPenaltyScore(match) {
  if (!hasPenaltyScore(match)) return null
  return `${match.penalty_a} - ${match.penalty_b}`
}

/**
 * Score lines for cards / detail / bracket.
 * - final: full-time including ET
 * - regulation: 90-min score when ET was played
 * - penalty: shootout when present
 */
export function formatMatchScoreLines(match) {
  const final = formatFinalScore(match)
  if (!final) {
    return { regulation: null, final: null, ninety: null, penalty: null, extraTime: false }
  }
  return {
    // Back-compat: "regulation" previously meant the main displayed score (final).
    regulation: final,
    final,
    ninety: formatNinetyScore(match),
    penalty: formatPenaltyScore(match),
    extraTime: !!match.extra_time,
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
