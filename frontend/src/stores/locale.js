import { defineStore } from 'pinia'
import { getElementPlusLocale } from '@/i18n/element-plus-locale'
import { getAppLocale } from '@/i18n'

let elementPlusLocaleRef = null

export const useLocaleStore = defineStore('locale', {
  state: () => ({
    locale: getAppLocale()
  }),

  actions: {
    bindElementPlusLocale(ref) {
      elementPlusLocaleRef = ref
      this.applyElementPlusLocale(getAppLocale())
    },

    applyElementPlusLocale(locale) {
      this.locale = locale
      if (elementPlusLocaleRef) {
        elementPlusLocaleRef.value = getElementPlusLocale(locale)
      }
    }
  }
})
