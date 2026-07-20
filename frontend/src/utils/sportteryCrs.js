/** Official 竞彩 CRS grid order (team_a home-win / draw / away-win columns). */
export const CRS_HOME_WIN_ORDER = [
  '1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2', '5:0', '5:1', '5:2',
]
export const CRS_DRAW_ORDER = ['0:0', '1:1', '2:2', '3:3']
export const CRS_AWAY_WIN_ORDER = [
  '0:1', '0:2', '1:2', '0:3', '1:3', '2:3', '0:4', '1:4', '2:4', '0:5', '1:5', '2:5',
]
export const CRS_OTHER_LABELS = ['胜其它', '平其它', '负其它']

/** Display sporttery odds with two decimals (e.g. 5.80). */
export function formatCrsOdds(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return '-'
  return n.toFixed(2)
}

export function buildCrsGrid(scoreOdds, teamA, teamB) {
  const map = scoreOdds || {}
  const pick = (order) =>
    order
      .filter((score) => map[score] != null && map[score] > 0)
      .map((score) => ({ score, odds: formatCrsOdds(map[score]) }))

  const others = CRS_OTHER_LABELS
    .filter((label) => map[label] != null && map[label] > 0)
    .map((label) => ({ score: label, odds: formatCrsOdds(map[label]) }))

  return {
    homeWin: pick(CRS_HOME_WIN_ORDER),
    draw: pick(CRS_DRAW_ORDER),
    awayWin: pick(CRS_AWAY_WIN_ORDER),
    others,
    homeLabel: teamA,
    awayLabel: teamB,
  }
}
