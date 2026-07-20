export function deepMerge(target, source) {
  const out = { ...target }
  for (const key of Object.keys(source || {})) {
    const val = source[key]
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      out[key] = deepMerge(out[key] || {}, val)
    } else {
      out[key] = val
    }
  }
  return out
}
