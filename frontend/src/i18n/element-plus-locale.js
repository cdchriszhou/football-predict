import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import zhTw from 'element-plus/dist/locale/zh-tw.mjs'
import en from 'element-plus/dist/locale/en.mjs'
import ja from 'element-plus/dist/locale/ja.mjs'
import ru from 'element-plus/dist/locale/ru.mjs'
import ar from 'element-plus/dist/locale/ar.mjs'

const MAP = {
  'zh-CN': zhCn,
  'zh-TW': zhTw,
  en,
  ja,
  ru,
  ar
}

export function getElementPlusLocale(locale) {
  return MAP[locale] || zhCn
}
