const { app, BrowserWindow, screen, Tray, Menu, nativeImage } = require('electron')
const path = require('path')
const fs   = require('fs')

let win, tray

const cfgPath = () => path.join(app.getPath('userData'), 'ltn-config.json')
function loadCfg()  { try { return JSON.parse(fs.readFileSync(cfgPath(),'utf8')) } catch { return {} } }
function saveCfg(o) { try { fs.writeFileSync(cfgPath(), JSON.stringify(o)) } catch {} }

function assertOnTop() {
  if (!win || win.isDestroyed()) return
  win.setAlwaysOnTop(true, 'screen-saver', 1000)
  win.moveTop()
}

function portraitBounds(d) {
  const pw = Math.min(d.bounds.width, d.bounds.height)
  const ph = Math.max(d.bounds.width, d.bounds.height)
  return {
    x: d.bounds.x + Math.floor((d.bounds.width  - pw) / 2),
    y: d.bounds.y + Math.floor((d.bounds.height - ph) / 2),
    width: pw, height: ph
  }
}

function positionOnDisplay(idx) {
  const displays = screen.getAllDisplays()
  const d = displays[Math.min(idx, displays.length - 1)]
  win.setBounds(portraitBounds(d))
  saveCfg({ displayIndex: idx })
  assertOnTop()
  buildTrayMenu()
}

function buildTrayMenu() {
  const displays = screen.getAllDisplays()
  const { displayIndex = 0 } = loadCfg()
  const cur = Math.min(displayIndex, displays.length - 1)

  const items = displays.map((d, i) => ({
    label: `Display ${i + 1}  (${d.bounds.width}×${d.bounds.height})${i === cur ? '  ✓' : ''}`,
    click: () => positionOnDisplay(i)
  }))

  items.push({ type: 'separator' })
  items.push({ label: 'Bring to Front', click: () => assertOnTop() })
  items.push({ type: 'separator' })
  items.push({ label: 'Quit LTN Overlay', click: () => app.quit() })

  tray.setContextMenu(Menu.buildFromTemplate(items))
  tray.setToolTip(`LTN Overlay — Display ${cur + 1}`)
}

function createTray() {
  const icon = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
  )
  tray = new Tray(icon)
  tray.setTitle('🎮')
  buildTrayMenu()
}

function createWindow() {
  const { displayIndex = 0 } = loadCfg()
  const displays = screen.getAllDisplays()
  const d = displays[Math.min(displayIndex, displays.length - 1)]
  const { x, y, width, height } = portraitBounds(d)

  win = new BrowserWindow({
    x, y, width, height,
    transparent: true,
    frame: false,
    hasShadow: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    webPreferences: { backgroundThrottling: false }
  })

  win.setAlwaysOnTop(true, 'screen-saver', 1000)
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  win.setIgnoreMouseEvents(true)
  win.loadFile(path.join(__dirname, 'gameover.html'))

  setInterval(assertOnTop, 2000)
}

app.whenReady().then(() => {
  app.dock && app.dock.show()
  createTray()
  createWindow()
})

app.on('window-all-closed', () => app.quit())
