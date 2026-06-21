/** Whether sporttery block has on-sale SPF, handicap, or CRS odds. */
function sportteryHasContent(st) {
  if (!st) return false
  if (st.win_win) return true
  if (st.handicap_win || st.handicap_draw || st.handicap_lose) return true
  const scores = st.score_odds
  return !!(scores && Object.keys(scores).length)
}

/** True when odds come from sporttery.cn official API (on sale). */
export function isSportteryOfficial(source) {
  if (!source) return false
  return source === 'sporttery.cn' || String(source).includes('sporttery')
}

/** Whether sporttery block or legacy source has on-sale odds. */
export function hasSportteryOdds(odds) {
  if (!odds) return false
  if (sportteryHasContent(odds.sporttery)) return true
  return !!(odds.win_win && isSportteryOfficial(odds.source))
}

/** View model for sporttery tab / match card (market fields stay separate). */
export function resolveSportteryView(odds) {
  if (!odds) return null
  if (sportteryHasContent(odds.sporttery)) {
    return {
      ...odds.sporttery,
      sporttery_meta: odds.sporttery?.sporttery_meta || odds.sporttery_meta,
      update_time: odds.sporttery?.update_time || odds.update_time,
      source: 'sporttery.cn',
    }
  }
  if (odds.win_win && isSportteryOfficial(odds.source)) {
    return odds
  }
  return null
}
