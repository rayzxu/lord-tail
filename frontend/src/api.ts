export type Talent = { id: string; name: string; description: string }
export type Tile = { x: number; y: number; kind: string; label: string; owner: string | null }
export type DiplomacyState = { stance: string; relation: number; treaties: unknown[]; at_war: boolean }
export type MapTileKind = { label: string; category: 'terrain' | 'settlement' | 'structure'; icon: string; color: string; description: string }
export type FactionStatic = { color: string; banner: string; description: string; is_player?: boolean }
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
  items?: Record<string, ItemCatalogEntry>
  equipment_slots?: Record<string, EquipmentSlotInfo>
  diplomacy?: Record<string, string | DiplomacyState>
  population_classes?: Record<string, PopulationClassCatalog>
  [key: string]: unknown
}
export type AttributeId = 'STR' | 'DEX' | 'CON' | 'INT' | 'WIS' | 'CHA' | string
export type EquipmentSlotInfo = { label: string; adult_only?: boolean; examples?: string[] }
export type ItemCatalogEntry = {
  name: string
  type?: string
  slot?: string
  allowed_slots?: string[]
  occupied_slots?: string[]
  armor?: number
  damage?: number
  weight?: number
  durability?: number
  warmth?: number
  value?: number
  tags?: string[]
  requirements?: Record<string, unknown>
  description?: string
  effects?: { character_attributes?: Record<AttributeId, number>; realm_resources?: Record<string, number> }
}
export type ItemsCatalogResponse = {
  items: Record<string, ItemCatalogEntry>
  attribute_ids: Record<AttributeId, { name: string; label: string; influence: string }>
  equipment_slots: Record<string, EquipmentSlotInfo>
  public_equipment_slots: string[]
  private_equipment_slots: string[]
  accessory_equipment_slots: string[]
  body_slot_presets?: Record<string, { label: string; slots: string[] }>
}
export type ArmyStatus = { organization: number; routed: boolean; last_loss_ratio: number }
export type FactionOperationalState = {
  is_player?: boolean
  resources: Record<string, number>
  changes: Record<string, number>
  army: Record<string, number>
  army_status: ArmyStatus
  buildings: Record<string, number>
  workforce?: { available: number; assigned: number }
  laws?: string[]
  territory?: { owned_tile_count: number; owned_tiles: Tile[] }
}
export type FactionDetail = FactionStatic & { stance: string; relation: number; treaties: { name: string; remaining_turns: number }[]; at_war: boolean; owned_tiles: Tile[]; owned_tile_count: number; state?: FactionOperationalState }
export type TurnEvent = { phase: string; kind: string; message: string; severity: 'info' | 'warning' | 'critical' | string; data: Record<string, unknown> }
export type HistoryEntry = {
  id: string
  turn: number
  calendar_day: number
  clock_24: string
  season: string
  weather: string
  title: string
  summary_md: string
  details_md?: string
  source: string
  importance: number
  visibility: string
  tags: string[]
  related: Record<string, unknown>
  created_by?: string
  created_at?: string
  updated_at?: string
}
export type HistoryResponse = { entries: HistoryEntry[]; total: number }
export type GameTimePoint = { calendar_day: number; clock_24: string; season?: string; weather?: string }
export type ScheduledEvent = {
  id: string
  type: string
  title: string
  description_md: string
  status: 'scheduled' | 'due' | 'active' | 'resolved' | 'cancelled' | 'missed' | string
  visibility: string
  importance: number
  created_time: GameTimePoint
  schedule: { due_time: GameTimePoint; window_days?: number; repeat?: Record<string, unknown> | null }
  conditions?: Record<string, unknown>
  on_due?: Record<string, unknown>
  on_resolve?: Record<string, unknown>
  related?: Record<string, unknown>
  flags?: Record<string, unknown>
  result_md?: string
  created_by?: string
  updated_at?: string
}
export type ScheduledEventsResponse = {
  events: ScheduledEvent[]
  total: number
  context?: { urgent_due_events: ScheduledEvent[]; active_events: ScheduledEvent[]; upcoming_events: ScheduledEvent[] }
}
export type StoryletChoice = { id: string; label: string; description_md: string; confirm?: boolean }
export type StoryletInstance = {
  id: string; definition_id: string; node_key: string; title: string; category: string; chain_id: string
  status: 'ready' | 'active' | 'awaiting_choice' | 'resolved' | 'failed' | 'cancelled' | string
  priority: 'major' | 'minor' | string; blocking: boolean; scene_type: string
  created_time: GameTimePoint; activated_time?: GameTimePoint | null; resolved_time?: GameTimePoint | null
  scheduled_event_id?: string; scene_id?: string | null
  cast: Record<string, string>; cast_snapshots: Record<string, { id?: string; name?: string; role?: string; class_id?: string }>
  facts: Record<string, unknown>; choice_ids: string[]; choices?: StoryletChoice[]
  narrative_md: string; narrative_source?: string; selected_choice_id?: string | null
  result?: Record<string, unknown> | null; followup_instance_ids?: string[]
}
export type StoryletsResponse = { instances: StoryletInstance[]; total: number; current_instance_id?: string | null }
export type ManagementMode = 'delegated' | 'advisory' | 'manual'
export type RealmAnalysis = {
  resources: Record<string, number>
  finance: Record<string, unknown>
  military: Record<string, unknown>
  diplomacy: Record<string, unknown>
  stability: Record<string, number>
  metrics: Record<string, number | string | null>
}
export type CouncilProposal = {
  id: string
  domain: 'finance' | 'military' | 'diplomacy' | 'reserve' | string
  title: string
  minister: string
  summary: string
  speech_md: string
  evidence: string[]
  targets: Record<string, number>
  budget_limits: Record<string, number>
  allowed_action_tags: string[]
  risks: string[]
  forecast?: { horizon_turns?: number; status?: string; summary?: string }
}
export type CouncilMeeting = {
  id: string
  event_id?: string
  status: string
  reason: string
  trigger_key: string
  opened_time: GameTimePoint
  analysis_snapshot: RealmAnalysis
  crisis_summary: string[]
  proposals: CouncilProposal[]
  resolved_proposal_id?: string | null
  resolved_time?: GameTimePoint | null
  management_mode?: ManagementMode | null
}
export type StrategicDirective = {
  id: string
  source_meeting_id: string
  proposal_id: string
  domain: string
  title: string
  status: 'active' | 'completed' | 'expired' | 'suspended' | 'replaced' | string
  started_time: GameTimePoint
  expires_time: GameTimePoint
  duration_strategic_turns: number
  executed_strategic_turns: number
  targets: Record<string, number>
  budget_limits: Record<string, number>
  allowed_action_tags: string[]
  progress: Record<string, { target: number; actual: number | null; completed: boolean }>
  completed_targets: string[]
}
export type StrategicAction = {
  type: string
  action_id: string
  actor: string
  tags: string[]
  payload: Record<string, unknown>
  estimated_cost: Record<string, number>
  explanation_key: string
}
export type ManagementCandidate = {
  action: StrategicAction
  label: string
  legal: boolean
  score: number
  score_breakdown: Record<string, number>
  hard_constraint_failures: string[]
  reason: string
  planned_sequence: string[]
}
export type ManagementDecision = {
  id: string
  mode: ManagementMode
  directive_id: string
  turn: number
  selected_action: StrategicAction
  selected_label: string
  reason: string
  score: number
  score_breakdown: Record<string, number>
  candidates: ManagementCandidate[]
  planned_sequence_labels: string[]
  forecast: Record<string, unknown>
}
export type ManagementAiState = {
  enabled: boolean
  mode: ManagementMode
  last_decision?: ManagementDecision | null
  pending_advice?: ManagementDecision | null
  accepted_action?: StrategicAction | null
  consecutive_no_action_turns: number
}
export type CharacterEntry = {
  id: string
  kind?: string
  name: string
  role: string
  gender: string
  age?: number | null
  faction: string
  location: string
  status: string
  appearance_md: string
  personality_md: string
  description_md: string
  relationship_to_lord: string
  disposition: number
  traits: string[]
  memories: string[]
  components?: Record<string, unknown>
  flags: Record<string, unknown>
  created_time?: GameTimePoint
  created_at?: string
  updated_at?: string
}
export type CharactersResponse = { characters: CharacterEntry[]; total: number }
export type CharacterRelationship = { id: string; from_character_id: string; to_character_id: string; type: string; inverse_type: string; strength: number; status: string; source_story_event_id?: string }
export type CharacterUpsertPayload = {
  kind?: string
  name: string
  role?: string
  gender?: string
  age?: number | null
  faction?: string
  location?: string
  status?: string
  appearance_md?: string
  personality_md?: string
  description_md?: string
  relationship_to_lord?: string
  disposition?: number
  traits?: string[]
  memories?: string[]
  flags?: Record<string, unknown>
}
export type CharacterMutationResult = TurnResult & { character: CharacterEntry; created?: boolean }
export type CharacterItemGrantPayload = { item_id: string; quantity?: number; created_by?: string }
export type CharacterEquipPayload = { item_id: string; slot?: string; auto_add?: boolean; created_by?: string }
export type CharacterUnequipPayload = { slot?: string; item_id?: string; created_by?: string }
export type CharacterComponentPatchPayload = { values: Record<string, unknown>; created_by?: string }
export type LordMutationResult = TurnResult & { lord: CharacterEntry; item_effects?: Record<string, unknown> }
export type AgentRunMode = 'strategic_turn' | 'scene_step' | 'story_turn' | 'describe_realm' | 'describe_lord' | 'describe_tile' | 'describe_item' | 'storylet_opening' | 'storylet_result'
export type AgentRunStartRequest = { mode: AgentRunMode; input: string; client_context?: Record<string, unknown> }
export type AgentRunStartResponse = { run_id: string; hermes_run_id: string; status: string; events_url: string }
export type AgentRunStatus = { run_id: string; hermes_run_id?: string; status: string; mode?: AgentRunMode; input?: string; output?: string; error?: string }
export type AgentSseEvent = { seq?: number; event?: string; type?: string; message?: string; delta?: string; output?: string; text?: string; status?: string; question?: string; choices?: unknown[]; clarify_id?: string; data?: Record<string, unknown>; [key: string]: unknown }
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
  factions?: Record<string, FactionStatic>
  time?: GameTime; game_mode?: 'strategic' | 'scene' | string; active_scene?: ActiveScene | null
  lord_components?: Record<string, unknown>
  resources: Record<string, number> & { gold: number; food: number; wood: number; stone: number; population: number; morale: number; authority: number }
  effective_resources?: Record<string, number>
  item_effects?: { realm_resource_modifiers?: Record<string, number>; sources?: Record<string, unknown>[] }
  changes: Record<string, number>; army: { infantry: number; archers: number; cavalry: number }
  army_status?: ArmyStatus; diplomacy: Record<string, string | DiplomacyState>; demographics?: Record<string, unknown>; buildings: Record<string, number>; laws: string[]; map: Tile[]; map_size: number; diplomacy_map?: Tile[]; diplomacy_map_size?: number
  faction_states?: Record<string, FactionOperationalState>
  scheduled_events?: { entries: ScheduledEvent[]; next_id: number }
  council?: { current_meeting: CouncilMeeting | null; history: CouncilMeeting[]; next_id: number }
  strategic_directive?: StrategicDirective | null
  management_ai?: ManagementAiState
  characters?: { entries: CharacterEntry[]; next_id: number }
  storylets?: { current_instance_id?: string | null; instances?: StoryletInstance[]; [key: string]: unknown }
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
  items: () => request<ItemsCatalogResponse>('/items'),
  characters: (query = '') => request<CharactersResponse>(`/characters${query}`),
  characterRelationships: (characterId: string) => request<{ relationships: CharacterRelationship[]; total: number }>(`/characters/${encodeURIComponent(characterId)}/relationships`),
  history: (query = '') => request<HistoryResponse>(`/history${query}`),
  events: (query = '') => request<ScheduledEventsResponse>(`/events${query}`),
  storylets: {
    list: (query = '') => request<StoryletsResponse>(`/storylets${query}`),
    current: () => request<{ instance: StoryletInstance | null }>('/storylets/current'),
    detail: (id: string) => request<{ instance: StoryletInstance; chain: Record<string, unknown> }>(`/storylets/${encodeURIComponent(id)}`),
    choose: (id: string, choiceId: string) => request<TurnResult & { instance: StoryletInstance; result: Record<string, unknown>; idempotent: boolean }>(`/storylets/${encodeURIComponent(id)}/choose`, { method: 'POST', body: JSON.stringify({ choice_id: choiceId, actor: 'player' }) }),
  },
  start: (settings: Record<string, unknown>) => request<TurnResult>('/game/start', { method: 'POST', body: JSON.stringify(settings) }),
  turn: (command: string) => request<TurnResult>('/game/turn', { method: 'POST', body: JSON.stringify({ command }) }),
  time: () => request<{ turn: number; time: GameTime; game_mode: string; active_scene: ActiveScene | null }>('/time'),
  strategicTurn: (payload: StrategicTurnRequest) => request<TurnResult>('/game/strategic-turn', { method: 'POST', body: JSON.stringify(payload) }),
  council: {
    current: () => request<{ meeting: CouncilMeeting | null; history: CouncilMeeting[]; directive: StrategicDirective | null; management_ai: ManagementAiState }>('/council/current'),
    resolve: (meetingId: string, payload: { proposal_id: string; management_mode: ManagementMode }) => request<TurnResult & { meeting: CouncilMeeting; directive: StrategicDirective; idempotent: boolean }>(`/council/${encodeURIComponent(meetingId)}/resolve`, { method: 'POST', body: JSON.stringify(payload) }),
    requestReview: () => request<TurnResult & { meeting: CouncilMeeting }>('/council/request-review', { method: 'POST' }),
  },
  strategy: {
    current: () => request<{ directive: StrategicDirective | null; management_ai: ManagementAiState }>('/strategy/current'),
    analysis: () => request<{ analysis: RealmAnalysis }>('/strategy/analysis'),
    setMode: (mode: ManagementMode) => request<TurnResult & { management_ai: ManagementAiState }>('/strategy/management-mode', { method: 'POST', body: JSON.stringify({ mode }) }),
    advice: () => request<{ decision: ManagementDecision }>('/strategy/advice'),
    acceptAdvice: (decisionId: string, actionId = '') => request<TurnResult & { decision: ManagementDecision; accepted_action: StrategicAction }>(`/strategy/advice/${encodeURIComponent(decisionId)}/accept`, { method: 'POST', body: JSON.stringify({ action_id: actionId }) }),
  },
  actions: {
    legal: () => request<{ actions: StrategicAction[] }>('/actions/legal'),
    validate: (action: StrategicAction, actor = 'player') => request<{ legal: boolean; action: StrategicAction; errors: string[] }>('/actions/validate', { method: 'POST', body: JSON.stringify({ action, actor }) }),
    execute: (action: StrategicAction, actor = 'player') => request<TurnResult & { action: StrategicAction }>('/actions/execute', { method: 'POST', body: JSON.stringify({ action, actor }) }),
  },
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
    characters: {
      upsert: (payload: CharacterUpsertPayload) => request<CharacterMutationResult>('/state/characters', { method: 'POST', body: JSON.stringify(payload) }),
      grantItem: (characterId: string, payload: CharacterItemGrantPayload) => request<CharacterMutationResult>(`/state/characters/${encodeURIComponent(characterId)}/items`, { method: 'POST', body: JSON.stringify(payload) }),
      equip: (characterId: string, payload: CharacterEquipPayload) => request<CharacterMutationResult>(`/state/characters/${encodeURIComponent(characterId)}/equipment/equip`, { method: 'POST', body: JSON.stringify(payload) }),
      unequip: (characterId: string, payload: CharacterUnequipPayload) => request<CharacterMutationResult>(`/state/characters/${encodeURIComponent(characterId)}/equipment/unequip`, { method: 'POST', body: JSON.stringify(payload) }),
      patchComponent: (characterId: string, componentId: string, payload: CharacterComponentPatchPayload) => request<CharacterMutationResult>(`/state/characters/${encodeURIComponent(characterId)}/components/${encodeURIComponent(componentId)}`, { method: 'PATCH', body: JSON.stringify(payload) }),
    },
    lord: {
      grantItem: (payload: CharacterItemGrantPayload) => request<LordMutationResult>('/state/lord/items', { method: 'POST', body: JSON.stringify(payload) }),
      equip: (payload: CharacterEquipPayload) => request<LordMutationResult>('/state/lord/equipment/equip', { method: 'POST', body: JSON.stringify(payload) }),
      unequip: (payload: CharacterUnequipPayload) => request<LordMutationResult>('/state/lord/equipment/unequip', { method: 'POST', body: JSON.stringify(payload) }),
      patchComponent: (componentId: string, payload: CharacterComponentPatchPayload) => request<LordMutationResult>(`/state/lord/components/${encodeURIComponent(componentId)}`, { method: 'PATCH', body: JSON.stringify(payload) }),
    },
    battles: {
      resolve: (payload: BattleResolveRequest) => request<TurnResult & { battle_result: BattleResult }>('/state/battles/resolve', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    },
  },
}
