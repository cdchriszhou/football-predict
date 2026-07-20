/** Match score prediction: two likely scorelines + one upset. */
export const LIKELY_SCORE_LIMIT = 2

export function parseLikelyScores(prediction) {
  if (!prediction) return []
  const upset = parseUpsetScore(prediction)
  const raw = prediction.best_scores && Array.isArray(prediction.best_scores)
    ? prediction.best_scores
    : (prediction.best_score && prediction.best_score !== '?'
      ? [prediction.best_score]
      : [])
  const ordered = []
  for (const s of raw) {
    if (!s || s === '?' || s === upset || ordered.includes(s)) continue
    ordered.push(s)
    if (ordered.length >= LIKELY_SCORE_LIMIT) break
  }
  return ordered
}

export function parseUpsetScore(prediction) {
  const s = prediction?.upset_score
  return s && s !== '?' ? s : ''
}
