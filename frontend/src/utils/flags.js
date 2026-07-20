// 48 qualified teams → ISO 3166-1 alpha-2 country codes for flag images
// Real 2026 FIFA World Cup participants (confirmed May 2026)
const TEAM_CODES = {
  // Group A
  '墨西哥': 'mx', '南非': 'za', '韩国': 'kr', '捷克': 'cz',
  // Group B
  '加拿大': 'ca', '波黑': 'ba', '卡塔尔': 'qa', '瑞士': 'ch',
  // Group C
  '巴西': 'br', '摩洛哥': 'ma', '海地': 'ht', '苏格兰': 'gb-sct',
  // Group D
  '美国': 'us', '巴拉圭': 'py', '澳大利亚': 'au', '土耳其': 'tr',
  // Group E
  '德国': 'de', '库拉索': 'cw', '科特迪瓦': 'ci', '厄瓜多尔': 'ec',
  // Group F
  '荷兰': 'nl', '日本': 'jp', '瑞典': 'se', '突尼斯': 'tn',
  // Group G
  '比利时': 'be', '埃及': 'eg', '伊朗': 'ir', '新西兰': 'nz',
  // Group H
  '西班牙': 'es', '佛得角': 'cv', '沙特阿拉伯': 'sa', '乌拉圭': 'uy',
  // Group I
  '法国': 'fr', '塞内加尔': 'sn', '伊拉克': 'iq', '挪威': 'no',
  // Group J
  '阿根廷': 'ar', '阿尔及利亚': 'dz', '奥地利': 'at', '约旦': 'jo',
  // Group K
  '葡萄牙': 'pt', '刚果(金)': 'cd', '乌兹别克斯坦': 'uz', '哥伦比亚': 'co',
  // Group L
  '英格兰': 'gb-eng', '克罗地亚': 'hr', '加纳': 'gh', '巴拿马': 'pa',
}

// Flag emoji fallback (renders natively, no HTTP request)
const EMOJI_FLAGS = {
  // Group A
  '墨西哥': '🇲🇽', '南非': '🇿🇦', '韩国': '🇰🇷', '捷克': '🇨🇿',
  // Group B
  '加拿大': '🇨🇦', '波黑': '🇧🇦', '卡塔尔': '🇶🇦', '瑞士': '🇨🇭',
  // Group C
  '巴西': '🇧🇷', '摩洛哥': '🇲🇦', '海地': '🇭🇹', '苏格兰': '🏴󠁧󠁢󠁳󠁣󠁴󠁿',
  // Group D
  '美国': '🇺🇸', '巴拉圭': '🇵🇾', '澳大利亚': '🇦🇺', '土耳其': '🇹🇷',
  // Group E
  '德国': '🇩🇪', '库拉索': '🇨🇼', '科特迪瓦': '🇨🇮', '厄瓜多尔': '🇪🇨',
  // Group F
  '荷兰': '🇳🇱', '日本': '🇯🇵', '瑞典': '🇸🇪', '突尼斯': '🇹🇳',
  // Group G
  '比利时': '🇧🇪', '埃及': '🇪🇬', '伊朗': '🇮🇷', '新西兰': '🇳🇿',
  // Group H
  '西班牙': '🇪🇸', '佛得角': '🇨🇻', '沙特阿拉伯': '🇸🇦', '乌拉圭': '🇺🇾',
  // Group I
  '法国': '🇫🇷', '塞内加尔': '🇸🇳', '伊拉克': '🇮🇶', '挪威': '🇳🇴',
  // Group J
  '阿根廷': '🇦🇷', '阿尔及利亚': '🇩🇿', '奥地利': '🇦🇹', '约旦': '🇯🇴',
  // Group K
  '葡萄牙': '🇵🇹', '刚果(金)': '🇨🇩', '乌兹别克斯坦': '🇺🇿', '哥伦比亚': '🇨🇴',
  // Group L
  '英格兰': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', '克罗地亚': '🇭🇷', '加纳': '🇬🇭', '巴拿马': '🇵🇦',
}

/**
 * Get flag image URL from flagcdn.com (SVG — resolution-independent)
 * @param {string} teamName - Chinese team name
 * @param {number} size - unused (kept for backward compatibility)
 * @returns {string} flag SVG URL
 */
export function flagUrl(teamName, size = 80) {
  const code = TEAM_CODES[teamName]
  if (!code) return ''
  return `https://flagcdn.com/${code}.svg`
}

/**
 * Get flag emoji for a team
 * @param {string} teamName
 * @returns {string} emoji or empty string
 */
export function flagEmoji(teamName) {
  return EMOJI_FLAGS[teamName] || ''
}

/**
 * Get country code for a team
 * @param {string} teamName
 * @returns {string} ISO code or ''
 */
export function countryCode(teamName) {
  return TEAM_CODES[teamName] || ''
}
