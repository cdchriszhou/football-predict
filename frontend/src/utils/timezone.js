export const BEIJING_TZ = 'Asia/Shanghai'

export const COMPETITION_TIMEZONES = {
  'worldcup-2026': { timezone: 'America/New_York', labelKey: 'usa' },
  'premier-league': { timezone: 'Europe/London', labelKey: 'uk' },
  'la-liga': { timezone: 'Europe/Madrid', labelKey: 'spain' },
  'serie-a': { timezone: 'Europe/Rome', labelKey: 'italy' },
  'bundesliga': { timezone: 'Europe/Berlin', labelKey: 'germany' },
  'ligue-1': { timezone: 'Europe/Paris', labelKey: 'france' },
}

export const TIMEZONE_FLAGS = {
  uk: '🇬🇧',
  spain: '🇪🇸',
  italy: '🇮🇹',
  germany: '🇩🇪',
  france: '🇫🇷',
  usa: '🇺🇸',
  local: '🌍',
}

export function resolveActiveCompetition(compStore) {
  const cur = compStore.current
  if (cur?.slug === compStore.slug) return cur
  const fromList = compStore.list.find(c => c.slug === compStore.slug)
  return fromList || { slug: compStore.slug }
}

export function resolveCompetitionTimezone(item) {
  if (item?.timezone) {
    return {
      timezone: item.timezone,
      labelKey: item.timezone_label_key || 'local',
    }
  }
  return COMPETITION_TIMEZONES[item?.slug] || { timezone: 'UTC', labelKey: 'local' }
}

export function formatClock(timeZone, locale = 'zh-CN', now = new Date()) {
  const fmtLocale = locale === 'zh-TW' ? 'zh-TW' : locale === 'zh-CN' ? 'zh-CN' : 'en-US'
  const raw = new Intl.DateTimeFormat(fmtLocale, {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(now)
  return raw.replace(/\//g, '.').replace(/,/g, '')
}

export function formatDateTimeInTz(isoString, timeZone = BEIJING_TZ, locale = 'zh-CN') {
  if (!isoString) return ''
  let normalized = String(isoString)
  if (!/[zZ]|[+-]\d{2}:\d{2}$/.test(normalized)) {
    normalized = `${normalized}Z`
  }
  const d = new Date(normalized)
  if (Number.isNaN(d.getTime())) return String(isoString)
  const fmtLocale = locale === 'zh-TW' ? 'zh-TW' : locale === 'zh-CN' ? 'zh-CN' : 'en-US'
  return new Intl.DateTimeFormat(fmtLocale, {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(d).replace(/\//g, '-')
}
