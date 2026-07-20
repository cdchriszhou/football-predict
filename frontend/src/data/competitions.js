/** Static competition metadata — used when API is unavailable. */
export const FALLBACK_COMPETITIONS = [
  {
    slug: 'worldcup-2026',
    name_key: 'worldcup2026',
    short_name: '2026世界杯',
    type: 'international',
    theme_color: '#1a237e',
    timezone: 'America/New_York',
    timezone_label_key: 'usa',
    opening_date: '2026-06-11T20:00:00Z',
    closing_date: '2026-07-19T22:00:00Z',
    stats: { matches: 0, teams: 0, upcoming: 0 },
  },
  {
    slug: 'premier-league',
    name_key: 'premierLeague',
    short_name: '英超',
    type: 'club',
    theme_color: '#38003c',
    timezone: 'Europe/London',
    timezone_label_key: 'uk',
    opening_date: '2025-08-15T00:00:00Z',
    closing_date: '2026-05-24T23:59:59Z',
    stats: { matches: 0, teams: 0, upcoming: 0 },
  },
  {
    slug: 'la-liga',
    name_key: 'laLiga',
    short_name: '西甲',
    type: 'club',
    theme_color: '#ee8707',
    timezone: 'Europe/Madrid',
    timezone_label_key: 'spain',
    opening_date: '2025-08-15T00:00:00Z',
    closing_date: '2026-05-24T23:59:59Z',
    stats: { matches: 0, teams: 0, upcoming: 0 },
  },
  {
    slug: 'serie-a',
    name_key: 'serieA',
    short_name: '意甲',
    type: 'club',
    theme_color: '#008fd7',
    timezone: 'Europe/Rome',
    timezone_label_key: 'italy',
    opening_date: '2025-08-23T00:00:00Z',
    closing_date: '2026-05-24T23:59:59Z',
    stats: { matches: 0, teams: 0, upcoming: 0 },
  },
  {
    slug: 'bundesliga',
    name_key: 'bundesliga',
    short_name: '德甲',
    type: 'club',
    theme_color: '#d20515',
    timezone: 'Europe/Berlin',
    timezone_label_key: 'germany',
    opening_date: '2025-08-22T00:00:00Z',
    closing_date: '2026-05-16T23:59:59Z',
    stats: { matches: 0, teams: 0, upcoming: 0 },
  },
  {
    slug: 'ligue-1',
    name_key: 'ligue1',
    short_name: '法甲',
    type: 'club',
    theme_color: '#091c3e',
    timezone: 'Europe/Paris',
    timezone_label_key: 'france',
    opening_date: '2025-08-15T00:00:00Z',
    closing_date: '2026-05-16T23:59:59Z',
    stats: { matches: 0, teams: 0, upcoming: 0 },
  },
  {
    slug: 'pailie',
    name_key: 'pailie',
    short_name: '数字彩',
    type: 'digital',
    theme_color: '#c62828',
    timezone: 'Asia/Shanghai',
    timezone_label_key: 'beijing',
    opening_date: '2004-01-01T00:00:00Z',
    closing_date: null,
    features: {
      bracket: false,
      tournament: false,
      sporttery: false,
      groups: false,
      digital_lottery: true,
      games: ['pl3', 'pl5', 'qxc', 'ssq', 'dlt'],
    },
    stats: { matches: 0, teams: 0, upcoming: 0 },
  },
]

export function resolveSeasonStatus(item) {
  if (item.season_status) return item.season_status
  const now = Date.now()
  if (item.opening_date && now < new Date(item.opening_date).getTime()) return 'upcoming'
  if (item.closing_date && now > new Date(item.closing_date).getTime()) return 'ended'
  const s = item.stats || {}
  if ((s.matches || 0) > 0) {
    if ((s.live || 0) > 0 || (s.upcoming || 0) > 0) return 'live'
    if ((s.finished || 0) >= s.matches) return 'ended'
  }
  return item.opening_date ? 'live' : 'upcoming'
}

export function normalizeCompetition(row) {
  return {
    ...row,
    stats: row.stats || { matches: 0, teams: 0, upcoming: 0 },
    season_status: resolveSeasonStatus(row),
  }
}

/** Resolve static metadata when detail API is slow or unavailable. */
export function findCompetitionMeta(slug, list = []) {
  if (!slug) return null
  const fromList = list.find((c) => c.slug === slug)
  if (fromList) return normalizeCompetition(fromList)
  const fallback = FALLBACK_COMPETITIONS.find((c) => c.slug === slug)
  return fallback ? normalizeCompetition(fallback) : null
}
