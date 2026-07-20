/** Canonical position codes stored for club leagues (GK/DF/MF/FW). */
const POSITION_CODES = {
  GK: 'GK', DF: 'DF', MF: 'MF', FW: 'FW',
  门将: 'GK', 后卫: 'DF', 中场: 'MF', 前锋: 'FW',
  Goalkeeper: 'GK', Defender: 'DF', Midfielder: 'MF', Forward: 'FW',
  goalkeeper: 'GK', defender: 'DF', midfielder: 'MF', forward: 'FW',
}

/** football-data.org / common API nationality → i18n key */
export const NATIONALITY_KEYS = {
  England: 'england',
  Scotland: 'scotland',
  Wales: 'wales',
  'Northern Ireland': 'northernIreland',
  Ireland: 'ireland',
  Italy: 'italy',
  Spain: 'spain',
  France: 'france',
  Germany: 'germany',
  Netherlands: 'netherlands',
  Belgium: 'belgium',
  Portugal: 'portugal',
  Brazil: 'brazil',
  Argentina: 'argentina',
  Uruguay: 'uruguay',
  Colombia: 'colombia',
  Mexico: 'mexico',
  'United States': 'usa',
  USA: 'usa',
  Canada: 'canada',
  Japan: 'japan',
  'Korea Republic': 'koreaRepublic',
  'South Korea': 'koreaRepublic',
  Australia: 'australia',
  Nigeria: 'nigeria',
  Ghana: 'ghana',
  Senegal: 'senegal',
  Morocco: 'morocco',
  Egypt: 'egypt',
  Algeria: 'algeria',
  Tunisia: 'tunisia',
  Cameroon: 'cameroon',
  "Côte d'Ivoire": 'ivoryCoast',
  'Ivory Coast': 'ivoryCoast',
  Norway: 'norway',
  Sweden: 'sweden',
  Denmark: 'denmark',
  Finland: 'finland',
  Iceland: 'iceland',
  Poland: 'poland',
  'Czech Republic': 'czechRepublic',
  Czechia: 'czechRepublic',
  Austria: 'austria',
  Switzerland: 'switzerland',
  Croatia: 'croatia',
  Serbia: 'serbia',
  Slovenia: 'slovenia',
  Slovakia: 'slovakia',
  Hungary: 'hungary',
  Romania: 'romania',
  Ukraine: 'ukraine',
  Russia: 'russia',
  Turkey: 'turkey',
  Greece: 'greece',
  Iran: 'iran',
  'Saudi Arabia': 'saudiArabia',
  Qatar: 'qatar',
  China: 'china',
  Chile: 'chile',
  Peru: 'peru',
  Ecuador: 'ecuador',
  Paraguay: 'paraguay',
  Venezuela: 'venezuela',
  Bolivia: 'bolivia',
  'Costa Rica': 'costaRica',
  Jamaica: 'jamaica',
  Mali: 'mali',
  Guinea: 'guinea',
  'DR Congo': 'drCongo',
  'Democratic Republic of the Congo': 'drCongo',
  Angola: 'angola',
  Zambia: 'zambia',
  Zimbabwe: 'zimbabwe',
  'South Africa': 'southAfrica',
  'New Zealand': 'newZealand',
  Israel: 'israel',
  Kosovo: 'kosovo',
  Albania: 'albania',
  'Bosnia and Herzegovina': 'bosnia',
  Montenegro: 'montenegro',
  'North Macedonia': 'northMacedonia',
  Georgia: 'georgia',
  Armenia: 'armenia',
  Azerbaijan: 'azerbaijan',
  Lithuania: 'lithuania',
  Latvia: 'latvia',
  Estonia: 'estonia',
  Luxembourg: 'luxembourg',
  Cyprus: 'cyprus',
  Malta: 'malta',
  // Chinese names (World Cup roster)
  英格兰: 'england',
  意大利: 'italy',
  西班牙: 'spain',
  法国: 'france',
  德国: 'germany',
  巴西: 'brazil',
  阿根廷: 'argentina',
  荷兰: 'netherlands',
  比利时: 'belgium',
  葡萄牙: 'portugal',
  日本: 'japan',
  韩国: 'koreaRepublic',
  美国: 'usa',
  墨西哥: 'mexico',
  克罗地亚: 'croatia',
  摩洛哥: 'morocco',
  塞内加尔: 'senegal',
  尼日利亚: 'nigeria',
  加纳: 'ghana',
  喀麦隆: 'cameroon',
  科特迪瓦: 'ivoryCoast',
  埃及: 'egypt',
  澳大利亚: 'australia',
  加拿大: 'canada',
  乌拉圭: 'uruguay',
  哥伦比亚: 'colombia',
  瑞士: 'switzerland',
  奥地利: 'austria',
  波兰: 'poland',
  丹麦: 'denmark',
  瑞典: 'sweden',
  挪威: 'norway',
  威尔士: 'wales',
  苏格兰: 'scotland',
}

function resolvePositionCode(position) {
  if (!position) return null
  if (POSITION_CODES[position]) return POSITION_CODES[position]
  const upper = position.toUpperCase?.() ? position.toUpperCase() : position
  if (POSITION_CODES[upper]) return POSITION_CODES[upper]
  return null
}

export function playerPositionLabel(t, position) {
  const code = resolvePositionCode(position)
  if (code) return t(`playerPosition.${code}`)
  return position || '—'
}

export function nationalityLabel(t, nationality) {
  if (!nationality) return '—'
  const key = NATIONALITY_KEYS[nationality]
  if (key) return t(`nationality.${key}`, nationality)
  return nationality
}

function hasCjk(text) {
  return /[\u4e00-\u9fff\u3400-\u4dbf]/.test(text || '')
}

/** Pick display name based on UI locale and stored name fields. */
export function playerDisplayName(player, locale) {
  const cn = (player?.name || '').trim()
  const en = (player?.name_en || player?.name || '').trim()
  const useChinese = locale === 'zh-CN' || locale === 'zh-TW'

  if (useChinese && cn && hasCjk(cn)) return cn
  if (locale === 'en') return en || cn
  if (locale === 'ja' || locale === 'ru' || locale === 'ar') return en || cn
  return en || cn
}

export function formatPlayerNumber(number) {
  if (number === null || number === undefined || number === '') return '—'
  return number
}

export function sortPlayers(players = []) {
  return [...players].sort((a, b) => {
    const na = a.number ?? 9999
    const nb = b.number ?? 9999
    if (na !== nb) return na - nb
    return (b.ability || 0) - (a.ability || 0)
  })
}
