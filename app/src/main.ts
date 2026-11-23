// Floorhand, first hour of build week: a probe screen.
// Shows one line of text, mirrors every input event on the glasses and in the
// companion page, and checks that Latin and Cyrillic both render.
import {
  waitForEvenAppBridge,
  TextContainerProperty,
  CreateStartUpPageContainer,
  TextContainerUpgrade,
  OsEventTypeList,
} from '@evenrealities/even_hub_sdk'

const log = document.createElement('pre')
document.querySelector('#app')!.appendChild(log)
function note(line: string) {
  log.textContent = `${new Date().toISOString().slice(11, 19)} ${line}\n` + (log.textContent ?? '')
}

const bridge = await waitForEvenAppBridge()

const screen = new TextContainerProperty({
  xPosition: 0,
  yPosition: 0,
  width: 576,
  height: 288,
  borderWidth: 0,
  borderColor: 5,
  paddingLength: 4,
  containerID: 1,
  containerName: 'main',
  content: 'Hello Floorhand\nПривіт, ТехноТочка\nTap, swipe or hold',
  isEventCapture: 1,
})

const created = await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({ containerTotalNum: 1, textObject: [screen] }),
)
note(`createStartUpPageContainer -> ${created}`)

// Tap arrives with eventType undefined (protobuf drops zero), so resolve the
// default inside the envelope check, as the official template does.
function typeOf(envelope?: { eventType?: OsEventTypeList }): OsEventTypeList | null {
  if (!envelope) return null
  return envelope.eventType ?? OsEventTypeList.CLICK_EVENT
}

let count = 0
bridge.onEvenHubEvent(async event => {
  const type = typeOf(event.sysEvent) ?? typeOf(event.textEvent)
  if (type === null) return
  const name = OsEventTypeList[type] ?? String(type)
  note(name)
  if (type === OsEventTypeList.DOUBLE_CLICK_EVENT) {
    bridge.shutDownPageContainer(1)
    return
  }
  count += 1
  await bridge.textContainerUpgrade(
    new TextContainerUpgrade({
      containerID: 1,
      containerName: 'main',
      content: `Hello Floorhand\nПривіт, ТехноТочка\nEvent ${count}: ${name}`,
    }),
  )
})
