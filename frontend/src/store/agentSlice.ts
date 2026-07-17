import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

export interface ToolEvent {
  name: string
  status: string
  at: number
}

export interface Suggestion {
  action_type: string
  target_ref?: string | null
  label: string
  rationale_quote?: string | null
  confidence?: number
}

export interface FilteredMaterial {
  material_id: string
  title: string
  reason: string
}

interface AgentState {
  toolLog: ToolEvent[]
  suggestions: Suggestion[]
  filteredMaterials: FilteredMaterial[]
  sampleRejection: Record<string, unknown> | null
  modelBanner: string | null
  error: { code: string; message: string; retry_after?: number } | null
}

const initialState: AgentState = {
  toolLog: [], suggestions: [], filteredMaterials: [], sampleRejection: null,
  modelBanner: null, error: null,
}

const slice = createSlice({
  name: 'agent',
  initialState,
  reducers: {
    toolStarted(state, { payload }: PayloadAction<{ name: string; status: string }>) {
      state.toolLog.push({ name: payload.name, status: payload.status, at: Date.now() })
    },
    setSuggestions(state, { payload }: PayloadAction<Suggestion[]>) {
      state.suggestions = payload
    },
    setFilteredMaterials(state, { payload }: PayloadAction<FilteredMaterial[]>) {
      state.filteredMaterials = payload
    },
    setSampleRejection(state, { payload }: PayloadAction<Record<string, unknown>>) {
      state.sampleRejection = payload
    },
    setBanner(state, { payload }: PayloadAction<string | null>) {
      state.modelBanner = payload
    },
    streamFailed(state, { payload }: PayloadAction<{ code: string; message: string; retry_after?: number }>) {
      state.error = payload
    },
    clearError(state) {
      state.error = null
    },
    resetAgent(state) {
      state.toolLog = []
      state.suggestions = []
      state.filteredMaterials = []
      state.sampleRejection = null
      state.error = null
    },
  },
})

export const {
  toolStarted, setSuggestions, setFilteredMaterials, setSampleRejection,
  setBanner, streamFailed, clearError, resetAgent,
} = slice.actions
export default slice.reducer
