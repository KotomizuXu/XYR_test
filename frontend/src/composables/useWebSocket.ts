import { ref } from 'vue'

export function useWebSocket(url: string) {
  const connected = ref(false)
  const error = ref<string | null>(null)
  let ws: WebSocket | null = null
  let reconnectTimer: any = null

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return

    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      error.value = null
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    }

    ws.onclose = () => {
      connected.value = false
      reconnectTimer = setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      error.value = 'WebSocket connection failed'
    }
  }

  function send(data: any) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
    }
  }

  function close() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (ws) ws.close()
  }

  return { connected, error, connect, send, close, ws }
}
