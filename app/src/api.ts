// Calls to the Floorhand server. The app holds no keys: the server does.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://127.0.0.1:8787'

export type Draft = { text: string; confident: boolean }
export type Ticket = {
  id: number
  name: string
  text: string
  drafts: Draft[]
  draft_mode: 'ai' | 'template' | null
  waiting_s: number
  product: { code: string; name: string; price_uah: number | null; stock: string } | null
}
export type Card =
  | { mode: 'pair'; code: string }
  | { mode: 'empty'; drafting: number }
  | { mode: 'card'; queue: number; ticket: Ticket }

export async function getCard(uid: string): Promise<Card> {
  const r = await fetch(`${BASE}/api/card?uid=${encodeURIComponent(uid)}`)
  if (!r.ok) throw new Error(`card ${r.status}`)
  return r.json()
}

async function post(path: string, body: unknown) {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${path} ${r.status}`)
  return r.json()
}

export const send = (uid: string, ticketId: number, draft: number) =>
  post('/api/send', { uid, ticket_id: ticketId, draft })

export const handoff = (uid: string, ticketId: number) => post('/api/handoff', { uid, ticket_id: ticketId })

export async function voice(uid: string, ticketId: number, pcm: Uint8Array): Promise<{ ok: boolean; said: string; drafts?: Draft[] }> {
  const r = await fetch(`${BASE}/api/voice?uid=${encodeURIComponent(uid)}&ticket_id=${ticketId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: new Blob([pcm as BlobPart]),
  })
  if (!r.ok) throw new Error(`voice ${r.status}`)
  return r.json()
}
