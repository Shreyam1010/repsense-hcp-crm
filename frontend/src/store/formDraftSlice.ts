import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

export interface FieldMeta {
  source: 'user' | 'agent'
  prevValue?: unknown
  rationaleQuote?: string
  needsReview?: boolean
  updatedAt: number
  kind?: 'fill' | 'edit'
}

export interface ComplianceFlag {
  severity: 'info' | 'warn' | 'block'
  code: string
  message: string
  field?: string
}

interface FormDraftState {
  values: Record<string, unknown>
  fieldMeta: Record<string, FieldMeta>
  touchedByUser: string[]
  pendingSuggestions: Record<string, { value: unknown; rationaleQuote?: string }>
  complianceFlags: ComplianceFlag[]
  interactionId: string | null
  version: number
  status: string
  locked: boolean
}

const initialState: FormDraftState = {
  values: {}, fieldMeta: {}, touchedByUser: [], pendingSuggestions: {},
  complianceFlags: [], interactionId: null, version: 0, status: 'DRAFT', locked: false,
}

function entries(patch: Record<string, unknown>): [string, unknown][] {
  return Object.entries(patch)
}

const slice = createSlice({
  name: 'formDraft',
  initialState,
  reducers: {
    applyAgentPatch(state, { payload }: PayloadAction<Record<string, unknown>>) {
      const now = Date.now()
      for (const [path, v] of entries(payload)) {
        if (state.touchedByUser.includes(path)) {

          state.pendingSuggestions[path] = { value: v }
          continue
        }
        const isEdit = state.values[path] !== undefined &&
          JSON.stringify(state.values[path]) !== JSON.stringify(v)
        state.fieldMeta[path] = {
          source: 'agent', prevValue: state.values[path], updatedAt: now,
          kind: isEdit ? 'edit' : 'fill',
        }
        state.values[path] = v
      }
    },
    userEditedField(state, { payload }: PayloadAction<{ path: string; value: unknown }>) {
      state.values[payload.path] = payload.value
      state.fieldMeta[payload.path] = { source: 'user', updatedAt: Date.now() }
      if (!state.touchedByUser.includes(payload.path)) state.touchedByUser.push(payload.path)
      delete state.pendingSuggestions[payload.path]
    },
    acceptSuggestion(state, { payload }: PayloadAction<string>) {
      const s = state.pendingSuggestions[payload]
      if (!s) return
      state.values[payload] = s.value
      state.fieldMeta[payload] = { source: 'agent', updatedAt: Date.now(), kind: 'edit' }

      state.touchedByUser = state.touchedByUser.filter((p) => p !== payload)
      delete state.pendingSuggestions[payload]
    },
    keepMine(state, { payload }: PayloadAction<string>) {
      delete state.pendingSuggestions[payload]
    },
    addFlag(state, { payload }: PayloadAction<ComplianceFlag>) {
      state.complianceFlags.push(payload)
    },
    setFiled(state, { payload }: PayloadAction<{ interactionId: string; version: number; status: string }>) {
      state.interactionId = payload.interactionId
      state.version = payload.version
      state.status = payload.status
      state.locked = payload.status === 'SUBMITTED' || payload.status === 'AMENDED'
    },
    hydrate(state, { payload }: PayloadAction<{ values: Record<string, unknown>; interactionId?: string | null }>) {
      state.values = payload.values || {}
      state.interactionId = payload.interactionId ?? null
    },
    resetForm() {
      return initialState
    },
  },
})

export const {
  applyAgentPatch, userEditedField, acceptSuggestion, keepMine, addFlag, setFiled, hydrate, resetForm,
} = slice.actions
export default slice.reducer
