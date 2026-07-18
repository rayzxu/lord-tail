import { FormEvent, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { AgentRunMode, AgentSseEvent, AgentTraceEvent, api, Catalog, DemographicsResponse, DiplomacyState, FactionDetail, GameState, PopulationClassCatalog, PopulationClassState, Talent, Tile, TurnResult } from './api'

const fallbackIcon: Record<string, string> = { grass: '·', castle: '♜', homes: '⌂', farm: '≋', forest: '♣', lumberyard: '♧', quarry: '◆', barracks: '⚔', wall: '▤' }
const resourceLabels: Record<string, [string, string]> = {
  gold: ['金币', '✦'], food: ['粮食', '◒'], wood: ['木材', '▥'], stone: ['石料', '◆'], population: ['人口', '♙'], morale: ['民心', '♡'], authority: ['统治力', '⚖'],
}
function diplomacyLabel(value: GameState['diplomacy'][string]) { return typeof value === 'string' ? value : value.stance }
function diplomacyState(value: GameState['diplomacy'][string]): DiplomacyState {
  return typeof value === 'string' ? { stance: value, relation: 0, treaties: [], at_war: value === '战争' } : value
}
function columnLabel(index: number) { return index < 26 ? String.fromCharCode(65 + index) : String(index + 1) }
function coordLabel(x: number, y: number) { return `${columnLabel(x - 1)}${y}` }
function clock24(time?: { hour?: number; minute?: number; clock_24?: string; clock?: string }) {
  if (time?.clock_24 || time?.clock) return String(time.clock_24 || time.clock)
  const hour = Math.max(0, Number(time?.hour ?? 6)) % 24
  const minute = Math.max(0, Number(time?.minute ?? 0)) % 60
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}
function categoryLabel(category?: string) { return category === 'terrain' ? '天然地形' : category === 'settlement' ? '聚落' : category === 'structure' ? '建筑设施' : '未知' }
function realmTileInfo(catalog: Catalog | null, kind: string) { return catalog?.map_tile_kinds?.[kind] }
function diplomacyTileInfo(catalog: Catalog | null, kind: string) { return catalog?.diplomacy_tile_kinds?.[kind] ?? catalog?.map_tile_kinds?.[kind] }
function tileIcon(catalog: Catalog | null, kind: string) { return realmTileInfo(catalog, kind)?.icon ?? fallbackIcon[kind] ?? '·' }
function diplomacyTileIcon(catalog: Catalog | null, kind: string) { return diplomacyTileInfo(catalog, kind)?.icon ?? fallbackIcon[kind] ?? '·' }
const diplomacySettlementKinds: [string, string][] = [['village', '农村'], ['castle', '城堡'], ['town', '城镇'], ['slum', '流民窝棚']]
const diplomacyOnlyRealmKinds = new Set(['town', 'village', 'slum'])
function realmMapTile(tile: Tile): Tile {
  if (tile.owner || diplomacyOnlyRealmKinds.has(tile.kind)) return { ...tile, kind: 'grass', label: '草地', owner: null }
  return tile.owner === null ? tile : { ...tile, owner: null }
}
function fallbackDiplomacyMap(state: GameState, size: number): Tile[] {
  const tiles = Array.from({ length: size * size }, (_, index) => {
    const x = (index % size) + 1
    const y = Math.floor(index / size) + 1
    return { x, y, kind: 'grass', label: '草地', owner: null } as Tile
  })
  const byCoord = new Map(tiles.map(tile => [`${tile.x}-${tile.y}`, tile]))
  const perimeter = [
    ...Array.from({ length: size }, (_, index) => [index + 1, 1] as const),
    ...Array.from({ length: Math.max(0, size - 1) }, (_, index) => [size, index + 2] as const),
    ...Array.from({ length: Math.max(0, size - 1) }, (_, index) => [size - index - 1, size] as const),
    ...Array.from({ length: Math.max(0, size - 2) }, (_, index) => [1, size - index - 1] as const),
  ]
  const factions = Object.keys(state.diplomacy)
  const step = factions.length ? Math.max(1, Math.floor(perimeter.length / factions.length)) : 1
  factions.forEach((faction, index) => {
    const [x, y] = perimeter[(index * step) % perimeter.length] ?? [1, 1]
    const [kind, suffix] = diplomacySettlementKinds[index % diplomacySettlementKinds.length]
    const tile = byCoord.get(`${x}-${y}`)
    if (tile) {
      tile.kind = kind
      tile.label = `${faction}${suffix}`
      tile.owner = faction
    }
  })
  return tiles
}
const housingLabels: Record<string, string> = { hut: '窝棚', open_land_shelter: '空地自建窝棚', townhouse: '镇屋', workshop_home: '作坊住房', shop_home: '商铺住房', manor: '宅邸' }
function housingLabel(type: string) { return housingLabels[type] ?? type }
function percent(part: number, total: number) { return total > 0 ? `${Math.round((part / total) * 100)}%` : '-' }
function sumNumbers(values: Record<string, number> | undefined) { return Object.values(values ?? {}).reduce((total, value) => total + Number(value || 0), 0) }
function buildingSummary(buildings: Record<string, number>) {
  const entries = Object.entries(buildings).filter(([, count]) => Number(count) > 0)
  return entries.length ? entries.map(([name, count]) => `${name} ×${count}`).join('、') : '无'
}
function buildFactionDetail(state: GameState, catalog: Catalog | null, faction: string): FactionDetail {
  const dynamic = diplomacyState(state.diplomacy[faction])
  const info = catalog?.factions?.[faction]
  const diplomacyMap = state.diplomacy_map?.length ? state.diplomacy_map : fallbackDiplomacyMap(state, state.diplomacy_map_size || state.map_size || 10)
  const ownedTiles = diplomacyMap.filter(tile => tile.owner === faction)
  return {
    stance: dynamic.stance,
    relation: dynamic.relation,
    treaties: dynamic.treaties as { name: string; remaining_turns: number }[],
    at_war: dynamic.at_war,
    color: info?.color ?? '#8a8a8a',
    banner: info?.banner ?? '⚑',
    description: info?.description ?? '',
    owned_tiles: ownedTiles,
    owned_tile_count: ownedTiles.length,
  }
}

type Settings = { lord_name: string; lord_gender: string; realm_name: string; appearance: string; personality: string }
const defaultSettings: Settings = { lord_name: '亚历山大', lord_gender: '男', realm_name: '黑泥堡', appearance: '', personality: '' }

function App() {
  const [view, setView] = useState<'setup' | 'game'>('setup')
  const [talents, setTalents] = useState<Talent[]>([])
  const [visibleTalents, setVisibleTalents] = useState<Talent[]>([])
  const [selected, setSelected] = useState<Talent[]>([])
  const [settings, setSettings] = useState(defaultSettings)
  const [game, setGame] = useState<TurnResult | null>(null)
  const [error, setError] = useState('')
  const [catalog, setCatalog] = useState<Catalog | null>(null)

  useEffect(() => { api.talents().then(data => { setTalents(data); setVisibleTalents(draw(data)) }).catch(() => setError('无法连接后端，请先启动 FastAPI 服务。')) }, [])
  useEffect(() => { api.catalog().then(setCatalog).catch(() => undefined) }, [])
  const newRoll = () => { setVisibleTalents(draw(talents)); setSelected([]) }

  async function begin(event: FormEvent) {
    event.preventDefault(); setError('')
    if (selected.length !== 2) return setError('请先选择两项命运赐福。')
    try { setGame(await api.start({ ...settings, talents: selected })); setView('game') }
    catch (e) { setError(e instanceof Error ? e.message : '开局失败') }
  }
  const update = (key: keyof Settings, value: string) => setSettings(previous => ({ ...previous, [key]: value }))

  if (view === 'game' && game) return <GameScreen game={game} onGame={setGame} onBack={() => setView('setup')} catalog={catalog} />
  return <SetupScreen settings={settings} update={update} talents={visibleTalents} selected={selected} error={error} onRoll={newRoll} onToggle={(talent) => setSelected(previous => previous.some(t => t.id === talent.id) ? previous.filter(t => t.id !== talent.id) : previous.length < 2 ? [...previous, talent] : previous)} onSubmit={begin} />
}

function SetupScreen({ settings, update, talents, selected, error, onRoll, onToggle, onSubmit }: { settings: Settings; update: (key: keyof Settings, value: string) => void; talents: Talent[]; selected: Talent[]; error: string; onRoll: () => void; onToggle: (talent: Talent) => void; onSubmit: (event: FormEvent) => void }) {
  return <main className="setup-page"><form className="setup-card" onSubmit={onSubmit}>
    <div className="eyebrow">THE LORD TAIL · CHRONICLES</div><h1>领主降临设定</h1><p className="lead">在潮湿的春季，写下这片领地的第一个名字。</p>
    <div className="form-grid"><Field label="领主姓名"><input value={settings.lord_name} onChange={e => update('lord_name', e.target.value)} required /></Field><Field label="领主身份"><select value={settings.lord_gender} onChange={e => update('lord_gender', e.target.value)}><option>男</option><option>女</option><option>非二元</option><option>未说明</option></select></Field></div>
    <Field label="领地名称"><input value={settings.realm_name} onChange={e => update('realm_name', e.target.value)} required /></Field>
    <Field label="领主外表"><textarea value={settings.appearance} onChange={e => update('appearance', e.target.value)} placeholder="衣着、神情、气质……" /></Field>
    <Field label="领主性格"><textarea value={settings.personality} onChange={e => update('personality', e.target.value)} placeholder="信念、野心与执政风格……" /></Field>
    <section className="talent-section"><div className="section-head"><div><span className="section-label">命运赐福</span><small>选择 2 项 · {selected.length}/2</small></div><button type="button" className="ghost-button" onClick={onRoll}>↻ 换一批</button></div><div className="talent-grid">{talents.map(talent => <button className={`talent ${selected.some(item => item.id === talent.id) ? 'selected' : ''}`} type="button" key={talent.id} onClick={() => onToggle(talent)}><span className="talent-mark">{selected.some(item => item.id === talent.id) ? '✦' : '○'}</span><span><strong>{talent.name}</strong><small>{talent.description}</small></span></button>)}</div></section>
    {error && <div className="error">{error}</div>}<button className="primary-button" type="submit">写下开局剧本 <span>→</span></button>
  </form></main>
}
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="field"><span>{label}</span>{children}</label> }

type DescriptionState = { open: boolean; title: string; text: string; trace: AgentTraceEvent[]; loading: boolean }
type TileDrawerState = { tile: Tile; source: 'realm' | 'diplomacy'; text: string; trace: AgentTraceEvent[]; loading: boolean }

function GameScreen({ game, onGame, onBack, catalog }: { game: TurnResult; onGame: (game: TurnResult) => void; onBack: () => void; catalog: Catalog | null }) {
  const [command, setCommand] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')
  const [panel, setPanel] = useState<'realm' | 'population' | 'lord' | 'history' | null>(null)
  const [demographics, setDemographics] = useState<DemographicsResponse | null>(null)
  const [demographicsLoading, setDemographicsLoading] = useState(false)
  const [demographicsError, setDemographicsError] = useState('')
  const [trace, setTrace] = useState<AgentTraceEvent[]>(game.trace ?? [])
  const [traceCollapsed, setTraceCollapsed] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [description, setDescription] = useState<DescriptionState>({ open: false, title: '', text: '', trace: [], loading: false })
  const [tileDetail, setTileDetail] = useState<TileDrawerState | null>(null)
  const [factionDetail, setFactionDetail] = useState<string | null>(null)
  const [mapMode, setMapMode] = useState<'tactical' | 'diplomacy'>('tactical')
  const state = game.state
  const realmMapSize = state.map_size || 10
  const diplomacyMapSize = state.diplomacy_map_size || realmMapSize
  const diplomacyMap = useMemo(() => state.diplomacy_map?.length ? state.diplomacy_map : fallbackDiplomacyMap(state, diplomacyMapSize), [state, diplomacyMapSize])
  const realmTiles = useMemo(() => new Map(state.map.map(tile => { const cleanTile = realmMapTile(tile); return [`${cleanTile.x}-${cleanTile.y}`, cleanTile] })), [state.map])
  const diplomacyTiles = useMemo(() => new Map(diplomacyMap.map(tile => [`${tile.x}-${tile.y}`, tile])), [diplomacyMap])
  const realmKinds = useMemo(() => new Set(Array.from(realmTiles.values()).map(tile => tile.kind)), [realmTiles])

  useEffect(() => { setTrace(game.trace ?? []); setStreamText('') }, [game.run_id])

  async function fallbackTurn(text: string) {
    onGame(await api.turn(text))
    setCommand('')
  }

  async function send(text = command) {
    const input = text.trim()
    if (!input || busy) return
    setBusy(true)
    setCommand('')
    setTrace([])
    setStreamText('')
    setTraceCollapsed(false)
    try {
      const mode: AgentRunMode = state.game_mode === 'scene' ? 'scene_step' : 'scene_step'
      const run = await api.agent.startRun({ mode, input, client_context: { screen: 'game', intent: 'scene_step' } })
      let accumulated = ''
      let collectedTrace: AgentTraceEvent[] = []
      const pushTrace = (event: AgentTraceEvent | null) => {
        if (!event) return
        collectedTrace = [...collectedTrace, event].slice(-80)
        setTrace(collectedTrace)
      }
      const source = new EventSource(api.agent.eventsUrl(run.run_id))
      source.onmessage = async message => {
        const event = parseAgentEvent(message.data)
        pushTrace(traceFromAgentEvent(event))
        if (event.event === 'message.delta' && typeof event.delta === 'string') {
          accumulated += event.delta
          setStreamText(accumulated)
        }
        if (event.event === 'run.completed') {
          source.close()
          const output = extractNarrative(event.output) || accumulated || 'Hermes 已完成裁决，但没有返回叙事文本。'
          const suggestions = extractSuggestions(event.output, game.suggestions)
          setStreamText('')
          const refreshed = await api.state.read()
          onGame({ ...game, state: refreshed.state, narrative: output, suggestions, source: 'hermes', run_id: run.run_id, trace: collectedTrace })
          setBusy(false)
        }
        if (event.event === 'run.failed' || event.event === 'run.cancelled') {
          source.close()
          setToast(String(event.message || event.error || 'Hermes run 已终止'))
          setBusy(false)
        }
      }
      source.onerror = () => {
        source.close()
        setToast('Hermes SSE 连接中断')
        setBusy(false)
      }
    } catch (e) {
      try { await fallbackTurn(input) }
      catch (fallbackError) { setToast(fallbackError instanceof Error ? fallbackError.message : e instanceof Error ? e.message : '命令未送达') }
      finally { setBusy(false) }
    }
  }

  async function describe(mode: AgentRunMode, title: string, input: string, client_context: Record<string, unknown>) {
    setDescription({ open: true, title, text: '', trace: [], loading: true })
    try {
      const run = await api.agent.startRun({ mode, input, client_context })
      let accumulated = ''
      let collectedTrace: AgentTraceEvent[] = []
      const source = new EventSource(api.agent.eventsUrl(run.run_id))
      source.onmessage = message => {
        const event = parseAgentEvent(message.data)
        const traceEvent = traceFromAgentEvent(event)
        if (traceEvent) {
          collectedTrace = [...collectedTrace, traceEvent].slice(-80)
          setDescription(previous => ({ ...previous, trace: collectedTrace }))
        }
        if (event.event === 'message.delta' && typeof event.delta === 'string') {
          accumulated += event.delta
          setDescription(previous => ({ ...previous, text: accumulated }))
        }
        if (event.event === 'run.completed') {
          source.close()
          const text = extractNarrative(event.output) || accumulated || 'Hermes 没有返回描述文本。'
          setDescription(previous => ({ ...previous, text, loading: false }))
        }
        if (event.event === 'run.failed' || event.event === 'run.cancelled') {
          source.close()
          setDescription(previous => ({ ...previous, loading: false }))
          setToast(String(event.message || event.error || '描述 run 已终止'))
        }
      }
      source.onerror = () => {
        source.close()
        setDescription(previous => ({ ...previous, loading: false }))
        setToast('Hermes 描述连接中断')
      }
    } catch (e) {
      setDescription(previous => ({ ...previous, loading: false, text: e instanceof Error ? e.message : 'Hermes 描述不可用' }))
    }
  }

  async function openTileDrawer(tile: Tile, source: 'realm' | 'diplomacy' = 'realm') {
    const coord = coordLabel(tile.x, tile.y)
    const updateIfCurrent = (updater: (previous: TileDrawerState) => TileDrawerState) => {
      setTileDetail(previous => {
        if (!previous || previous.source !== source || previous.tile.x !== tile.x || previous.tile.y !== tile.y) return previous
        return updater(previous)
      })
    }
    setTileDetail({ tile, source, text: '', trace: [], loading: true })
    try {
      const run = await api.agent.startRun({
        mode: 'describe_tile',
        input: `描述地图格 ${coord}：${tile.label}`,
        client_context: { selected_tile: { x: tile.x, y: tile.y, map_source: source }, map_source: source, tile },
      })
      let accumulated = ''
      let collectedTrace: AgentTraceEvent[] = []
      const eventSource = new EventSource(api.agent.eventsUrl(run.run_id))
      eventSource.onmessage = message => {
        const event = parseAgentEvent(message.data)
        const traceEvent = traceFromAgentEvent(event)
        if (traceEvent) {
          collectedTrace = [...collectedTrace, traceEvent].slice(-80)
          updateIfCurrent(previous => ({ ...previous, trace: collectedTrace }))
        }
        if (event.event === 'message.delta' && typeof event.delta === 'string') {
          accumulated += event.delta
          updateIfCurrent(previous => ({ ...previous, text: accumulated }))
        }
        if (event.event === 'run.completed') {
          eventSource.close()
          const text = extractNarrative(event.output) || accumulated || 'Hermes 没有返回地块描述。'
          updateIfCurrent(previous => ({ ...previous, text, loading: false }))
        }
        if (event.event === 'run.failed' || event.event === 'run.cancelled') {
          eventSource.close()
          updateIfCurrent(previous => ({ ...previous, loading: false }))
          setToast(String(event.message || event.error || '地块描述 run 已终止'))
        }
      }
      eventSource.onerror = () => {
        eventSource.close()
        updateIfCurrent(previous => ({ ...previous, loading: false }))
        setToast('Hermes 地块描述连接中断')
      }
    } catch (e) {
      updateIfCurrent(previous => ({ ...previous, loading: false, text: e instanceof Error ? e.message : 'Hermes 地块描述不可用' }))
    }
  }

  async function save() { try { setToast((await api.save()).message) } catch (e) { setToast(e instanceof Error ? e.message : '保存失败') } }
  async function load() { try { onGame(await api.load()); setToast('存档已载入') } catch (e) { setToast(e instanceof Error ? e.message : '读取失败') } }
  async function openPopulationPanel() {
    setPanel('population')
    setDemographicsLoading(true)
    setDemographicsError('')
    try {
      setDemographics(await api.demographics())
    } catch (e) {
      setDemographicsError(e instanceof Error ? e.message : '居民分析读取失败')
    } finally {
      setDemographicsLoading(false)
    }
  }
  async function advanceStrategicTurn() {
    if (busy) return
    setBusy(true)
    try {
      const text = command.trim() || '让领地按当前安排运转九天'
      onGame(await api.strategicTurn({ command: text, source: 'player' }))
      setCommand('')
      setToast('九天战略回合已结算')
    } catch (e) {
      setToast(e instanceof Error ? e.message : '战略回合推进失败')
    } finally {
      setBusy(false)
    }
  }
  async function startScene() {
    if (busy) return
    try {
      const title = command.trim() || '领主事件'
      onGame(await api.scenes.start({ type: 'daily', title }))
      setToast('场景已开始')
    } catch (e) {
      setToast(e instanceof Error ? e.message : '场景开始失败')
    }
  }
  async function endScene() {
    if (busy) return
    try {
      const summary = command.trim() || '当前事件已经完成。'
      onGame(await api.scenes.end({ summary }))
      setCommand('')
      setToast('场景已结束')
    } catch (e) {
      setToast(e instanceof Error ? e.message : '场景结束失败')
    }
  }
  const time = state.time
  const activeScene = state.active_scene
  const modeLabel = activeScene ? `场景：${activeScene.title}` : '战略'
  return <main className="game-page">
    <header className="status-bar"><div className="brand"><span className="crest">♜</span><div><small>领地纪事</small><strong>{state.realm_name}</strong></div></div><div className="building-count">建筑 <b>{Object.values(state.buildings).reduce((a, b) => a + b, 0)}</b><span>处</span></div><div className="stat-cluster">{(['gold','food','wood','stone'] as const).map(key => <Resource key={key} name={key} state={state} onDescribe={() => describe('describe_item', resourceLabels[key][0], `描述资源：${resourceLabels[key][0]}`, { target_type: 'resource', key })} />)}</div><div className="military"><span>⚔ {state.army.infantry + state.army.archers + state.army.cavalry}</span><span>组织 {state.army_status?.organization ?? 100}</span><span className="diplomacy-dot">{diplomacyLabel(state.diplomacy['血鸦'])} · 血鸦</span></div><div className="menu"><button onClick={() => setPanel('realm')}>领地详情</button><button onClick={openPopulationPanel}>居民分析</button><button onClick={() => describe('describe_realm', '领地描述', `描述领地：${state.realm_name}`, { target_type: 'realm' })}>描述领地</button><button onClick={() => setPanel('lord')}>领主详情</button><button onClick={() => describe('describe_lord', '领主描述', `描述领主：${state.lord_name}`, { target_type: 'lord' })}>描述领主</button><button onClick={() => setPanel('history')}>历史</button><button onClick={save}>保存</button><button onClick={load}>读取</button><button onClick={onBack}>退出</button></div></header>
    <section className="turn-strip"><span>第 {state.turn} 轮</span><i /> <span>第 {time?.calendar_day ?? 1} 日</span><i /> <span>{clock24(time)}</span><i /> <span>本轮第 {time?.day_in_turn ?? 1}/{time?.turn_days ?? 9} 日</span><i /> <span>{state.season}</span><i /> <span>{state.weather}</span><i /> <span>{modeLabel}</span>{activeScene && <span>已过 {activeScene.elapsed_days} 日 {activeScene.elapsed_hours} 时 {activeScene.elapsed_minutes ?? 0} 分</span>}<span className="engine-badge">{game.source === 'hermes' ? 'HERMES 已接管叙事' : '本地规则引擎'}</span></section>
    <div className="game-layout"><section className="story-column"><div className="report"><div className="report-top"><span>本轮报告</span><span className="wax">{busy ? '✦ Hermes 裁决中' : '✦ 已裁决'}</span></div><p>{streamText || game.narrative}</p><div className="secondary-stats"><Meter label="民心" value={state.resources.morale} /><Meter label="统治力" value={state.resources.authority} /><span>人口 <b>{state.resources.population}</b></span></div></div><AgentTracePanel trace={trace} collapsed={traceCollapsed} setCollapsed={setTraceCollapsed} running={busy} /><div className="prompt-box"><label>{activeScene ? `场景命令 · ${activeScene.title}` : '故事互动 / 场景命令'}</label><textarea value={command} onChange={e => setCommand(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }} placeholder={activeScene ? '例如：我命令卫兵把商队头领带到火盆前问话……' : '例如：召见管家询问粮仓亏空，或点击“推进九天”结算战略回合……'} /><div className="composer-footer"><span>⌘ Enter 发送场景互动</span><div className="mode-actions">{!activeScene && <button className="ghost-button" type="button" onClick={startScene} disabled={busy}>开始场景</button>}{activeScene && <button className="ghost-button" type="button" onClick={endScene} disabled={busy}>结束场景</button>}<button className="ghost-button" type="button" onClick={advanceStrategicTurn} disabled={busy || !!activeScene}>推进九天</button><button className="primary-button compact" onClick={() => send()} disabled={busy}>{busy ? '裁决中…' : '场景互动 →'}</button></div></div></div><div className="suggestions">{game.suggestions.map(item => <button key={item} onClick={() => send(item)} disabled={busy}>+ {item}</button>)}</div></section>
      <div className="map-column">
        <div className="map-switch"><button type="button" className={mapMode === 'tactical' ? 'active' : ''} onClick={() => setMapMode('tactical')}>领地地图</button><button type="button" className={mapMode === 'diplomacy' ? 'active' : ''} onClick={() => setMapMode('diplomacy')}>外交地图</button></div>
        {mapMode === 'tactical' && <aside className="map-panel tactical-panel"><div className="map-head"><div><span className="section-label">领地地图</span><small>直辖地产与经营建筑 · 点击后自动描述</small></div><span>{realmMapSize}×{realmMapSize}</span></div><div className="coordinates" style={{ gridTemplateColumns: `repeat(${realmMapSize}, 1fr)` }}>{Array.from({ length: realmMapSize }, (_, index) => <span key={index}>{columnLabel(index)}</span>)}</div><div className="map-grid tactical-grid" style={{ gridTemplateColumns: `repeat(${realmMapSize}, 1fr)` }}>{Array.from({ length: realmMapSize * realmMapSize }, (_, index) => { const x = (index % realmMapSize) + 1, y = Math.floor(index / realmMapSize) + 1, tile = realmTiles.get(`${x}-${y}`)!; return <button title={`${coordLabel(x, y)} · ${tile.label}`} key={`${x}-${y}`} className={`tile ${tile.kind}`} onClick={() => openTileDrawer(tile, 'realm')}><span>{tileIcon(catalog, tile.kind)}</span></button> })}</div><div className="legend">{Object.entries(catalog?.map_tile_kinds ?? {}).filter(([kind]) => realmKinds.has(kind)).map(([kind, info]) => <span key={kind}><b style={{ color: info.color }}>{info.icon}</b>{info.label}</span>)}</div></aside>}
        {mapMode === 'diplomacy' && <aside className="map-panel diplomacy-panel"><div className="map-head"><div><span className="section-label">外交地图</span><small>大地理与势力领地 · 点击后自动描述</small></div><span>{Object.keys(state.diplomacy).length} 方势力</span></div><div className="coordinates" style={{ gridTemplateColumns: `repeat(${diplomacyMapSize}, 1fr)` }}>{Array.from({ length: diplomacyMapSize }, (_, index) => <span key={index}>{columnLabel(index)}</span>)}</div><div className="map-grid diplomacy-grid" style={{ gridTemplateColumns: `repeat(${diplomacyMapSize}, 1fr)` }}>{Array.from({ length: diplomacyMapSize * diplomacyMapSize }, (_, index) => { const x = (index % diplomacyMapSize) + 1, y = Math.floor(index / diplomacyMapSize) + 1, tile = diplomacyTiles.get(`${x}-${y}`) ?? { x, y, kind: 'grass', label: '草地', owner: null }; const owner = tile.owner ? catalog?.factions?.[tile.owner] : null; const style = owner ? { background: `${owner.color}3d`, borderColor: owner.color, color: owner.color } : undefined; return <button title={`${coordLabel(x, y)} · ${tile.label}${tile.owner ? ` · ${tile.owner}` : ''}`} key={`${x}-${y}`} className={`tile diplomacy-tile ${tile.owner ? 'owned' : 'unowned'}`} style={style} onClick={() => openTileDrawer(tile, 'diplomacy')}><span>{owner?.banner ?? diplomacyTileIcon(catalog, tile.kind)}</span></button> })}</div><div className="legend faction-legend">{Object.entries(state.diplomacy).map(([name, value]) => { const info = catalog?.factions?.[name]; return <button key={name} type="button" className="faction-chip" onClick={() => setFactionDetail(name)}><b style={{ color: info?.color ?? '#8a8a8a' }}>{info?.banner ?? '⚑'}</b>{name} · {diplomacyLabel(value)}</button> })}</div></aside>}
      </div>
    </div>
    {description.open && <DescriptionDrawer description={description} close={() => setDescription(previous => ({ ...previous, open: false }))} />}{panel && panel !== 'population' && <DetailPanel panel={panel} state={state} close={() => setPanel(null)} />}{panel === 'population' && <PopulationAnalysisPanel demographics={demographics} catalog={catalog} loading={demographicsLoading} error={demographicsError} close={() => setPanel(null)} />}
    {tileDetail && <TileDetailDrawer detail={tileDetail} catalog={catalog} close={() => setTileDetail(null)} onRefresh={() => openTileDrawer(tileDetail.tile, tileDetail.source)} onViewFaction={(faction) => { setFactionDetail(faction) }} />}
    {factionDetail && <FactionDetailPanel faction={factionDetail} detail={buildFactionDetail(state, catalog, factionDetail)} close={() => setFactionDetail(null)} />}
    {toast && <div className="toast" onAnimationEnd={() => setToast('')}>{toast}</div>}
  </main>
}
function Resource({ name, state, onDescribe }: { name: keyof typeof resourceLabels; state: GameState; onDescribe?: () => void }) { const [label, symbol] = resourceLabels[name]; const change = state.changes[name] ?? 0; return <button className="resource resource-button" type="button" onClick={onDescribe} title={`描述${label}`}><small>{symbol} {label}</small><b>{state.resources[name as keyof GameState['resources']]}</b>{change !== 0 && <em className={change > 0 ? 'up' : 'down'}>{change > 0 ? '+' : ''}{change}</em>}</button> }
function AgentTracePanel({ trace, collapsed, setCollapsed, running }: { trace: AgentTraceEvent[]; collapsed: boolean; setCollapsed: (value: boolean) => void; running: boolean }) {
  return <section className="agent-trace"><button className="trace-head" type="button" onClick={() => setCollapsed(!collapsed)}><span>Hermes Trace</span><small>{running ? '运行中' : '空闲'} · {trace.length} 条</small><b>{collapsed ? '展开' : '收起'}</b></button>{!collapsed && <div className="trace-list">{trace.length ? trace.map(item => <div className={`trace-item ${item.status ?? ''}`} key={item.id}><span>{traceMark(item.kind)}</span><div><strong>{item.title}</strong>{item.detail && <p>{item.detail}</p>}</div></div>) : <p className="empty-trace">尚无 Hermes run 事件。</p>}</div>}</section>
}
function DescriptionDrawer({ description, close }: { description: DescriptionState; close: () => void }) {
  const markdown = description.text || (description.loading ? 'Hermes 正在观察与书写……' : '暂无描述。')
  return <aside className="description-drawer"><div className="drawer-card"><button className="close" onClick={close}>×</button><span className="section-label">Hermes 描述者</span><h2>{description.title}</h2><div className="markdown-description"><ReactMarkdown skipHtml>{markdown}</ReactMarkdown></div><AgentTracePanel trace={description.trace} collapsed={false} setCollapsed={() => undefined} running={description.loading} /></div></aside>
}
function Meter({ label, value }: { label: string; value: number }) { return <span className="meter"><small>{label}</small><b>{value}</b><i><i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></i></span> }
function DetailPanel({ panel, state, close }: { panel: 'realm' | 'lord' | 'history'; state: GameState; close: () => void }) { const title = panel === 'realm' ? '领地档案' : panel === 'lord' ? '领主档案' : '编年史'; const body = panel === 'realm' ? <><p>生效法令：{state.laws.length ? state.laws.join('、') : '无'}</p><p>建筑：{buildingSummary(state.buildings)}</p><p>外交：{Object.entries(state.diplomacy).map(([name,status]) => `${name}[${diplomacyLabel(status)}]`).join(' · ')}</p></> : panel === 'lord' ? <><p><b>{state.lord_name}</b> · {state.lord_gender}</p><p>{state.appearance || '尚未留下外貌记述。'}</p><p>{state.personality || '尚未留下性格记述。'}</p><p>天赋：{state.talents.map(t => t.name).join('、')}</p></> : <p>第 {state.turn} 轮 · {state.season} · {state.weather}<br/>重要的裁决将会记录在这里。</p>; return <div className="modal-shade"><section className="detail-modal"><button className="close" onClick={close}>×</button><span className="section-label">{title}</span>{body}</section></div> }
function PopulationAnalysisPanel({ demographics, catalog, loading, error, close }: { demographics: DemographicsResponse | null; catalog: Catalog | null; loading: boolean; error: string; close: () => void }) {
  const data = demographics?.demographics
  const classes = data ? Object.entries(data.classes) : []
  const totalPopulation = classes.reduce((total, [, item]) => total + item.population, 0)
  return <div className="modal-shade"><section className="detail-modal population-analysis">
    <button className="close" onClick={close}>×</button>
    <span className="section-label">居民分析</span>
    <h2>领民阶级与民生结构</h2>
    {loading && <p>书记官正在翻检户籍、产籍与产婆账册……</p>}
    {error && <p className="error">{error}</p>}
    {!loading && !error && data && <>
      <div className="population-summary">
        <StatCard label="总人口" value={totalPopulation} />
        <StatCard label="阶级数" value={classes.length} />
        <StatCard label="住房容量" value={data.housing.total_capacity} />
        <StatCard label="已住/空余" value={`${data.housing.total_occupied}/${data.housing.total_vacant}`} />
        <StatCard label="上轮出生" value={data.last_births} />
        <StatCard label="迁入/流失" value={`${data.last_migration}/${data.last_outflow}`} />
      </div>
      <div className="population-table-wrap">
        <table className="population-table">
          <thead><tr><th>阶级</th><th>人口</th><th>男/女</th><th>年龄</th><th>孕妇</th><th>生产力</th><th>财富</th><th>税/支</th><th>出生率</th><th>民心</th><th>住房</th></tr></thead>
          <tbody>{classes.map(([classId, item]) => <PopulationClassRow key={classId} classId={classId} item={item} catalog={catalog?.population_classes?.[classId]} />)}</tbody>
        </table>
      </div>
      <h3>孕妇月龄</h3>
      <div className="pregnancy-grid">{classes.map(([classId, item]) => <div className="pregnancy-card" key={classId}><b>{item.name}</b><span>{Array.from({ length: 10 }, (_, index) => item.pregnancy[String(index + 1)] ?? 0).join(' / ')}</span></div>)}</div>
      <h3>住房分析</h3>
      <div className="population-table-wrap">
        <table className="population-table housing-table">
          <thead><tr><th>住房类型</th><th>容量</th><th>已住</th><th>空余</th><th>质量</th></tr></thead>
          <tbody>{Object.entries(data.housing.by_type).map(([type, item]) => <tr key={type}><td>{housingLabel(type)}</td><td>{item.capacity}</td><td>{item.occupied}</td><td>{item.vacant}</td><td>{item.quality}</td></tr>)}</tbody>
        </table>
      </div>
    </>}
    {!loading && !error && !data && <p>暂无居民分析数据。</p>}
  </section></div>
}
function StatCard({ label, value }: { label: string; value: string | number }) { return <div className="stat-card"><small>{label}</small><b>{value}</b></div> }
function PopulationClassRow({ classId, item, catalog }: { classId: string; item: PopulationClassState; catalog?: PopulationClassCatalog }) {
  const pregnantTotal = sumNumbers(item.pregnancy)
  const nextWealth = catalog ? item.wealth_per_capita + catalog.productivity - catalog.tax - catalog.expense : null
  return <tr>
    <td><b>{item.name}</b><small>{classId}</small></td>
    <td>{item.population}</td>
    <td>{item.sex.male}/{item.sex.female}<small>{percent(item.sex.female, item.population)} 女</small></td>
    <td>幼 {item.age.child} / 劳 {item.age.working} / 老 {item.age.elder}<small>劳力 {percent(item.age.working, item.population)}</small></td>
    <td>{pregnantTotal}<small>1-10 月龄见下</small></td>
    <td>{catalog?.productivity ?? '-'}</td>
    <td>{item.wealth_per_capita}<small>{nextWealth === null ? '' : `预计 ${nextWealth}`}</small></td>
    <td>{catalog ? `${catalog.tax}/${catalog.expense}` : '-'}</td>
    <td>{catalog ? `${(catalog.annual_birth_rate * 100).toFixed(1)}%` : '-'}</td>
    <td>{item.morale}</td>
    <td>{catalog?.housing_types?.map(housingLabel).join('、') || '-'}</td>
  </tr>
}
function TileDetailDrawer({ detail, catalog, close, onRefresh, onViewFaction }: { detail: TileDrawerState; catalog: Catalog | null; close: () => void; onRefresh: () => void; onViewFaction: (faction: string) => void }) {
  const { tile, source } = detail
  const info = source === 'diplomacy' ? diplomacyTileInfo(catalog, tile.kind) : realmTileInfo(catalog, tile.kind)
  const owner = tile.owner ? catalog?.factions?.[tile.owner] : null
  const ownerLabel = tile.owner ? <><b style={{ color: owner?.color }}>{owner?.banner ?? '⚑'} {tile.owner}</b></> : source === 'realm' ? '领地直辖' : '未被明确控制'
  const markdown = detail.text || (detail.loading ? 'Hermes 正在观察这块土地……' : '暂无地块描述。')
  return <aside className="description-drawer tile-detail-drawer"><div className="drawer-card">
    <button className="close" onClick={close}>×</button>
    <span className="section-label">{source === 'realm' ? '领地地块' : '外交地块'} · {coordLabel(tile.x, tile.y)}</span>
    <h2>{info?.icon ?? tileIcon(catalog, tile.kind)} {tile.label}</h2>
    <div className="tile-meta">
      <p>类型：{categoryLabel(info?.category)}</p>
      <p>归属：{ownerLabel}</p>
      {info?.description && <p>{info.description}</p>}
    </div>
    <div className="detail-actions">
      {tile.owner && <button type="button" className="ghost-button" onClick={() => onViewFaction(tile.owner!)}>查看外交详情</button>}
      <button type="button" className="ghost-button" onClick={onRefresh} disabled={detail.loading}>{detail.loading ? '描述中…' : '重新描述'}</button>
    </div>
    <div className="markdown-description tile-description"><ReactMarkdown skipHtml>{markdown}</ReactMarkdown></div>
    <AgentTracePanel trace={detail.trace} collapsed={false} setCollapsed={() => undefined} running={detail.loading} />
  </div></aside>
}
function FactionDetailPanel({ faction, detail, close }: { faction: string; detail: FactionDetail; close: () => void }) {
  const relationPercent = Math.max(0, Math.min(100, (detail.relation + 100) / 2))
  return <div className="modal-shade"><section className="detail-modal faction-detail">
    <button className="close" onClick={close}>×</button>
    <span className="section-label">外交势力详情</span>
    <p><b style={{ color: detail.color }}>{detail.banner} {faction}</b></p>
    {detail.description && <p>{detail.description}</p>}
    <p>姿态：<b style={{ color: detail.color }}>{detail.stance}</b>{detail.at_war && ' · 战争状态'}</p>
    <p className="meter"><small>关系值 {detail.relation}</small><i><i style={{ width: `${relationPercent}%`, background: detail.color }} /></i></p>
    <p>条约：{detail.treaties.length ? detail.treaties.map(t => `${t.name}（剩余 ${t.remaining_turns} 轮）`).join('、') : '无'}</p>
    <p>领地：{detail.owned_tile_count} 处{detail.owned_tile_count > 0 && `（${detail.owned_tiles.map(t => coordLabel(t.x, t.y)).join('、')}）`}</p>
  </section></div>
}
function parseAgentEvent(data: string): AgentSseEvent { try { return JSON.parse(data) as AgentSseEvent } catch { return { event: 'run.event', message: data } } }
function traceFromAgentEvent(event: AgentSseEvent): AgentTraceEvent | null {
  const name = String(event.event || event.type || 'run.event')
  const seq = String(event.seq ?? Date.now())
  if (name === 'message.delta') return null
  if (name === 'reasoning.available') return { id: `reasoning-${seq}`, kind: 'reasoning', title: '推理片段', detail: String(event.text || event.message || ''), status: 'complete' }
  if (name.startsWith('tool.')) return { id: `tool-${seq}`, kind: 'tool', title: name === 'tool.started' ? '工具调用开始' : '工具调用完成', detail: String(event.message || event.name || event.command || ''), status: name === 'tool.started' ? 'running' : name.endsWith('failed') ? 'error' : 'complete' }
  if (name.startsWith('approval.')) return { id: `approval-${seq}`, kind: 'approval', title: name === 'approval.request' ? '审批请求' : '审批响应', detail: String(event.message || event.choice || ''), status: name === 'approval.request' ? 'pending' : 'complete' }
  if (name.startsWith('clarify.')) return { id: `clarify-${seq}`, kind: 'clarify', title: name === 'clarify.request' ? '澄清请求' : '澄清响应', detail: String(event.message || event.response || ''), status: name === 'clarify.request' ? 'pending' : 'complete' }
  if (name.startsWith('state.action_')) return { id: `state-${seq}`, kind: 'state_action', title: name === 'state.action_applied' ? '状态变更已应用' : '状态变更被拒绝', detail: String(event.message || ''), status: name === 'state.action_applied' ? 'complete' : 'error' }
  if (name.startsWith('run.')) return { id: `run-${seq}`, kind: 'run', title: name, detail: String(event.message || event.error || ''), status: name === 'run.failed' ? 'error' : name === 'run.started' ? 'running' : 'complete' }
  return { id: `event-${seq}`, kind: 'message', title: name, detail: String(event.message || ''), status: 'complete' }
}
function traceMark(kind: AgentTraceEvent['kind']) { return kind === 'reasoning' ? '思' : kind === 'tool' ? '具' : kind === 'approval' ? '审' : kind === 'clarify' ? '问' : kind === 'state_action' ? '改' : kind === 'run' ? '行' : '讯' }
function extractNarrative(output: unknown): string {
  if (!output) return ''
  if (typeof output === 'object' && output && 'narrative' in output) return String((output as { narrative?: unknown }).narrative ?? '')
  if (typeof output !== 'string') return String(output)
  try {
    const parsed = JSON.parse(output)
    if (parsed && typeof parsed === 'object' && typeof parsed.narrative === 'string') return parsed.narrative
  } catch { /* keep raw output */ }
  return output
}
function extractSuggestions(output: unknown, fallback: string[]): string[] {
  if (typeof output !== 'string') return fallback
  try {
    const parsed = JSON.parse(output)
    return Array.isArray(parsed?.suggestions) ? parsed.suggestions.map(String) : fallback
  } catch { return fallback }
}
function draw(items: Talent[]) { return [...items].sort(() => Math.random() - .5).slice(0, 8) }
export default App
