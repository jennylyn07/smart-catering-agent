/**
 * Smart Catering – static + proxy server
 * Serves build/ and proxies /api/ to FastAPI on port 8001.
 * Zero external dependencies – uses only Node built-ins.
 * Usage: node server.js
 */
const http = require('http');
const fs   = require('fs');
const path = require('path');

const PORT      = process.env.PORT || 3001;
const BUILD_DIR = path.join(__dirname, 'build');
const API_HOST  = '127.0.0.1';
const API_PORT  = 8001;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'text/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.txt':  'text/plain',
  '.webp': 'image/webp',
};

function proxyRequest(req, res) {
  const options = {
    hostname: API_HOST,
    port:     API_PORT,
    path:     req.url,
    method:   req.method,
    headers:  { ...req.headers, host: `${API_HOST}:${API_PORT}` },
  };
  const proxyReq = http.request(options, proxyRes => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });
  proxyReq.on('error', err => {
    console.error('[proxy error]', err.message);
    res.writeHead(502, { 'Content-Type': 'text/plain' });
    res.end(`Backend unreachable: ${err.message}`);
  });
  req.pipe(proxyReq, { end: true });
}

function serveStatic(req, res) {
  const pathname = req.url.split('?')[0];
  let filePath = path.join(BUILD_DIR, pathname);
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(BUILD_DIR, 'index.html');
  }
  const ext      = path.extname(filePath).toLowerCase();
  const mimeType = MIME[ext] || 'application/octet-stream';
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found'); return; }
    res.writeHead(200, { 'Content-Type': mimeType });
    res.end(data);
  });
}

const server = http.createServer((req, res) => {
  if (req.url.startsWith('/api/')) {
    proxyRequest(req, res);
  } else {
    serveStatic(req, res);
  }
});

server.listen(PORT, () => {
  console.log(`\n✅  Smart Catering running at http://localhost:${PORT}`);
  console.log(`    Static : ${BUILD_DIR}`);
  console.log(`    API    : http://${API_HOST}:${API_PORT}\n`);
});
