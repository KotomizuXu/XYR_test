import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface OutputMessage {
  type: 'output'
  data: {
    kind: string
    [key: string]: any
  }
}

export interface InputRequest {
  type: 'input_request'
  request_id: string
  data: {
    kind: 'choice' | 'yes_no' | 'single' | 'multiline' | 'int'
    message: string
    [key: string]: any
  }
}

export interface SessionMessage {
  type: 'session_started' | 'session_ended'
  session_id: string
  reason?: string
  error?: string
}

export type ServerMessage = OutputMessage | InputRequest | SessionMessage

export const useNovelStore = defineStore('novel', () => {
  const novels = ref<any[]>([])
  const sessionId = ref<string | null>(null)
  const connected = ref(false)
  const messages = ref<ServerMessage[]>([])
  const pendingInput = ref<InputRequest | null>(null)
  const sessionEnded = ref(false)
  const sessionError = ref<string | null>(null)

  let ws: WebSocket | null = null

  const outputMessages = computed(() =>
    messages.value.filter((m): m is OutputMessage => m.type === 'output')
  )

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/ws`)

    ws.onopen = () => { connected.value = true }
    ws.onclose = () => { connected.value = false }
    ws.onerror = () => { connected.value = false }

    ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data)
      messages.value.push(msg)

      if (msg.type === 'session_started') {
        sessionId.value = msg.session_id
        sessionEnded.value = false
        sessionError.value = null
      } else if (msg.type === 'session_ended') {
        sessionEnded.value = true
        pendingInput.value = null
        if (msg.error) sessionError.value = msg.error
      } else if (msg.type === 'input_request') {
        pendingInput.value = msg
      } else if (msg.type === 'output' && msg.data.kind === 'progress') {
        // progress updates are handled by display components
      }
    }
  }

  function disconnect() {
    if (ws) { ws.close(); ws = null }
    connected.value = false
  }

  function send(msg: any) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg))
    }
  }

  function startMode(mode: string, params: any = {}) {
    messages.value = []
    pendingInput.value = null
    sessionEnded.value = false
    sessionError.value = null
    send({ type: 'start', mode, params })
  }

  function respondToInput(requestId: string, value: any) {
    send({ type: 'input_response', request_id: requestId, value })
    pendingInput.value = null
  }

  function cancel() {
    send({ type: 'cancel' })
  }

  async function fetchNovels() {
    try {
      const res = await fetch('/api/novels')
      const data = await res.json()
      novels.value = data.novels || []
    } catch { novels.value = [] }
  }

  return {
    novels, sessionId, connected, messages, pendingInput,
    sessionEnded, sessionError, outputMessages,
    connect, disconnect, startMode, respondToInput, cancel, fetchNovels,
  }
})
