import { createParser } from 'eventsource-parser'
import type { AppDispatch } from '../store'
import {
  appendToken, commitStream, clarifyRequested, setConversationId,
} from '../store/chatSlice'
import { applyAgentPatch, addFlag, setFiled } from '../store/formDraftSlice'
import {
  toolStarted, setSuggestions, setFilteredMaterials, setSampleRejection, streamFailed,
} from '../store/agentSlice'

export async function streamChat(
  dispatch: AppDispatch,
  message: string,
  conversationId: string | null,
): Promise<void> {

  let tokenBuf = ''
  let raf = 0
  const flush = () => {
    raf = 0
    if (tokenBuf) {
      dispatch(appendToken(tokenBuf))
      tokenBuf = ''
    }
  }
  const scheduleFlush = () => {
    if (!raf) raf = requestAnimationFrame(flush)
  }

  const parser = createParser({
    onEvent(ev) {
      const type = ev.event || 'message'
      let data: unknown = ev.data
      try { data = JSON.parse(ev.data) } catch {  }

      switch (type) {
        case 'token':
          tokenBuf += String(data)
          scheduleFlush()
          break
        case 'tool_call':
          dispatch(toolStarted(data as { name: string; status: string }))
          break
        case 'form_patch':
          dispatch(applyAgentPatch(data as Record<string, unknown>))
          break
        case 'compliance_flag':

          dispatch(addFlag(data as any))
          break
        case 'clarify':

          dispatch(clarifyRequested(data as any))
          break
        case 'suggestions':

          dispatch(setSuggestions(data as any))
          break
        case 'materials_filtered':

          dispatch(setFilteredMaterials(data as any))
          break
        case 'sample_rejected':
          dispatch(setSampleRejection(data as Record<string, unknown>))
          break
        case 'filed':
        case 'amended': {
          const d = data as { interaction_id: string; version: number; status: string }
          dispatch(setFiled({ interactionId: d.interaction_id, version: d.version, status: d.status }))
          break
        }
        case 'error':

          dispatch(streamFailed(data as any))
          break
        case 'done': {
          const d = data as { conversation_id?: string }
          if (d?.conversation_id) dispatch(setConversationId(d.conversation_id))
          break
        }
      }
    },
  })

  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  })
  if (!res.ok || !res.body) {
    dispatch(streamFailed({ code: 'http_error', message: `HTTP ${res.status}` }))
    dispatch(commitStream())
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      parser.feed(decoder.decode(value, { stream: true }))
    }
  } finally {
    if (raf) cancelAnimationFrame(raf)
    flush()
    reader.releaseLock()
    dispatch(commitStream())
  }
}

export async function fetchThreadState(tid: string) {
  const r = await fetch(`/api/threads/${tid}/state`)
  return r.ok ? r.json() : null
}

export function markFiled(dispatch: AppDispatch, interactionId: string, version: number, status: string) {
  dispatch(setFiled({ interactionId, version, status }))
}
