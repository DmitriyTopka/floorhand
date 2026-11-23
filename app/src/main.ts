// Floorhand glasses app: one customer question, one reply, one tap.
import {
  waitForEvenAppBridge,
  TextContainerProperty,
  CreateStartUpPageContainer,
  TextContainerUpgrade,
  OsEventTypeList,
} from '@evenrealities/even_hub_sdk'
import { getCard, send, handoff, voice, type Card } from './api'
import { render, type Blocks } from './screens'

const mirror = document.createElement('pre')
mirror.style.cssText = 'font: 15px/1.4 monospace; background:#000; color:#3f3; padding:12px; white-space:pre-wrap'
document.querySelector('#app')!.appendChild(mirror)

const bridge = await waitForEvenAppBridge()

const LAYOUT: [keyof Blocks, number, number, number][] = [
  // name, id, y, height
  ['head', 1, 0, 40],
  ['question', 2, 40, 76],
  ['draft', 3, 116, 136],
  ['foot', 4, 252, 36],
]
await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({
    containerTotalNum: LAYOUT.length,
    textObject: LAYOUT.map(
      ([name, id, y, h]) =>
        new TextContainerProperty({
          xPosition: 0,
          yPosition: y,
          width: 576,
          height: h,
          borderWidth: name === 'draft' ? 1 : 0,
          borderColor: 8,
          paddingLength: 4,
          containerID: id,
          containerName: name,
          content: ' ',
          isEventCapture: name === 'draft' ? 1 : 0,
        }),
    ),
  }),
)

let uid = ''
let card: Card | null = null
let draftIndex = 0
let status: string | null = null
let shownTicket = -1
const shown: Partial<Blocks> = {}

async function paint() {
  const blocks = render(card, draftIndex, status, uid !== '')
  mirror.textContent = `${blocks.head}\n\n${blocks.question}\n\n${blocks.draft}\n\n${blocks.foot}`
  for (const [name, id] of LAYOUT) {
    if (shown[name] === blocks[name]) continue
    shown[name] = blocks[name]
    await bridge.textContainerUpgrade(
      new TextContainerUpgrade({ containerID: id, containerName: name, content: blocks[name] || ' ' }),
    )
  }
}

function flash(text: string, ms = 1500) {
  status = text
  paint()
  window.setTimeout(() => {
    if (status === text) {
      status = null
      paint()
    }
  }, ms)
}

async function refresh() {
  try {
    card = await getCard(uid)
    if (card.mode === 'card' && card.ticket.id !== shownTicket) {
      shownTicket = card.ticket.id
      draftIndex = 0
    }
  } catch {
    status = 'Server not reachable'
  }
  paint()
}

// Push-to-talk: hold to record a short instruction, release to rewrite the drafts.
let recording = false
let chunks: Uint8Array[] = []

async function startVoice() {
  if (card?.mode !== 'card' || recording) return
  recording = true
  chunks = []
  status = 'Listening... release to apply'
  paint()
  await bridge.audioControl(true)
}

async function stopVoice() {
  if (!recording || card?.mode !== 'card') return
  recording = false
  await bridge.audioControl(false)
  const size = chunks.reduce((n, c) => n + c.length, 0)
  const pcm = new Uint8Array(size)
  let o = 0
  for (const c of chunks) {
    pcm.set(c, o)
    o += c.length
  }
  status = 'Rewriting...'
  paint()
  try {
    const res = await voice(uid, card.ticket.id, pcm)
    if (res.ok && res.drafts) {
      card.ticket.drafts = res.drafts
      draftIndex = 0
      flash(`Heard: "${res.said}"`, 2500)
    } else {
      flash('Did not catch that')
    }
  } catch {
    flash('Voice edit failed')
  }
}

async function tap() {
  if (card?.mode !== 'card') return
  const t = card.ticket
  const d = t.drafts[draftIndex]
  try {
    if (d.confident) {
      await send(uid, t.id, draftIndex)
      flash('Sent')
    } else {
      await handoff(uid, t.id)
      flash('Handed off to a person')
    }
  } catch {
    flash('Could not send, try again')
  }
  refresh()
}

function typeOf(envelope?: { eventType?: OsEventTypeList }): OsEventTypeList | null {
  if (!envelope) return null
  return envelope.eventType ?? OsEventTypeList.CLICK_EVENT
}

bridge.onEvenHubEvent(event => {
  const pcm = event.audioEvent?.audioPcm
  if (pcm && recording) chunks.push(new Uint8Array(pcm))
  const type = typeOf(event.sysEvent) ?? typeOf(event.textEvent)
  if (type === null) return
  switch (type) {
    case OsEventTypeList.DOUBLE_CLICK_EVENT:
      bridge.shutDownPageContainer(1)
      return
    case OsEventTypeList.CLICK_EVENT:
      tap()
      return
    case OsEventTypeList.SCROLL_BOTTOM_EVENT:
    case OsEventTypeList.SCROLL_TOP_EVENT:
      if (card?.mode === 'card') {
        const n = card.ticket.drafts.length
        draftIndex = (draftIndex + (type === OsEventTypeList.SCROLL_BOTTOM_EVENT ? 1 : n - 1)) % n
        paint()
      }
      return
    case OsEventTypeList.LONG_PRESS_EVENT:
      startVoice()
      return
    case OsEventTypeList.LONG_PRESS_RELEASE_EVENT:
      stopVoice()
      return
  }
})

// The device key is a random 128-bit secret made on first run and kept on the
// phone. It identifies these glasses to the shop server; the Even uid is not
// used because it is guessable.
function deviceKey(): string {
  const KEY = 'floorhand.device'
  try {
    const saved = localStorage.getItem(KEY)
    if (saved && /^[A-Za-z0-9_-]{22,64}$/.test(saved)) return saved
  } catch {}
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  const key = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  try {
    localStorage.setItem(KEY, key)
  } catch {}
  return key
}
uid = deviceKey()
await refresh()
window.setInterval(refresh, 2000)
