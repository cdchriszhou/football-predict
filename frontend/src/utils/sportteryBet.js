/** 体彩参考注额与奖金测算（单注 2 元为常见起点） */
export const DEFAULT_STAKE_YUAN = 2

export function resolveStake(stake) {
  const s = Number(stake)
  return Number.isFinite(s) && s > 0 ? s : DEFAULT_STAKE_YUAN
}

/** Prefer API `bet` payload; otherwise compute from odds. */
export function betFromApiOrOdds(odds, apiBet, stake = DEFAULT_STAKE_YUAN) {
  const s = resolveStake(stake)
  if (apiBet && Number.isFinite(Number(apiBet.return_yuan))) {
    return {
      stake: Number(apiBet.stake_yuan ?? s),
      returnAmount: Number(apiBet.return_yuan),
      profit: Number(apiBet.profit_yuan ?? apiBet.return_yuan - (apiBet.stake_yuan ?? s)),
    }
  }
  return calcBetReturn(odds, s)
}

export function calcBetReturn(odds, stake = DEFAULT_STAKE_YUAN) {
  const o = Number(odds)
  const s = Number(stake)
  if (!Number.isFinite(o) || o <= 0 || !Number.isFinite(s) || s <= 0) {
    return { stake: s || 0, returnAmount: 0, profit: 0 }
  }
  const returnAmount = Math.round(o * s * 100) / 100
  const profit = Math.round((returnAmount - s) * 100) / 100
  return { stake: s, returnAmount, profit }
}

export function formatStakeYuan(amount) {
  const n = Number(amount)
  if (!Number.isFinite(n)) return '-'
  return `${formatNum(n)}元`
}

export function formatReturnYuan(amount) {
  const n = Number(amount)
  if (!Number.isFinite(n)) return '-'
  return `${formatNum(n)}元`
}

function formatNum(n) {
  if (n >= 1000) return n.toFixed(0)
  if (Number.isInteger(n)) return String(n)
  return n.toFixed(2).replace(/\.?0+$/, (m) => (m === '.00' ? '' : m.replace(/0+$/, '')))
}
