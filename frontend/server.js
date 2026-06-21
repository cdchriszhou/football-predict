import { readFile, stat } from 'node:fs/promises'
import { createServer, request } from 'node:http'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const DIST = join(__dirname, 'dist')
const API_TARGET = process.env.BACKEND_URL || process.env.API_TARGET || 'http://127.0.0.1:8888'
const PORT = parseInt(process.env.PORT || '4173', 10)

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.svg':  'image/svg+xml',
  '.png':  'image/png',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
}

const CACHE_LONG  = 'public, max-age=31536000, immutable'
const CACHE_SHORT = 'no-cache'

function log(msg) {
  const ts = new Date().toISOString().slice(11, 19)
  process.stdout.write(`[${ts}] ${msg}\n`)
}

createServer(async (req, res) => {
  if (req.url === '/health') {
    res.writeHead(200).end('ok')
    return
  }

  // API proxy -> backend
  if (req.url.startsWith('/api/')) {
    const { hostname, port, pathname, search } = new URL(req.url, API_TARGET)
    const proxyPath = pathname + (search || '')
    const opts = {
      hostname, port, path: proxyPath,
      method: req.method,
      headers: { ...req.headers, host: hostname + ':' + port },
    }

    log(`${req.method} ${req.url} -> ${API_TARGET}${proxyPath}`)

    const proxy = request(opts, (proxyRes) => {
      log(`  <- ${proxyRes.statusCode} (${req.url})`)
      res.writeHead(proxyRes.statusCode, proxyRes.headers)
      proxyRes.pipe(res)
    })
    proxy.on('error', (err) => {
      log(`  !! PROXY ERROR: ${err.message}`)
      res.writeHead(502, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ message: 'Backend API unavailable', error: err.message }))
    })
    req.pipe(proxy)
    return
  }

  // SPA routing: non-file requests -> index.html
  let file = req.url.split('?')[0]
  if (file === '/') file = '/index.html'
  let ext = extname(file)
  if (!ext || ext === '') {
    file = '/index.html'
    ext = '.html'
  }

  const filePath = join(DIST, file)
  const gzPath = filePath + '.gz'

  try {
    let useGzip = ext !== '.png' && ext !== '.svg'
    let servePath = useGzip ? gzPath : filePath
    let [fileData, fileStat] = await Promise.all([
      readFile(servePath).catch(() => null),
      stat(servePath).catch(() => null)
    ])

    // Fallback to non-gzip if .gz not available
    if ((!fileData || !fileStat) && useGzip) {
      servePath = filePath
      useGzip = false
      ;[fileData, fileStat] = await Promise.all([
        readFile(servePath).catch(() => null),
        stat(servePath).catch(() => null)
      ])
    }

    if (!fileData || !fileStat) {
      res.writeHead(404).end('Not Found')
      return
    }

    const isHtml = ext === '.html'
    const cache = isHtml ? CACHE_SHORT : CACHE_LONG

    const headers = {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': cache,
      'Access-Control-Allow-Origin': '*',
    }

    if (useGzip && ext !== '.png') {
      headers['Content-Encoding'] = 'gzip'
      headers['Vary'] = 'Accept-Encoding'
    }

    res.writeHead(200, headers)
    res.end(fileData)
  } catch {
    try {
      const html = await readFile(join(DIST, 'index.html.gz'))
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Content-Encoding': 'gzip',
        'Cache-Control': CACHE_SHORT,
      })
      res.end(html)
    } catch {
      res.writeHead(404).end('Not Found')
    }
  }
}).listen(PORT, '0.0.0.0', () => {
  console.log(`Production server: http://0.0.0.0:${PORT}  (API proxy -> ${API_TARGET})`)
  console.log(`Serving static files from: ${DIST}`)
})
