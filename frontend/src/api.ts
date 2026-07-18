export type Talent = { id: string; name: string; description: string }
export type Tile = { x: number; y: number; kind: string; label: string; owner: string | null }
export type DiplomacyState = { stance: string; relation: number; treaties: unknown[]; at_war: boolean }
export type MapTileKind = { label: string; category: 'terrain' | 'settlement' | 'structure'; icon: string; color: string; description: string }
export type FactionStatic = { color: string; banner: string; description: string }
export type MapConfig = { default_size: number; min_size: number; max_size: number }
export type PopulationClassCatalog = {
  name: string
  description?: string
  productivity: number
  tax: number
  expense: number
  annual_birth_rate: number
  housing_types: string[]
  class_requirement?: number
}
export type Catalog = {
  map: MapConfig
  map_tile_kinds: Record<string, MapTileKind>
  diplomacy_tile_kinds: Record<string, MapTileKind>
  factions: Record<string, FactionStatic>
  population_classes?: Record<string, PopulationClassCatalog>
  [key: string]: unknown
}
export type FactionDetail = FactionStatic & { stance: string; relation: number; treaties: { name: string; remaining_turns: number }[]; at_war: boolean; owned_tiles: Tile[]; owned_tile_count: number }
export type ArmyStatus = { organization: number; routed: boolean; last_loss_ratio: number }
export type TurnEvent = { phase: string; kind: string; message: string; severity: 'info' | 'warning' | 'critical' | string; data: Record<string, unknown> }
export type AgentRunMode = 'strategic_turn' | 'scene_step' | 'story_turn' | 'describe_realm' | 'describe_lord' | 'describe_tile' | 'describe_item'
export type AgentRunStartRequest = { mode: AgentRunMode; input: string; client_context?: Record<string, unknown> }
export type AgentRunStartResponse = { run_id: string; hermes_run_id: string; status: string; events_url: string }
export type AgentRunStatus = { run_id: string; hermes_run_id?: string; status: string; mode?: AgentRunMode; input?: string; output?: string; error?: string }
export type AgentSseEvent = { seq?: number; event?: string; type?: string; message?: string; delta?: string; output?: string; text?: string; status?: string; data?: Record<string, unknown>; [key: string]: unknown }
export type AgentTraceEvent = {
  id: string
  kind: 'message' | 'reasoning' | 'tool' | 'approval' | 'clarify' | 'state_action' | 'run'
  title: string
  detail?: string
  status?: 'running' | 'complete' | 'error' | 'pending'
}
export type GameTime = {
  calendar_day: number
  turn_days: number
  day_in_turn: number
  hour: number
  hour_24?: number
  minute?: number
  clock?: string
  clock_24?: string
  time_of_day: string
  season: string
  weather: string
}
export type ActiveScene = {
  id: string
  type: string
  title: string
  status: string
  elapsed_hours: number
  elapsed_minutes?: number
  elapsed_days: number
  recent_messages?: unknown[]
  [key: string]: unknown
}
export type GameState = {
  realm_name: string; lord_name: string; lord_gender: string; appearance: string; personality: string
  talents: Talent[]; turn: number; season: string; weather: string
  time?: GameTime; game_mode?: 'strategic' | 'scene' | string; active_scene?: ActiveScene | null
  resources: Record<string, number> & { gold: number; food: number; wood: number; stone: number; population: number; morale: number; authority: number }
  changes: Record<string, number>; army: { infantry: number; archers: number; cavalry: number }
  army_status?: ArmyStatus; diplomacy: Record<string, string | DiplomacyState>; demographics?: Record<string, unknown>; buildings: Record<string, number>; laws: string[]; map: Tile[]; map_size: number; diplomacy_map?: Tile[]; diplomacy_map_size?: number
}
export type TurnResult = { state: GameState; narrative: string; suggestions: string[]; source: 'rules' | 'hermes' | 'state-api'; events?: TurnEvent[]; run_id?: string; trace?: AgentTraceEvent[] }
export type ResourceMutation = { changes?: Record<string, number>; values?: Record<string, number> }
export type ValueMutation = { delta?: number; value?: number }
export type ArmyMutation = ValueMutation & { unit: string }
export type DiplomacyMutation = { faction: string; status: string }
export type BuildingMutation = { building: string; action: 'build' | 'destroy'; count?: number; x?: number; y?: number }
export type StrategicTurnRequest = { command: string; source?: string; force_end_scene?: boolean }
export type SceneStartRequest = { type?: string; title: string; participants?: Record<string, unknown>[]; flags?: Record<string, unknown> }
export type SceneStepRequest = { input?: string; narrative?: string; events?: TurnEvent[] }
export type SceneAdvanceTimeRequest = { hours?: number; minutes?: number; days?: number; reason?: string; run_due_strategic_turns?: boolean }
export type SceneEndRequest = { summary?: string; outcome?: Record<string, unknown> }
export type BattleResolveRequest = {
  player?: Record<string, number>
  enemy: Record<string, number>
  enemy_organization?: number
  terrain?: string
  stance?: 'cautious' | 'balanced' | 'aggressive'
  apply_to_state?: boolean
  source?: string
  label?: string
  notes?: string
}
export type BattleResult = {
  id: string
  winner: 'player' | 'enemy'
  terrain: string
  stance: 'cautious' | 'balanced' | 'aggressive' | string
  player: Record<string, unknown>
  enemy: Record<string, unknown>
  modifiers: Record<string, unknown>
  scores: Record<string, number>
}
export type PopulationClassState = {
  name: string
  population: number
  wealth_per_capita: number
  morale: number
  age: { child: number; working: number; elder: number; [key: string]: number }
  sex: { female: number; male: number; [key: string]: number }
  pregnancy: Record<string, number>
  last_births: number
  last_migration: number
  last_outflow: number
  last_wealth_delta: number
}
export type HousingState = {
  by_type: Record<string, { capacity: number; occupied: number; vacant: number; quality: number }>
  total_capacity: number
  total_occupied: number
  total_vacant: number
}
export type DemographicsResponse = {
  demographics: {
    classes: Record<string, PopulationClassState>
    housing: HousingState
    last_births: number
    last_migration: number
    last_outflow: number
    last_wealth_delta: number
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? '请求未完成')
  return response.json() as Promise<T>
}

export const api = {
  talents: () => request<Talent[]>('/talents'),
  catalog: () => request<Catalog>('/catalog'),
  demographics: () => request<DemographicsResponse>('/demographics'),
  start: (settings: Record<string, unknown>) => request<TurnResult>('/game/start', { method: 'POST', body: JSON.stringify(settings) }),
  turn: (command: string) => request<TurnResult>('/game/turn', { method: 'POST', body: JSON.stringify({ command }) }),
  time: () => request<{ turn: number; time: GameTime; game_mode: string; active_scene: ActiveScene | null }>('/time'),
  strategicTurn: (payload: StrategicTurnRequest) => request<TurnResult>('/game/strategic-turn', { method: 'POST', body: JSON.stringify(payload) }),
  save: () => request<{ message: string }>('/game/save', { method: 'POST' }),
  load: () => request<TurnResult>('/game/load', { method: 'POST' }),
  scenes: {
    start: (payload: SceneStartRequest) => request<TurnResult>('/game/scenes', { method: 'POST', body: JSON.stringify(payload) }),
    step: (payload: SceneStepRequest) => request<TurnResult>('/game/scenes/current/step', { method: 'POST', body: JSON.stringify(payload) }),
    advanceTime: (payload: SceneAdvanceTimeRequest) => request<TurnResult>('/game/scenes/current/advance-time', { method: 'POST', body: JSON.stringify(payload) }),
    end: (payload: SceneEndRequest) => request<TurnResult>('/game/scenes/current/end', { method: 'POST', body: JSON.stringify(payload) }),
  },
  agent: {
    startRun: (payload: AgentRunStartRequest) => request<AgentRunStartResponse>('/agent/runs', { method: 'POST', body: JSON.stringify(payload) }),
    runStatus: (runId: string) => request<AgentRunStatus>(`/agent/runs/${encodeURIComponent(runId)}`),
    eventsUrl: (runId: string, sinceSeq?: number) => `/api/agent/runs/${encodeURIComponent(runId)}/events${sinceSeq ? `?since_seq=${sinceSeq}` : ''}`,
    cancel: (runId: string) => request<{ status: string }>(`/agent/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' }),
    approval: (runId: string, payload: Record<string, unknown>) => request<{ status: string }>(`/agent/runs/${encodeURIComponent(runId)}/approval`, { method: 'POST', body: JSON.stringify(payload) }),
    clarify: (runId: string, payload: Record<string, unknown>) => request<{ status: string }>(`/agent/runs/${encodeURIComponent(runId)}/clarify`, { method: 'POST', body: JSON.stringify(payload) }),
  },
  state: {
    read: () => request<{ state: GameState }>('/state'),
    resources: (mutation: ResourceMutation) => request<TurnResult>('/state/resources', { method: 'POST', body: JSON.stringify(mutation) }),
    population: (mutation: ValueMutation) => request<TurnResult>('/state/population', { method: 'POST', body: JSON.stringify(mutation) }),
    morale: (mutation: ValueMutation) => request<TurnResult>('/state/morale', { method: 'POST', body: JSON.stringify(mutation) }),
    army: (mutation: ArmyMutation) => request<TurnResult>('/state/army', { method: 'POST', body: JSON.stringify(mutation) }),
    diplomacy: (mutation: DiplomacyMutation) => request<TurnResult>('/state/diplomacy', { method: 'POST', body: JSON.stringify(mutation) }),
    buildings: (mutation: BuildingMutation) => request<TurnResult>('/state/buildings', { method: 'POST', body: JSON.stringify(mutation) }),
    battles: {
      resolve: (payload: BattleResolveRequest) => request<TurnResult & { battle_result: BattleResult }>('/state/battles/resolve', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    },
  },
}
