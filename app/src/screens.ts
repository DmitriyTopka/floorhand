// What the glasses show. Pure functions: state in, four text blocks out.
import type { Card } from './api'

export type Blocks = { head: string; question: string; draft: string; foot: string }

const LINE = 44 // rough characters per line at the firmware font

function clip(text: string, lines: number): string {
  const max = LINE * lines
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length <= max ? flat : flat.slice(0, max - 1).trimEnd() + '…'
}

function ago(s: number): string {
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m`
}

export function render(card: Card | null, draftIndex: number, status: string | null, uidReady: boolean): Blocks {
  if (!uidReady || !card) {
    return { head: 'Floorhand', question: 'Connecting to the shop…', draft: '', foot: status ?? '' }
  }
  if (card.mode === 'pair') {
    return {
      head: 'Floorhand · pair your glasses',
      question: 'In the shop bot on Telegram send:',
      draft: `/pair ${card.code}`,
      foot: 'double tap to exit',
    }
  }
  if (card.mode === 'empty') {
    return {
      head: 'Floorhand',
      question: card.drafting ? `Preparing ${card.drafting} answer(s)…` : 'No customers waiting.',
      draft: '',
      foot: status ?? 'double tap to exit',
    }
  }
  const t = card.ticket
  const i = Math.min(draftIndex, t.drafts.length - 1)
  const d = t.drafts[i]
  const head = `${t.name} · ${ago(t.waiting_s)} · ${card.queue} waiting`
  const src = t.product ? `from catalog ${t.product.code}` : 'no product match'
  const draftHead = `Reply ${i + 1}/${t.drafts.length}${d.confident ? '' : ' · NOT SURE'} · ${src}`
  const foot = status ?? (d.confident ? 'tap send · swipe next · hold to edit' : 'tap hand off · swipe next · hold to edit')
  return { head, question: clip(`"${t.text}"`, 2), draft: `${draftHead}\n${clip(d.text, 4)}`, foot }
}
