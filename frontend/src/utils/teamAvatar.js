import { flagUrl, flagEmoji } from './flags'
import { crestUrl, isClubTeam } from './crests'

/**
 * Resolve team avatar URL — national flag for World Cup, club crest for leagues.
 * @param {{ name?: string, flag_url?: string, isWorldCup?: boolean }} opts
 */
export function resolveTeamAvatarUrl({ name, flag_url, isWorldCup } = {}) {
  if (flag_url) return flag_url
  if (!isWorldCup && isClubTeam(name)) return crestUrl(name)
  return flagUrl(name)
}

export function isTeamCrest({ name, flag_url, isWorldCup } = {}) {
  if (isWorldCup) return false
  if (flag_url && flag_url.includes('crests.football-data.org')) return true
  return isClubTeam(name)
}

export function teamAvatarFallback(name, isWorldCup) {
  if (!isWorldCup && isClubTeam(name)) return '⚽'
  return flagEmoji(name) || '⚽'
}
