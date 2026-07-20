import { createI18n } from 'vue-i18n'
import { deepMerge } from './merge'
import { playerLocaleExtras } from './locales/playerLocale'
import zhCNBase from './locales/zh-CN'
import zhTWBase from './locales/zh-TW'
import enBase from './locales/en'
import jaBase from './locales/ja'
import ruBase from './locales/ru'
import arBase from './locales/ar'
import zhCNExt from './locales/extended/zh-CN'
import zhTWExt from './locales/extended/zh-TW'
import enExt from './locales/extended/en'
import jaExt from './locales/extended/ja'
import ruExt from './locales/extended/ru'
import arExt from './locales/extended/ar'

export const LOCALE_STORAGE_KEY = 'worldcup_locale'

export const SUPPORTED_LOCALES = [
  { value: 'zh-CN', labelKey: 'language.zh-CN' },
  { value: 'zh-TW', labelKey: 'language.zh-TW' },
  { value: 'en', labelKey: 'language.en' },
  { value: 'ja', labelKey: 'language.ja' },
  { value: 'ru', labelKey: 'language.ru' },
  { value: 'ar', labelKey: 'language.ar' }
]

export const RTL_LOCALES = new Set(['ar'])

function detectInitialLocale() {
  const saved = localStorage.getItem(LOCALE_STORAGE_KEY)
  if (saved && SUPPORTED_LOCALES.some(l => l.value === saved)) return saved
  const browser = (navigator.language || 'zh-CN').toLowerCase()
  if (browser.startsWith('zh-tw') || browser.startsWith('zh-hk')) return 'zh-TW'
  if (browser.startsWith('zh')) return 'zh-CN'
  if (browser.startsWith('ja')) return 'ja'
  if (browser.startsWith('ru')) return 'ru'
  if (browser.startsWith('ar')) return 'ar'
  if (browser.startsWith('en')) return 'en'
  return 'zh-CN'
}

export function applyDocumentLocale(locale) {
  document.documentElement.lang = locale
  document.documentElement.dir = RTL_LOCALES.has(locale) ? 'rtl' : 'ltr'
}

const initialLocale = detectInitialLocale()
applyDocumentLocale(initialLocale)

const i18n = createI18n({
  legacy: false,
  locale: initialLocale,
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': deepMerge(deepMerge(zhCNBase, zhCNExt), playerLocaleExtras('zh-CN')),
    'zh-TW': deepMerge(deepMerge(zhTWBase, zhTWExt), playerLocaleExtras('zh-TW')),
    en: deepMerge(deepMerge(enBase, enExt), playerLocaleExtras('en')),
    ja: deepMerge(deepMerge(jaBase, jaExt), playerLocaleExtras('ja')),
    ru: deepMerge(deepMerge(ruBase, ruExt), playerLocaleExtras('ru')),
    ar: deepMerge(deepMerge(arBase, arExt), playerLocaleExtras('ar')),
  }
})

export default i18n

export function setAppLocale(locale) {
  if (!SUPPORTED_LOCALES.some(l => l.value === locale)) return
  i18n.global.locale.value = locale
  localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  applyDocumentLocale(locale)
}

export function getAppLocale() {
  return i18n.global.locale.value
}
