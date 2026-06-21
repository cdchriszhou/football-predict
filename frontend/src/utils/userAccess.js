export const ACCESS_DENIED_COMPETITION_MSG = '请购买访问该赛事的权益！ 199元/月'
export const ACCESS_DENIED_EXPIRED_MSG = '您的账户访问权限已过期，请联系管理员续期'

export function canAccessCompetition({
  isAdmin = false,
  accountExpired = false,
  accessExpiresAt = null,
  hasAllCompetitions = true,
  allowedCompetitions = null,
}, slug) {
  if (isAdmin) return true
  if (accountExpired) return false
  if (accessExpiresAt) {
    const exp = new Date(accessExpiresAt)
    if (!Number.isNaN(exp.getTime()) && Date.now() > exp.getTime()) {
      return false
    }
  }
  if (hasAllCompetitions || allowedCompetitions == null) return true
  return Array.isArray(allowedCompetitions) && allowedCompetitions.includes(slug)
}

export function accessDeniedMessage({
  isAdmin = false,
  accountExpired = false,
  accessExpiresAt = null,
}, slug) {
  if (isAdmin) return ''
  if (accountExpired) return ACCESS_DENIED_EXPIRED_MSG
  if (accessExpiresAt) {
    const exp = new Date(accessExpiresAt)
    if (!Number.isNaN(exp.getTime()) && Date.now() > exp.getTime()) {
      return ACCESS_DENIED_EXPIRED_MSG
    }
  }
  return ACCESS_DENIED_COMPETITION_MSG
}
