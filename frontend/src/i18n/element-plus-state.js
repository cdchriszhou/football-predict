import { ref } from 'vue'
import { getElementPlusLocale } from './element-plus-locale'
import { getAppLocale } from './index'

export const elementPlusLocale = ref(getElementPlusLocale(getAppLocale()))
