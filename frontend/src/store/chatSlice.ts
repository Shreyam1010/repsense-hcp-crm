import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface Clarify {
  field: string
  question: string
  options: { value: string; label: string }[]
}

interface ChatState {
  messages: ChatMessage[]
  streamingText: string
  streaming: boolean
  clarify: Clarify | null
  conversationId: string | null
}

const initialState: ChatState = {
  messages: [], streamingText: '', streaming: false, clarify: null, conversationId: null,
}

const slice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    addUserMessage(state, { payload }: PayloadAction<string>) {
      state.messages.push({ role: 'user', content: payload })
      state.streaming = true
      state.streamingText = ''
      state.clarify = null
    },
    appendToken(state, { payload }: PayloadAction<string>) {
      state.streamingText += payload
    },
    commitStream(state) {
      if (state.streamingText.trim()) {
        state.messages.push({ role: 'assistant', content: state.streamingText })
      }
      state.streamingText = ''
      state.streaming = false
    },
    clarifyRequested(state, { payload }: PayloadAction<Clarify>) {
      state.clarify = payload
    },
    clearClarify(state) {
      state.clarify = null
    },
    setConversationId(state, { payload }: PayloadAction<string>) {
      state.conversationId = payload
    },
    hydrateChat(state, { payload }: PayloadAction<ChatMessage[]>) {
      state.messages = payload
    },
    resetChat(state) {
      state.messages = []
      state.streamingText = ''
      state.streaming = false
      state.clarify = null
    },
  },
})

export const {
  addUserMessage, appendToken, commitStream, clarifyRequested, clearClarify,
  setConversationId, hydrateChat, resetChat,
} = slice.actions
export default slice.reducer
