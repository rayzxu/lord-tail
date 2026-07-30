import { FormEvent, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AgentRunMode, AgentSseEvent, AgentTraceEvent, api, Catalog, CharacterEntry, CharactersResponse, CharacterUpsertPayload, DemographicsResponse, DiplomacyState, FactionDetail, GameState, HistoryEntry, HistoryResponse, ItemCatalogEntry, ManagementDecision, ManagementMode, PopulationClassCatalog, PopulationClassState, RealmAnalysis, ScheduledEvent, ScheduledEventsResponse, Talent, Tile, TurnResult } from './api'
import CouncilPanel from './components/CouncilPanel'

const markdownPlugins = [remarkGfm]
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
  const playerFaction = Object.entries(state.factions ?? {}).find(([, info]) => info.is_player)?.[0] ?? state.realm_name
  const center = Math.max(1, Math.floor((size + 1) / 2))
  const playerTile = byCoord.get(`${center}-${center}`)
  if (playerTile) {
    playerTile.kind = 'castle'
    playerTile.label = `${playerFaction}城堡`
    playerTile.owner = playerFaction
  }
  const factions = Object.keys(state.diplomacy).filter(faction => faction !== playerFaction)
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
function namedNumberSummary(values: Record<string, number> | undefined, labels?: Record<string, [string, string]>, limit = 8) {
  const entries = Object.entries(values ?? {}).filter(([, value]) => Number(value) !== 0).slice(0, limit)
  return entries.length ? entries.map(([key, value]) => `${labels?.[key]?.[0] ?? key} ${value}`).join('、') : '无'
}
function courtText(value: unknown) {
  return String(value ?? '')
    .replaceAll('HERMES', '书记官')
    .replaceAll('Hermes', '书记官')
    .replaceAll('Agent', '书记官')
    .replaceAll('agent', '书记官')
    .replaceAll('SSE', '传信')
    .replaceAll('Trace', '手记')
    .replaceAll('trace', '手记')
    .replaceAll('run completed', '文书完成')
    .replaceAll('run failed', '文书受阻')
    .replaceAll('run cancelled', '文书停笔')
    .replaceAll('run 已终止', '文书已终止')
    .replaceAll('run', '文书')
}
function buildFactionDetail(state: GameState, catalog: Catalog | null, faction: string): FactionDetail {
  const dynamic = diplomacyState(state.diplomacy[faction])
  const info = state.factions?.[faction] ?? catalog?.factions?.[faction]
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
type NeighborSetup = { name: string; stance: string; relation: number; at_war: boolean; color: string; banner: string; description: string }
const setupMapSize = 10
const setupRealmForbiddenKinds = new Set(['hill', 'lake', 'river', 'town', 'village', 'slum', 'castle'])
function setupLabel(catalog: Catalog | null, kind: string, source: 'realm' | 'diplomacy') {
  return (source === 'diplomacy' ? diplomacyTileInfo(catalog, kind) : realmTileInfo(catalog, kind))?.label ?? kind
}
function setupBaseTiles(size = setupMapSize): Tile[] {
  return Array.from({ length: size * size }, (_, index) => ({ x: (index % size) + 1, y: Math.floor(index / size) + 1, kind: 'grass', label: '草地', owner: null }))
}
function initialSetupRealmMap(catalog: Catalog | null): Tile[] {
  const tiles = setupBaseTiles()
  const center = Math.max(1, Math.floor((setupMapSize + 1) / 2))
  return tiles.map(tile => {
    if (tile.x <= 2 && tile.y <= 3) return { ...tile, kind: 'forest', label: setupLabel(catalog, 'forest', 'realm') }
    if (tile.x === center && tile.y === center) return { ...tile, kind: 'castle', label: '领主堡垒' }
    if (tile.x === center && tile.y === center + 1) return { ...tile, kind: 'homes', label: setupLabel(catalog, 'homes', 'realm') }
    return tile
  })
}
function initialNeighbors(catalog: Catalog | null): NeighborSetup[] {
  return Object.entries(catalog?.factions ?? {}).map(([name, faction]) => {
    const dynamic = diplomacyState(catalog?.diplomacy?.[name] ?? '中立')
    return { name, stance: dynamic.stance, relation: dynamic.relation, at_war: dynamic.at_war, color: faction.color, banner: faction.banner, description: faction.description }
  })
}
function initialSetupDiplomacyMap(catalog: Catalog | null, neighbors: NeighborSetup[], playerFaction = '玩家'): Tile[] {
  const tiles = setupBaseTiles()
  const byCoord = new Map(tiles.map(tile => [`${tile.x}-${tile.y}`, tile]))
  const set = (x: number, y: number, kind: string, owner: string | null = null) => {
    const base = setupLabel(catalog, kind, 'diplomacy')
    const tile = byCoord.get(`${x}-${y}`)
    if (tile) Object.assign(tile, { kind, owner, label: owner ? `${owner}${base}` : base })
  }
  for (let y = 1; y <= 3; y += 1) for (let x = 1; x <= 2; x += 1) set(x, y, 'forest')
  for (let y = 1; y <= 2; y += 1) for (let x = setupMapSize - 1; x <= setupMapSize; x += 1) set(x, y, 'hill')
  for (let y = setupMapSize - 1; y <= setupMapSize; y += 1) for (let x = 1; x <= 2; x += 1) set(x, y, 'lake')
  for (let x = 3; x <= setupMapSize - 2; x += 1) set(x, setupMapSize, 'river')
  const center = Math.max(1, Math.floor((setupMapSize + 1) / 2))
  set(center, center, 'castle', playerFaction)
  const perimeter = [
    ...Array.from({ length: setupMapSize }, (_, index) => [index + 1, 1] as const),
    ...Array.from({ length: setupMapSize - 1 }, (_, index) => [setupMapSize, index + 2] as const),
    ...Array.from({ length: setupMapSize - 1 }, (_, index) => [setupMapSize - index - 1, setupMapSize] as const),
    ...Array.from({ length: setupMapSize - 2 }, (_, index) => [1, setupMapSize - index - 1] as const),
  ]
  const cycle = ['village', 'castle', 'town', 'slum']
  const step = neighbors.length ? Math.max(1, Math.floor(perimeter.length / neighbors.length)) : 1
  neighbors.forEach((neighbor, index) => {
    const [x, y] = perimeter[(index * step) % perimeter.length] ?? [1, 1]
    set(x, y, cycle[index % cycle.length], neighbor.name)
  })
  return Array.from(byCoord.values())
}
function neighborsToFactions(neighbors: NeighborSetup[]) {
  return Object.fromEntries(neighbors.filter(item => item.name.trim()).map(item => [item.name.trim(), { color: item.color, banner: item.banner, description: item.description }]))
}
function neighborsToDiplomacy(neighbors: NeighborSetup[]) {
  return Object.fromEntries(neighbors.filter(item => item.name.trim()).map(item => [item.name.trim(), { stance: item.at_war ? '战争' : item.stance, relation: Number(item.relation), at_war: item.at_war, treaties: [] }]))
}

function App() {
  const [view, setView] = useState<'setup' | 'game'>('setup')
  const [talents, setTalents] = useState<Talent[]>([])
  const [visibleTalents, setVisibleTalents] = useState<Talent[]>([])
  const [selected, setSelected] = useState<Talent[]>([])
  const [settings, setSettings] = useState(defaultSettings)
  const [neighbors, setNeighbors] = useState<NeighborSetup[]>([])
  const [realmSetupMap, setRealmSetupMap] = useState<Tile[]>([])
  const [diplomacySetupMap, setDiplomacySetupMap] = useState<Tile[]>([])
  const [setupMapMode, setSetupMapMode] = useState<'realm' | 'diplomacy'>('realm')
  const [realmBrush, setRealmBrush] = useState('grass')
  const [diplomacyBrush, setDiplomacyBrush] = useState('grass')
  const [ownerBrush, setOwnerBrush] = useState('')
  const [game, setGame] = useState<TurnResult | null>(null)
  const [error, setError] = useState('')
  const [catalog, setCatalog] = useState<Catalog | null>(null)

  useEffect(() => { api.talents().then(data => { setTalents(data); setVisibleTalents(draw(data)) }).catch(() => setError('无法连接后端，请先启动 FastAPI 服务。')) }, [])
  useEffect(() => {
    api.catalog().then(data => {
      setCatalog(data)
      const defaultNeighbors = initialNeighbors(data)
      setNeighbors(previous => previous.length ? previous : defaultNeighbors)
      setRealmSetupMap(previous => previous.length ? previous : initialSetupRealmMap(data))
      setDiplomacySetupMap(previous => previous.length ? previous : initialSetupDiplomacyMap(data, defaultNeighbors, settings.realm_name))
      setOwnerBrush(previous => previous || defaultNeighbors[0]?.name || '')
    }).catch(() => undefined)
  }, [])
  const newRoll = () => { setVisibleTalents(draw(talents)); setSelected([]) }

  async function begin(event: FormEvent) {
    event.preventDefault(); setError('')
    if (selected.length !== 2) return setError('请先选择两项命运赐福。')
    try {
      setGame(await api.start({
        ...settings,
        talents: selected,
        map_size: setupMapSize,
        factions: neighborsToFactions(neighbors),
        diplomacy: neighborsToDiplomacy(neighbors),
        realm_map: realmSetupMap,
        diplomacy_map: diplomacySetupMap,
      }))
      setView('game')
    }
    catch (e) { setError(e instanceof Error ? e.message : '开局失败') }
  }
  const update = (key: keyof Settings, value: string) => setSettings(previous => ({ ...previous, [key]: value }))
  const updateNeighbor = (index: number, patch: Partial<NeighborSetup>) => setNeighbors(previous => {
    const oldName = previous[index]?.name
    const updated = previous.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item)
    if (patch.name && oldName && patch.name !== oldName) {
      setDiplomacySetupMap(tiles => tiles.map(tile => tile.owner === oldName ? { ...tile, owner: patch.name || null, label: `${patch.name}${setupLabel(catalog, tile.kind, 'diplomacy')}` } : tile))
      if (ownerBrush === oldName) setOwnerBrush(patch.name)
    }
    return updated
  })
  const addNeighbor = () => {
    const next = `新邻居${neighbors.length + 1}`
    setNeighbors(previous => [...previous, { name: next, stance: '中立', relation: 0, at_war: false, color: '#8a8a8a', banner: '⚑', description: '' }])
    setOwnerBrush(previous => previous || next)
  }
  const removeNeighbor = (index: number) => setNeighbors(previous => {
    const removed = previous[index]?.name
    if (removed) setDiplomacySetupMap(tiles => tiles.map(tile => tile.owner === removed ? { ...tile, owner: null, label: setupLabel(catalog, tile.kind, 'diplomacy') } : tile))
    return previous.filter((_, itemIndex) => itemIndex !== index)
  })
  const resetSetupMap = (source: 'realm' | 'diplomacy') => {
    if (source === 'realm') setRealmSetupMap(initialSetupRealmMap(catalog))
    else setDiplomacySetupMap(initialSetupDiplomacyMap(catalog, neighbors, settings.realm_name))
  }
  const paintSetupTile = (source: 'realm' | 'diplomacy', tile: Tile) => {
    const center = Math.max(1, Math.floor((setupMapSize + 1) / 2))
    if (source === 'realm') {
      if (tile.x === center && tile.y === center) return
      setRealmSetupMap(tiles => tiles.map(item => item.x === tile.x && item.y === tile.y ? { ...item, kind: realmBrush, label: setupLabel(catalog, realmBrush, 'realm'), owner: null } : item))
      return
    }
    if (tile.x === center && tile.y === center) return
    const info = diplomacyTileInfo(catalog, diplomacyBrush)
    const owner = info?.category === 'settlement' ? ownerBrush || null : null
    setDiplomacySetupMap(tiles => tiles.map(item => item.x === tile.x && item.y === tile.y ? { ...item, kind: diplomacyBrush, label: owner ? `${owner}${setupLabel(catalog, diplomacyBrush, 'diplomacy')}` : setupLabel(catalog, diplomacyBrush, 'diplomacy'), owner } : item))
  }

  if (view === 'game' && game) return <GameScreen game={game} onGame={setGame} onBack={() => setView('setup')} catalog={catalog} />
  return <SetupScreen settings={settings} update={update} talents={visibleTalents} selected={selected} error={error} onRoll={newRoll} onToggle={(talent) => setSelected(previous => previous.some(t => t.id === talent.id) ? previous.filter(t => t.id !== talent.id) : previous.length < 2 ? [...previous, talent] : previous)} onSubmit={begin} catalog={catalog} neighbors={neighbors} updateNeighbor={updateNeighbor} addNeighbor={addNeighbor} removeNeighbor={removeNeighbor} setupMapMode={setupMapMode} setSetupMapMode={setSetupMapMode} realmSetupMap={realmSetupMap} diplomacySetupMap={diplomacySetupMap} realmBrush={realmBrush} setRealmBrush={setRealmBrush} diplomacyBrush={diplomacyBrush} setDiplomacyBrush={setDiplomacyBrush} ownerBrush={ownerBrush} setOwnerBrush={setOwnerBrush} paintSetupTile={paintSetupTile} resetSetupMap={resetSetupMap} />
}

function SetupScreen({ settings, update, talents, selected, error, onRoll, onToggle, onSubmit, catalog, neighbors, updateNeighbor, addNeighbor, removeNeighbor, setupMapMode, setSetupMapMode, realmSetupMap, diplomacySetupMap, realmBrush, setRealmBrush, diplomacyBrush, setDiplomacyBrush, ownerBrush, setOwnerBrush, paintSetupTile, resetSetupMap }: { settings: Settings; update: (key: keyof Settings, value: string) => void; talents: Talent[]; selected: Talent[]; error: string; onRoll: () => void; onToggle: (talent: Talent) => void; onSubmit: (event: FormEvent) => void; catalog: Catalog | null; neighbors: NeighborSetup[]; updateNeighbor: (index: number, patch: Partial<NeighborSetup>) => void; addNeighbor: () => void; removeNeighbor: (index: number) => void; setupMapMode: 'realm' | 'diplomacy'; setSetupMapMode: (mode: 'realm' | 'diplomacy') => void; realmSetupMap: Tile[]; diplomacySetupMap: Tile[]; realmBrush: string; setRealmBrush: (kind: string) => void; diplomacyBrush: string; setDiplomacyBrush: (kind: string) => void; ownerBrush: string; setOwnerBrush: (owner: string) => void; paintSetupTile: (source: 'realm' | 'diplomacy', tile: Tile) => void; resetSetupMap: (source: 'realm' | 'diplomacy') => void }) {
  const realmOptions = Object.entries(catalog?.map_tile_kinds ?? {}).filter(([kind]) => !setupRealmForbiddenKinds.has(kind))
  const diplomacyOptions = Object.entries(catalog?.diplomacy_tile_kinds ?? {})
  const activeTiles = setupMapMode === 'realm' ? realmSetupMap : diplomacySetupMap
  const activeBrush = setupMapMode === 'realm' ? realmBrush : diplomacyBrush
  const setActiveBrush = setupMapMode === 'realm' ? setRealmBrush : setDiplomacyBrush
  const activeOptions = setupMapMode === 'realm' ? realmOptions : diplomacyOptions
  return <main className="setup-page"><form className="setup-card" onSubmit={onSubmit}>
    <div className="eyebrow">THE LORD TAIL · CHRONICLES</div><h1>领主降临设定</h1><p className="lead">在潮湿的春季，写下这片领地的第一个名字。</p>
    <div className="form-grid"><Field label="领主姓名"><input value={settings.lord_name} onChange={e => update('lord_name', e.target.value)} required /></Field><Field label="领主身份"><select value={settings.lord_gender} onChange={e => update('lord_gender', e.target.value)}><option>男</option><option>女</option><option>非二元</option><option>未说明</option></select></Field></div>
    <Field label="领地名称"><input value={settings.realm_name} onChange={e => update('realm_name', e.target.value)} required /></Field>
    <Field label="领主外表"><textarea value={settings.appearance} onChange={e => update('appearance', e.target.value)} placeholder="衣着、神情、气质……" /></Field>
    <Field label="领主性格"><textarea value={settings.personality} onChange={e => update('personality', e.target.value)} placeholder="信念、野心与执政风格……" /></Field>
    <section className="talent-section"><div className="section-head"><div><span className="section-label">命运赐福</span><small>选择 2 项 · {selected.length}/2</small></div><button type="button" className="ghost-button" onClick={onRoll}>↻ 换一批</button></div><div className="talent-grid">{talents.map(talent => <button className={`talent ${selected.some(item => item.id === talent.id) ? 'selected' : ''}`} type="button" key={talent.id} onClick={() => onToggle(talent)}><span className="talent-mark">{selected.some(item => item.id === talent.id) ? '✦' : '○'}</span><span><strong>{talent.name}</strong><small>{talent.description}</small></span></button>)}</div></section>
    <section className="setup-section"><div className="section-head"><div><span className="section-label">外交设定</span><small>设定邻居势力、初始关系与描述</small></div><button type="button" className="ghost-button" onClick={addNeighbor}>+ 新增邻居</button></div><div className="neighbor-list">{neighbors.map((neighbor, index) => <div className="neighbor-card" key={`${neighbor.name}-${index}`}><div className="neighbor-main"><input value={neighbor.banner} onChange={e => updateNeighbor(index, { banner: e.target.value })} aria-label="旗帜" /><input value={neighbor.name} onChange={e => updateNeighbor(index, { name: e.target.value })} aria-label="势力名" /><select value={neighbor.at_war ? '战争' : neighbor.stance} onChange={e => updateNeighbor(index, { stance: e.target.value, at_war: e.target.value === '战争', relation: e.target.value === '战争' ? -100 : neighbor.relation })}><option>友善</option><option>中立</option><option>敌对</option><option>战争</option></select><input type="number" min="-100" max="100" value={neighbor.relation} onChange={e => updateNeighbor(index, { relation: Number(e.target.value) })} aria-label="关系值" /><input type="color" value={neighbor.color} onChange={e => updateNeighbor(index, { color: e.target.value })} aria-label="颜色" /><button type="button" className="ghost-button" onClick={() => removeNeighbor(index)}>删除</button></div><textarea value={neighbor.description} onChange={e => updateNeighbor(index, { description: e.target.value })} placeholder="这个邻居的地理、政治、贸易或军事设定……" /></div>)}</div></section>
    <section className="setup-section"><div className="section-head"><div><span className="section-label">地图编辑器</span><small>领地地图用于直辖经营；外交地图用于大地理与势力归属</small></div><button type="button" className="ghost-button" onClick={() => resetSetupMap(setupMapMode)}>重置当前地图</button></div><div className="map-switch setup-map-switch"><button type="button" className={setupMapMode === 'realm' ? 'active' : ''} onClick={() => setSetupMapMode('realm')}>领地地图编辑器</button><button type="button" className={setupMapMode === 'diplomacy' ? 'active' : ''} onClick={() => setSetupMapMode('diplomacy')}>外交地图编辑器</button></div><div className="setup-editor-toolbar"><Field label="地块类型"><select value={activeBrush} onChange={e => setActiveBrush(e.target.value)}>{activeOptions.map(([kind, info]) => <option key={kind} value={kind}>{info.icon} {info.label}</option>)}</select></Field>{setupMapMode === 'diplomacy' && <Field label="归属势力"><select value={ownerBrush} onChange={e => setOwnerBrush(e.target.value)}><option value="">无归属</option>{neighbors.map(neighbor => <option key={neighbor.name} value={neighbor.name}>{neighbor.banner} {neighbor.name}</option>)}</select></Field>}<p>{setupMapMode === 'realm' ? '中心格固定为领主堡垒；领地地图不会提交外交势力归属。' : '只有城镇、城堡、农村、流民窝棚等聚落地块会写入归属势力。'}</p></div><SetupMapPreview catalog={catalog} source={setupMapMode} tiles={activeTiles} neighbors={neighbors} onPaint={tile => paintSetupTile(setupMapMode, tile)} /></section>
    {error && <div className="error">{error}</div>}<button className="primary-button" type="submit">写下开局剧本 <span>→</span></button>
  </form></main>
}
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="field"><span>{label}</span>{children}</label> }

function SetupMapPreview({ catalog, source, tiles, neighbors, onPaint }: { catalog: Catalog | null; source: 'realm' | 'diplomacy'; tiles: Tile[]; neighbors: NeighborSetup[]; onPaint: (tile: Tile) => void }) {
  const byCoord = new Map(tiles.map(tile => [`${tile.x}-${tile.y}`, tile]))
  const center = Math.max(1, Math.floor((setupMapSize + 1) / 2))
  return <div className="setup-map-preview"><div className="coordinates" style={{ gridTemplateColumns: `repeat(${setupMapSize}, 1fr)` }}>{Array.from({ length: setupMapSize }, (_, index) => <span key={index}>{columnLabel(index)}</span>)}</div><div className="map-grid setup-grid" style={{ gridTemplateColumns: `repeat(${setupMapSize}, 1fr)` }}>{Array.from({ length: setupMapSize * setupMapSize }, (_, index) => { const x = (index % setupMapSize) + 1, y = Math.floor(index / setupMapSize) + 1, tile = byCoord.get(`${x}-${y}`) ?? { x, y, kind: 'grass', label: '草地', owner: null }; const owner = tile.owner ? neighbors.find(item => item.name === tile.owner) : null; const style = owner ? { background: `${owner.color}3d`, borderColor: owner.color, color: owner.color } : undefined; return <button type="button" title={`${coordLabel(x, y)} · ${tile.label}${tile.owner ? ` · ${tile.owner}` : ''}`} key={`${x}-${y}`} className={`tile ${source === 'diplomacy' ? 'diplomacy-tile' : ''} ${tile.kind} ${x === center && y === center ? 'locked' : ''}`} style={style} onClick={() => onPaint(tile)}><span>{tile.owner && !owner ? '♜' : owner?.banner ?? (source === 'diplomacy' ? diplomacyTileIcon(catalog, tile.kind) : tileIcon(catalog, tile.kind))}</span></button> })}</div><div className="legend">{Array.from(new Set(tiles.map(tile => tile.kind))).map(kind => { const info = source === 'diplomacy' ? diplomacyTileInfo(catalog, kind) : realmTileInfo(catalog, kind); return <span key={kind}><b style={{ color: info?.color }}>{info?.icon ?? fallbackIcon[kind] ?? '·'}</b>{info?.label ?? kind}</span> })}</div></div>
}

type DescriptionState = { open: boolean; title: string; text: string; trace: AgentTraceEvent[]; loading: boolean }
type TileDrawerState = { tile: Tile; source: 'realm' | 'diplomacy'; text: string; trace: AgentTraceEvent[]; loading: boolean }
type TileDescriptionCacheEntry = { signature: string; text: string; trace: AgentTraceEvent[] }
type EquipmentOwner = { type: 'lord' } | { type: 'character'; characterId: string }

function GameScreen({ game, onGame, onBack, catalog }: { game: TurnResult; onGame: (game: TurnResult) => void; onBack: () => void; catalog: Catalog | null }) {
  const [command, setCommand] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')
  const [panel, setPanel] = useState<'realm' | 'population' | 'lord' | 'characters' | 'history' | 'events' | 'strategy' | null>(null)
  const [demographics, setDemographics] = useState<DemographicsResponse | null>(null)
  const [demographicsLoading, setDemographicsLoading] = useState(false)
  const [demographicsError, setDemographicsError] = useState('')
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [events, setEvents] = useState<ScheduledEventsResponse | null>(null)
  const [eventsLoading, setEventsLoading] = useState(false)
  const [eventsError, setEventsError] = useState('')
  const [characters, setCharacters] = useState<CharactersResponse | null>(null)
  const [charactersLoading, setCharactersLoading] = useState(false)
  const [charactersError, setCharactersError] = useState('')
  const [strategyAnalysis, setStrategyAnalysis] = useState<RealmAnalysis | null>(null)
  const [strategyDecision, setStrategyDecision] = useState<ManagementDecision | null>(null)
  const [strategyLoading, setStrategyLoading] = useState(false)
  const [strategyError, setStrategyError] = useState('')
  const [trace, setTrace] = useState<AgentTraceEvent[]>(game.trace ?? [])
  const [traceCollapsed, setTraceCollapsed] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [description, setDescription] = useState<DescriptionState>({ open: false, title: '', text: '', trace: [], loading: false })
  const [tileDetail, setTileDetail] = useState<TileDrawerState | null>(null)
  const [tileDescriptionCache, setTileDescriptionCache] = useState<Record<string, TileDescriptionCacheEntry>>({})
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

  function tileCacheKey(tile: Tile, source: 'realm' | 'diplomacy') {
    return `${source}:${tile.x}:${tile.y}`
  }

  function tileDescriptionSignature(tile: Tile, source: 'realm' | 'diplomacy') {
    const tiles = source === 'diplomacy' ? diplomacyTiles : realmTiles
    const snapshotTile = (x: number, y: number) => {
      const item = tiles.get(`${x}-${y}`)
      return item ? { x: item.x, y: item.y, kind: item.kind, label: item.label, owner: item.owner ?? null } : { x, y, kind: null, label: null, owner: null }
    }
    return JSON.stringify({
      source,
      season: state.season,
      weather: state.weather,
      center: snapshotTile(tile.x, tile.y),
      north: snapshotTile(tile.x, tile.y - 1),
      south: snapshotTile(tile.x, tile.y + 1),
      west: snapshotTile(tile.x - 1, tile.y),
      east: snapshotTile(tile.x + 1, tile.y),
    })
  }

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
          const output = extractNarrative(event.output) || accumulated || '书记官已经完成裁决，但没有留下叙事文本。'
          const suggestions = extractSuggestions(event.output, game.suggestions)
          setStreamText('')
          const refreshed = await api.state.read()
          onGame({ ...game, state: refreshed.state, narrative: output, suggestions, source: 'hermes', run_id: run.run_id, trace: collectedTrace })
          setBusy(false)
        }
        if (event.event === 'run.failed' || event.event === 'run.cancelled') {
          source.close()
          setToast(courtText(event.message || event.error || '书记官文书已终止'))
          setBusy(false)
        }
      }
      source.onerror = () => {
        source.close()
        setToast('书记官传信中断')
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
          const text = extractNarrative(event.output) || accumulated || '书记官没有留下描述文本。'
          setDescription(previous => ({ ...previous, text, loading: false }))
        }
        if (event.event === 'run.failed' || event.event === 'run.cancelled') {
          source.close()
          setDescription(previous => ({ ...previous, loading: false }))
          setToast(courtText(event.message || event.error || '描述文书已终止'))
        }
      }
      source.onerror = () => {
        source.close()
        setDescription(previous => ({ ...previous, loading: false }))
        setToast('书记官描述传信中断')
      }
    } catch (e) {
      setDescription(previous => ({ ...previous, loading: false, text: e instanceof Error ? e.message : '书记官暂不可用' }))
    }
  }

  async function openTileDrawer(tile: Tile, source: 'realm' | 'diplomacy' = 'realm', forceRefresh = false) {
    const tiles = source === 'diplomacy' ? diplomacyTiles : realmTiles
    const currentTile = tiles.get(`${tile.x}-${tile.y}`) ?? tile
    const coord = coordLabel(currentTile.x, currentTile.y)
    const cacheKey = tileCacheKey(currentTile, source)
    const signature = tileDescriptionSignature(currentTile, source)
    const cached = tileDescriptionCache[cacheKey]
    if (!forceRefresh && cached?.signature === signature) {
      setTileDetail({ tile: currentTile, source, text: cached.text, trace: cached.trace, loading: false })
      return
    }
    const updateIfCurrent = (updater: (previous: TileDrawerState) => TileDrawerState) => {
      setTileDetail(previous => {
        if (!previous || previous.source !== source || previous.tile.x !== currentTile.x || previous.tile.y !== currentTile.y) return previous
        return updater(previous)
      })
    }
    setTileDetail({ tile: currentTile, source, text: '', trace: [], loading: true })
    try {
      const run = await api.agent.startRun({
        mode: 'describe_tile',
        input: `描述地图格 ${coord}：${currentTile.label}`,
        client_context: { selected_tile: { x: currentTile.x, y: currentTile.y, map_source: source }, map_source: source, tile: currentTile },
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
          const text = extractNarrative(event.output) || accumulated || '书记官没有留下地块描述。'
          setTileDescriptionCache(previous => ({ ...previous, [cacheKey]: { signature, text, trace: collectedTrace } }))
          updateIfCurrent(previous => ({ ...previous, text, loading: false }))
        }
        if (event.event === 'run.failed' || event.event === 'run.cancelled') {
          eventSource.close()
          updateIfCurrent(previous => ({ ...previous, loading: false }))
          setToast(courtText(event.message || event.error || '地块描述文书已终止'))
        }
      }
      eventSource.onerror = () => {
        eventSource.close()
        updateIfCurrent(previous => ({ ...previous, loading: false }))
        setToast('书记官地块传信中断')
      }
    } catch (e) {
      updateIfCurrent(previous => ({ ...previous, loading: false, text: e instanceof Error ? e.message : '书记官地块描述暂不可用' }))
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
  async function openHistoryPanel() {
    setPanel('history')
    setHistoryLoading(true)
    setHistoryError('')
    try {
      setHistory(await api.history('?limit=80&visibility=player'))
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : '编年史读取失败')
    } finally {
      setHistoryLoading(false)
    }
  }
  async function openEventsPanel() {
    setPanel('events')
    setEventsLoading(true)
    setEventsError('')
    try {
      setEvents(await api.events('?limit=80&visibility=player'))
    } catch (e) {
      setEventsError(e instanceof Error ? e.message : '事件读取失败')
    } finally {
      setEventsLoading(false)
    }
  }
  async function openCharactersPanel() {
    setPanel('characters')
    setCharactersLoading(true)
    setCharactersError('')
    try {
      setCharacters(await api.characters('?include_inactive=true'))
    } catch (e) {
      setCharactersError(e instanceof Error ? e.message : '人物账册读取失败')
    } finally {
      setCharactersLoading(false)
    }
  }
  async function openStrategyPanel() {
    setPanel('strategy')
    setStrategyLoading(true)
    setStrategyError('')
    setStrategyDecision(state.management_ai?.pending_advice ?? null)
    try {
      const response = await api.strategy.analysis()
      setStrategyAnalysis(response.analysis)
    } catch (e) {
      setStrategyError(e instanceof Error ? e.message : '领地战略分析读取失败')
    } finally {
      setStrategyLoading(false)
    }
  }
  async function resolveCouncil(proposalId: string, mode: ManagementMode) {
    const meeting = state.council?.current_meeting
    if (!meeting) return
    setStrategyLoading(true)
    try {
      const response = await api.council.resolve(meeting.id, { proposal_id: proposalId, management_mode: mode })
      applyStateApiResult(response)
      setStrategyAnalysis((await api.strategy.analysis()).analysis)
      setStrategyDecision(null)
      setToast(`方针已经确立：${response.directive.title}`)
    } catch (e) {
      setStrategyError(e instanceof Error ? e.message : '议会裁定失败')
    } finally {
      setStrategyLoading(false)
    }
  }
  async function changeManagementMode(mode: ManagementMode) {
    setStrategyLoading(true)
    try {
      const response = await api.strategy.setMode(mode)
      applyStateApiResult(response)
      if (mode !== 'advisory') setStrategyDecision(null)
      setToast(`管理方式已改为：${mode}`)
    } catch (e) {
      setStrategyError(e instanceof Error ? e.message : '管理方式修改失败')
    } finally {
      setStrategyLoading(false)
    }
  }
  async function requestCouncilReview() {
    setStrategyLoading(true)
    try {
      const response = await api.council.requestReview()
      applyStateApiResult(response)
      setStrategyDecision(null)
      setToast('大臣已经入厅，等待领主裁定')
    } catch (e) {
      setStrategyError(e instanceof Error ? e.message : '召集议会失败')
    } finally {
      setStrategyLoading(false)
    }
  }
  async function loadManagementAdvice() {
    setStrategyLoading(true)
    try {
      const response = await api.strategy.advice()
      setStrategyDecision(response.decision)
    } catch (e) {
      setStrategyError(e instanceof Error ? e.message : '顾问方案生成失败')
    } finally {
      setStrategyLoading(false)
    }
  }
  async function acceptManagementAdvice(decisionId: string, actionId: string) {
    setStrategyLoading(true)
    try {
      const response = await api.strategy.acceptAdvice(decisionId, actionId)
      applyStateApiResult(response)
      setStrategyDecision(response.decision)
      setToast('顾问行动已经盖印，将在推进九天时执行')
    } catch (e) {
      setStrategyError(e instanceof Error ? e.message : '顾问行动确认失败')
    } finally {
      setStrategyLoading(false)
    }
  }
  async function createCharacter(payload: CharacterUpsertPayload) {
    const result = await api.state.characters.upsert(payload)
    onGame({ ...game, state: result.state, narrative: result.narrative || game.narrative, suggestions: result.suggestions ?? game.suggestions, source: result.source ?? 'state-api', trace: result.trace ?? game.trace })
    setCharacters(await api.characters('?include_inactive=true'))
    setToast(`人物已加入账册：${result.character.name}`)
  }
  function applyStateApiResult(result: TurnResult) {
    onGame({
      ...game,
      state: result.state,
      narrative: result.narrative || game.narrative,
      suggestions: result.suggestions ?? game.suggestions,
      source: result.source ?? 'state-api',
      events: result.events ?? game.events,
      trace: result.trace ?? game.trace,
    })
  }
  async function refreshCharacterLedgerIfNeeded(owner: EquipmentOwner) {
    if (owner.type === 'character') setCharacters(await api.characters('?include_inactive=true'))
  }
  async function grantEquipmentItem(owner: EquipmentOwner, itemId: string, quantity: number) {
    const result = owner.type === 'lord'
      ? await api.state.lord.grantItem({ item_id: itemId, quantity, created_by: 'player' })
      : await api.state.characters.grantItem(owner.characterId, { item_id: itemId, quantity, created_by: 'player' })
    applyStateApiResult(result)
    await refreshCharacterLedgerIfNeeded(owner)
    setToast('物品已入账')
  }
  async function equipEquipmentItem(owner: EquipmentOwner, itemId: string, slot: string) {
    const result = owner.type === 'lord'
      ? await api.state.lord.equip({ item_id: itemId, slot, auto_add: true, created_by: 'player' })
      : await api.state.characters.equip(owner.characterId, { item_id: itemId, slot, auto_add: true, created_by: 'player' })
    applyStateApiResult(result)
    await refreshCharacterLedgerIfNeeded(owner)
    setToast('装备已更新')
  }
  async function unequipEquipmentItem(owner: EquipmentOwner, slot: string, itemId = '') {
    const result = owner.type === 'lord'
      ? await api.state.lord.unequip({ slot, item_id: itemId, created_by: 'player' })
      : await api.state.characters.unequip(owner.characterId, { slot, item_id: itemId, created_by: 'player' })
    applyStateApiResult(result)
    await refreshCharacterLedgerIfNeeded(owner)
    setToast('装备已卸下')
  }
  async function patchBodyProfile(owner: EquipmentOwner, availableSlots: string[]) {
    const payload = { values: { available_slots: availableSlots }, created_by: 'player' }
    const result = owner.type === 'lord'
      ? await api.state.lord.patchComponent('body_profile', payload)
      : await api.state.characters.patchComponent(owner.characterId, 'body_profile', payload)
    applyStateApiResult(result)
    await refreshCharacterLedgerIfNeeded(owner)
    setToast('身体槽位已更新')
  }
  async function startCharacterScene(character: CharacterEntry, sceneType: 'dialogue' | 'sexual') {
    if (busy) return
    if (sceneType === 'sexual') {
      const age = Number(character.age)
      if (!Number.isFinite(age) || age < 18) {
        setToast('成人场景需要人物年龄明确且不少于 18 岁')
        return
      }
    }
    const title = sceneType === 'sexual' ? `领主与${character.name}的成人场景` : `领主召见${character.name}`
    try {
      const started = await api.scenes.start({
        type: sceneType === 'sexual' ? 'sexual' : 'dialogue',
        title,
        participants: [
          { type: 'lord', name: state.lord_name },
          { type: 'character', id: character.id, name: character.name, role: character.role, age: character.age },
        ],
        flags: sceneType === 'sexual'
          ? { adult_scene: true, sexual_scene: true, requires_adult_participants: true, character_id: character.id }
          : { character_id: character.id },
      })
      onGame(started)
      setPanel(null)
      setCommand(sceneType === 'sexual'
        ? `领主 ${state.lord_name} 与 ${character.name} 进入成人/性爱场景。请先确认参与者均为成年人，并以中世纪游戏叙事推进互动；如果发生实际关系，请在剧情推进过程中调用人物性经历和内容物 API 记录结构化后果。`
        : `领主 ${state.lord_name} 召见 ${character.name} 进行交流。请根据人物账册、双方关系和当前领地状态推进对话。`)
      setToast(sceneType === 'sexual' ? '成人场景已创建，首轮命令已填入' : '交流场景已创建，首轮命令已填入')
    } catch (e) {
      setToast(e instanceof Error ? e.message : '人物场景创建失败')
    }
  }
  async function advanceStrategicTurn() {
    if (busy) return
    setBusy(true)
    try {
      const text = command.trim() || '让领地按当前安排运转九天'
      const nextGame = await api.strategicTurn({ command: text, source: 'player' })
      onGame(nextGame)
      setCommand('')
      const interrupted = (nextGame.events || []).some(event => event.kind === 'strategic_advance_interrupted' || event.kind === 'strategic_advance_blocked_by_due_event')
      const councilBlocked = (nextGame.events || []).some(event => event.kind === 'council_opened' || event.kind === 'strategic_advance_blocked_by_council')
      const adviceBlocked = (nextGame.events || []).some(event => event.kind === 'management_advice_required')
      if (councilBlocked || adviceBlocked) {
        setPanel('strategy')
        setStrategyDecision(nextGame.state.management_ai?.pending_advice ?? null)
        api.strategy.analysis().then(response => setStrategyAnalysis(response.analysis)).catch(() => undefined)
      }
      setToast(councilBlocked ? '推进被领主议会中断' : adviceBlocked ? '顾问方案等待裁定' : interrupted ? '推进被到期事件打断' : '九天战略回合已结算')
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
  const highlightedDiplomacy = Object.entries(state.diplomacy).find(([name]) => !(state.factions?.[name]?.is_player))
  return <main className="game-page">
    <header className="status-bar"><div className="brand"><span className="crest">♜</span><div><small>领地纪事</small><strong>{state.realm_name}</strong></div></div><div className="building-count">建筑 <b>{Object.values(state.buildings).reduce((a, b) => a + b, 0)}</b><span>处</span></div><div className="stat-cluster">{(['gold','food','wood','stone'] as const).map(key => <Resource key={key} name={key} state={state} onDescribe={() => describe('describe_item', resourceLabels[key][0], `描述资源：${resourceLabels[key][0]}`, { target_type: 'resource', key })} />)}</div><div className="military"><span>⚔ {state.army.infantry + state.army.archers + state.army.cavalry}</span><span>组织 {state.army_status?.organization ?? 100}</span>{highlightedDiplomacy && <span className="diplomacy-dot">{diplomacyLabel(highlightedDiplomacy[1])} · {highlightedDiplomacy[0]}</span>}</div><div className="menu"><button className={state.council?.current_meeting ? 'attention' : ''} onClick={openStrategyPanel}>{state.council?.current_meeting ? '议会待裁' : '战略方针'}</button><button onClick={() => setPanel('realm')}>领地详情</button><button onClick={openPopulationPanel}>居民分析</button><button onClick={() => describe('describe_realm', '领地描述', `描述领地：${state.realm_name}`, { target_type: 'realm' })}>描述领地</button><button onClick={() => setPanel('lord')}>领主详情</button><button onClick={() => describe('describe_lord', '领主描述', `描述领主：${state.lord_name}`, { target_type: 'lord' })}>描述领主</button><button onClick={openCharactersPanel}>人物</button><button onClick={openEventsPanel}>事件</button><button onClick={openHistoryPanel}>历史</button><button onClick={save}>保存</button><button onClick={load}>读取</button><button onClick={onBack}>退出</button></div></header>
    <section className="turn-strip"><span>第 {state.turn} 轮</span><i /> <span>第 {time?.calendar_day ?? 1} 日</span><i /> <span>{clock24(time)}</span><i /> <span>本轮第 {time?.day_in_turn ?? 1}/{time?.turn_days ?? 9} 日</span><i /> <span>{state.season}</span><i /> <span>{state.weather}</span><i /> <span>{modeLabel}</span>{activeScene && <span>已过 {activeScene.elapsed_days} 日 {activeScene.elapsed_hours} 时 {activeScene.elapsed_minutes ?? 0} 分</span>}<span className="engine-badge">{game.source === 'hermes' ? '书记官执笔叙事' : '管家按律核算'}</span></section>
    <div className="game-layout"><section className="story-column"><div className="report"><div className="report-top"><span>本轮报告</span><span className="wax">{busy ? '✦ 书记官裁决中' : '✦ 已裁决'}</span></div><div className="report-markdown"><ReactMarkdown skipHtml remarkPlugins={markdownPlugins}>{streamText || game.narrative}</ReactMarkdown></div><div className="secondary-stats"><Meter label="民心" value={state.resources.morale} /><Meter label="统治力" value={state.resources.authority} /><span>人口 <b>{state.resources.population}</b></span></div></div><AgentTracePanel trace={trace} collapsed={traceCollapsed} setCollapsed={setTraceCollapsed} running={busy} /><div className="prompt-box"><label>{activeScene ? `场景命令 · ${activeScene.title}` : '故事互动 / 场景命令'}</label><textarea value={command} onChange={e => setCommand(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }} placeholder={activeScene ? '例如：我命令卫兵把商队头领带到火盆前问话……' : '例如：召见管家询问粮仓亏空，或点击“推进九天”结算战略回合……'} /><div className="composer-footer"><span>⌘ Enter 递交书记官</span><div className="mode-actions">{!activeScene && <button className="ghost-button" type="button" onClick={startScene} disabled={busy}>开始场景</button>}{activeScene && <button className="ghost-button" type="button" onClick={endScene} disabled={busy}>结束场景</button>}<button className="ghost-button" type="button" onClick={advanceStrategicTurn} disabled={busy || !!activeScene}>推进九天</button><button className="primary-button compact" onClick={() => send()} disabled={busy}>{busy ? '裁决中…' : '递交文书 →'}</button></div></div></div><div className="suggestions">{game.suggestions.map(item => <button key={item} onClick={() => send(item)} disabled={busy}>+ {item}</button>)}</div></section>
      <div className="map-column">
        <div className="map-switch"><button type="button" className={mapMode === 'tactical' ? 'active' : ''} onClick={() => setMapMode('tactical')}>领地地图</button><button type="button" className={mapMode === 'diplomacy' ? 'active' : ''} onClick={() => setMapMode('diplomacy')}>外交地图</button></div>
        {mapMode === 'tactical' && <aside className="map-panel tactical-panel"><div className="map-head"><div><span className="section-label">领地地图</span><small>直辖地产与经营建筑 · 点击后自动描述</small></div><span>{realmMapSize}×{realmMapSize}</span></div><div className="coordinates" style={{ gridTemplateColumns: `repeat(${realmMapSize}, 1fr)` }}>{Array.from({ length: realmMapSize }, (_, index) => <span key={index}>{columnLabel(index)}</span>)}</div><div className="map-grid tactical-grid" style={{ gridTemplateColumns: `repeat(${realmMapSize}, 1fr)` }}>{Array.from({ length: realmMapSize * realmMapSize }, (_, index) => { const x = (index % realmMapSize) + 1, y = Math.floor(index / realmMapSize) + 1, tile = realmTiles.get(`${x}-${y}`)!; return <button title={`${coordLabel(x, y)} · ${tile.label}`} key={`${x}-${y}`} className={`tile ${tile.kind}`} onClick={() => openTileDrawer(tile, 'realm')}><span>{tileIcon(catalog, tile.kind)}</span></button> })}</div><div className="legend">{Object.entries(catalog?.map_tile_kinds ?? {}).filter(([kind]) => realmKinds.has(kind)).map(([kind, info]) => <span key={kind}><b style={{ color: info.color }}>{info.icon}</b>{info.label}</span>)}</div></aside>}
        {mapMode === 'diplomacy' && <aside className="map-panel diplomacy-panel"><div className="map-head"><div><span className="section-label">外交地图</span><small>大地理与势力领地 · 点击后自动描述</small></div><span>{Object.keys(state.diplomacy).length} 方势力</span></div><div className="coordinates" style={{ gridTemplateColumns: `repeat(${diplomacyMapSize}, 1fr)` }}>{Array.from({ length: diplomacyMapSize }, (_, index) => <span key={index}>{columnLabel(index)}</span>)}</div><div className="map-grid diplomacy-grid" style={{ gridTemplateColumns: `repeat(${diplomacyMapSize}, 1fr)` }}>{Array.from({ length: diplomacyMapSize * diplomacyMapSize }, (_, index) => { const x = (index % diplomacyMapSize) + 1, y = Math.floor(index / diplomacyMapSize) + 1, tile = diplomacyTiles.get(`${x}-${y}`) ?? { x, y, kind: 'grass', label: '草地', owner: null }; const owner = tile.owner ? state.factions?.[tile.owner] ?? catalog?.factions?.[tile.owner] : null; const style = owner ? { background: `${owner.color}3d`, borderColor: owner.color, color: owner.color } : undefined; return <button title={`${coordLabel(x, y)} · ${tile.label}${tile.owner ? ` · ${tile.owner}` : ''}`} key={`${x}-${y}`} className={`tile diplomacy-tile ${tile.owner ? 'owned' : 'unowned'}`} style={style} onClick={() => openTileDrawer(tile, 'diplomacy')}><span>{owner?.banner ?? diplomacyTileIcon(catalog, tile.kind)}</span></button> })}</div><div className="legend faction-legend">{Object.entries(state.diplomacy).map(([name, value]) => { const info = state.factions?.[name] ?? catalog?.factions?.[name]; return <button key={name} type="button" className="faction-chip" onClick={() => setFactionDetail(name)}><b style={{ color: info?.color ?? '#8a8a8a' }}>{info?.banner ?? '⚑'}</b>{name} · {diplomacyLabel(value)}</button> })}</div></aside>}
      </div>
    </div>
    {description.open && <DescriptionDrawer description={description} close={() => setDescription(previous => ({ ...previous, open: false }))} />}{panel && panel !== 'population' && panel !== 'history' && panel !== 'events' && panel !== 'characters' && panel !== 'strategy' && <DetailPanel panel={panel} state={state} catalog={catalog} close={() => setPanel(null)} onGrantItem={grantEquipmentItem} onEquipItem={equipEquipmentItem} onUnequipItem={unequipEquipmentItem} onPatchBodyProfile={patchBodyProfile} />}{panel === 'population' && <PopulationAnalysisPanel demographics={demographics} catalog={catalog} loading={demographicsLoading} error={demographicsError} close={() => setPanel(null)} />}{panel === 'characters' && <CharactersPanel characters={characters} catalog={catalog} loading={charactersLoading} error={charactersError} close={() => setPanel(null)} refresh={openCharactersPanel} onCreate={createCharacter} onDescribe={(character) => describe('describe_item', `人物描述：${character.name}`, `描述人物：${character.name}`, { target_type: 'character', key: character.id })} onTalk={(character) => startCharacterScene(character, 'dialogue')} onAdultScene={(character) => startCharacterScene(character, 'sexual')} onGrantItem={grantEquipmentItem} onEquipItem={equipEquipmentItem} onUnequipItem={unequipEquipmentItem} onPatchBodyProfile={patchBodyProfile} />}{panel === 'events' && <EventsPanel events={events} loading={eventsLoading} error={eventsError} close={() => setPanel(null)} refresh={openEventsPanel} currentDay={time?.calendar_day ?? 1} />}{panel === 'history' && <HistoryPanel history={history} loading={historyLoading} error={historyError} close={() => setPanel(null)} refresh={openHistoryPanel} />}{panel === 'strategy' && <CouncilPanel meeting={state.council?.current_meeting ?? null} directive={state.strategic_directive ?? null} management={state.management_ai ?? null} analysis={strategyAnalysis} decision={strategyDecision ?? state.management_ai?.pending_advice ?? null} loading={strategyLoading} error={strategyError} close={() => setPanel(null)} resolveMeeting={resolveCouncil} setMode={changeManagementMode} requestReview={requestCouncilReview} loadAdvice={loadManagementAdvice} acceptAdvice={acceptManagementAdvice} />}
    {tileDetail && <TileDetailDrawer detail={tileDetail} catalog={catalog} factions={state.factions} close={() => setTileDetail(null)} onRefresh={() => openTileDrawer(tileDetail.tile, tileDetail.source, true)} onViewFaction={(faction) => { setFactionDetail(faction) }} />}
    {factionDetail && <FactionDetailPanel faction={factionDetail} detail={buildFactionDetail(state, catalog, factionDetail)} close={() => setFactionDetail(null)} />}
    {toast && <div className="toast" onAnimationEnd={() => setToast('')}>{toast}</div>}
  </main>
}
function Resource({ name, state, onDescribe }: { name: keyof typeof resourceLabels; state: GameState; onDescribe?: () => void }) { const [label, symbol] = resourceLabels[name]; const change = state.changes[name] ?? 0; return <button className="resource resource-button" type="button" onClick={onDescribe} title={`描述${label}`}><small>{symbol} {label}</small><b>{state.resources[name as keyof GameState['resources']]}</b>{change !== 0 && <em className={change > 0 ? 'up' : 'down'}>{change > 0 ? '+' : ''}{change}</em>}</button> }
function AgentTracePanel({ trace, collapsed, setCollapsed, running }: { trace: AgentTraceEvent[]; collapsed: boolean; setCollapsed: (value: boolean) => void; running: boolean }) {
  return <section className="agent-trace"><button className="trace-head" type="button" onClick={() => setCollapsed(!collapsed)}><span>书记官手记</span><small>{running ? '誊写中' : '待命'} · {trace.length} 条</small><b>{collapsed ? '展开' : '收起'}</b></button>{!collapsed && <div className="trace-list">{trace.length ? trace.map(item => <div className={`trace-item ${item.status ?? ''}`} key={item.id}><span>{traceMark(item.kind)}</span><div><strong>{item.title}</strong>{item.detail && <p>{item.detail}</p>}</div></div>) : <p className="empty-trace">尚无书记官手记。</p>}</div>}</section>
}
function DescriptionDrawer({ description, close }: { description: DescriptionState; close: () => void }) {
  const markdown = description.text || (description.loading ? '书记官正在观察与书写……' : '暂无描述。')
  return <aside className="description-drawer"><div className="drawer-card"><button className="close" onClick={close}>×</button><span className="section-label">书记官描述</span><h2>{description.title}</h2><div className="markdown-description"><ReactMarkdown skipHtml remarkPlugins={markdownPlugins}>{markdown}</ReactMarkdown></div><AgentTracePanel trace={description.trace} collapsed={false} setCollapsed={() => undefined} running={description.loading} /></div></aside>
}
function Meter({ label, value }: { label: string; value: number }) { return <span className="meter"><small>{label}</small><b>{value}</b><i><i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></i></span> }
function DetailPanel({ panel, state, catalog, close, onGrantItem, onEquipItem, onUnequipItem, onPatchBodyProfile }: { panel: 'realm' | 'lord'; state: GameState; catalog: Catalog | null; close: () => void; onGrantItem: (owner: EquipmentOwner, itemId: string, quantity: number) => Promise<void>; onEquipItem: (owner: EquipmentOwner, itemId: string, slot: string) => Promise<void>; onUnequipItem: (owner: EquipmentOwner, slot: string, itemId?: string) => Promise<void>; onPatchBodyProfile: (owner: EquipmentOwner, availableSlots: string[]) => Promise<void> }) {
  const title = panel === 'realm' ? '领地档案' : '领主档案'
  const lordCharacter: CharacterEntry = {
    id: 'player_lord',
    kind: 'lord',
    name: state.lord_name,
    role: '领主',
    gender: state.lord_gender,
    faction: state.realm_name,
    location: '领主堡垒',
    status: 'active',
    appearance_md: state.appearance,
    personality_md: state.personality,
    description_md: '',
    relationship_to_lord: '本人',
    disposition: 100,
    traits: [],
    memories: [],
    components: state.lord_components ?? {},
    flags: {},
  }
  const body = panel === 'realm'
    ? <><p>生效法令：{state.laws.length ? state.laws.join('、') : '无'}</p><p>建筑：{buildingSummary(state.buildings)}</p><p>外交：{Object.entries(state.diplomacy).map(([name,status]) => `${name}[${diplomacyLabel(status)}]`).join(' · ')}</p></>
    : <><p><b>{state.lord_name}</b> · {state.lord_gender}</p><p>{state.appearance || '尚未留下外貌记述。'}</p><p>{state.personality || '尚未留下性格记述。'}</p><p>天赋：{state.talents.map(t => t.name).join('、')}</p><CharacterAttributesAndEquipment character={lordCharacter} /><EquipmentManager character={lordCharacter} catalog={catalog} owner={{ type: 'lord' }} onGrantItem={onGrantItem} onEquipItem={onEquipItem} onUnequipItem={onUnequipItem} onPatchBodyProfile={onPatchBodyProfile} /></>
  return <div className="modal-shade"><section className="detail-modal"><button className="close" onClick={close}>×</button><span className="section-label">{title}</span>{body}</section></div>
}
function HistoryPanel({ history, loading, error, close, refresh }: { history: HistoryResponse | null; loading: boolean; error: string; close: () => void; refresh: () => void }) {
  const entries = history?.entries ?? []
  return <div className="modal-shade"><section className="detail-modal history-panel">
    <button className="close" onClick={close}>×</button>
    <div className="section-head"><div><span className="section-label">编年史</span><small>书记官认为值得留存的领地记忆</small></div><button type="button" className="ghost-button" onClick={refresh} disabled={loading}>刷新</button></div>
    {loading && <p>书记官正在翻检羊皮卷……</p>}
    {error && <p className="error">{error}</p>}
    {!loading && !error && !entries.length && <p>尚无历史条目。</p>}
    {!loading && !error && !!entries.length && <div className="history-list">{entries.map(entry => <HistoryEntryCard key={entry.id} entry={entry} />)}</div>}
  </section></div>
}
function HistoryEntryCard({ entry }: { entry: HistoryEntry }) {
  const tags = entry.tags?.length ? entry.tags.join(' · ') : '未标记'
  const details = entry.details_md || ''
  return <article className="history-entry">
    <header><small>第 {entry.turn} 轮 · 第 {entry.calendar_day} 日 · {entry.clock_24} · {entry.season}</small><b>重要性 {entry.importance}</b></header>
    <h3>{entry.title}</h3>
    <div className="markdown-description history-markdown"><ReactMarkdown skipHtml remarkPlugins={markdownPlugins}>{entry.summary_md || '书记官未写下摘要。'}</ReactMarkdown></div>
    {details && <details><summary>展开详情</summary><div className="markdown-description history-markdown"><ReactMarkdown skipHtml remarkPlugins={markdownPlugins}>{details}</ReactMarkdown></div></details>}
    <footer><span>{entry.source}</span><span>{tags}</span></footer>
  </article>
}
function EventsPanel({ events, loading, error, close, refresh, currentDay }: { events: ScheduledEventsResponse | null; loading: boolean; error: string; close: () => void; refresh: () => void; currentDay: number }) {
  const entries = events?.events ?? []
  const dueCount = events?.context?.urgent_due_events?.length ?? entries.filter(item => item.status === 'due' || item.status === 'active').length
  return <div className="modal-shade"><section className="detail-modal events-panel">
    <button className="close" onClick={close}>×</button>
    <div className="section-head"><div><span className="section-label">事件</span><small>未来、到期与正在发生的长期事务</small></div><button type="button" className="ghost-button" onClick={refresh} disabled={loading}>刷新</button></div>
    <div className="event-summary"><StatCard label="总数" value={events?.total ?? 0} /><StatCard label="到期/进行中" value={dueCount} /><StatCard label="当前日" value={currentDay} /></div>
    {loading && <p>书记官正在翻检事件簿……</p>}
    {error && <p className="error">{error}</p>}
    {!loading && !error && !entries.length && <p>暂无长期事件。</p>}
    {!loading && !error && !!entries.length && <div className="history-list">{entries.map(event => <EventCard key={event.id} event={event} currentDay={currentDay} />)}</div>}
  </section></div>
}
function EventCard({ event, currentDay }: { event: ScheduledEvent; currentDay: number }) {
  const due = event.schedule?.due_time
  const remain = due ? Number(due.calendar_day) - currentDay : 0
  const tags = [event.type, event.status, event.visibility].filter(Boolean).join(' · ')
  const details = event.result_md || event.description_md || ''
  return <article className={`history-entry event-entry ${event.status}`}>
    <header><small>{due ? `第 ${due.calendar_day} 日 · ${due.clock_24} · ${due.season ?? ''}` : '未定时刻'}</small><b>{remain < 0 ? `已过 ${Math.abs(remain)} 日` : remain === 0 ? '今日到期' : `剩余 ${remain} 日`}</b></header>
    <h3>{event.title}</h3>
    <div className="event-meta"><span>{event.status}</span><span>重要性 {event.importance}</span><span>{event.id}</span></div>
    {details && <div className="markdown-description history-markdown"><ReactMarkdown skipHtml remarkPlugins={markdownPlugins}>{details}</ReactMarkdown></div>}
    <footer><span>{event.created_by ?? 'system'}</span><span>{tags}</span></footer>
  </article>
}
type CharacterFormState = {
  kind: string
  name: string
  role: string
  gender: string
  age: string
  faction: string
  location: string
  description_md: string
  relationship_to_lord: string
  disposition: string
  traits: string
}
const emptyCharacterForm: CharacterFormState = { kind: 'commoner', name: '', role: '', gender: '未说明', age: '', faction: '', location: '', description_md: '', relationship_to_lord: '', disposition: '0', traits: '' }
function CharactersPanel({ characters, catalog, loading, error, close, refresh, onCreate, onDescribe, onTalk, onAdultScene, onGrantItem, onEquipItem, onUnequipItem, onPatchBodyProfile }: { characters: CharactersResponse | null; catalog: Catalog | null; loading: boolean; error: string; close: () => void; refresh: () => void; onCreate: (payload: CharacterUpsertPayload) => Promise<void>; onDescribe: (character: CharacterEntry) => void; onTalk: (character: CharacterEntry) => void; onAdultScene: (character: CharacterEntry) => void; onGrantItem: (owner: EquipmentOwner, itemId: string, quantity: number) => Promise<void>; onEquipItem: (owner: EquipmentOwner, itemId: string, slot: string) => Promise<void>; onUnequipItem: (owner: EquipmentOwner, slot: string, itemId?: string) => Promise<void>; onPatchBodyProfile: (owner: EquipmentOwner, availableSlots: string[]) => Promise<void> }) {
  const entries = characters?.characters ?? []
  const [form, setForm] = useState<CharacterFormState>(emptyCharacterForm)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault()
    setCreateError('')
    const name = form.name.trim()
    if (!name) {
      setCreateError('必须填写人物姓名')
      return
    }
    setCreating(true)
    try {
      const payload: CharacterUpsertPayload = {
        kind: form.kind,
        name,
        role: form.role.trim(),
        gender: form.gender.trim() || '未说明',
        age: form.age.trim() ? Number(form.age) : null,
        faction: form.faction.trim(),
        location: form.location.trim(),
        description_md: form.description_md.trim(),
        relationship_to_lord: form.relationship_to_lord.trim(),
        disposition: Number(form.disposition) || 0,
        traits: form.traits.split(/[，,、\n]/).map(item => item.trim()).filter(Boolean),
      }
      await onCreate(payload)
      setForm(emptyCharacterForm)
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : '人物创建失败')
    } finally {
      setCreating(false)
    }
  }
  const update = (key: keyof CharacterFormState, value: string) => setForm(previous => ({ ...previous, [key]: value }))
  return <div className="modal-shade"><section className="detail-modal characters-panel">
    <button className="close" onClick={close}>×</button>
    <div className="section-head"><div><span className="section-label">人物账册</span><small>除领主本人以外，书记官记下的重要人物</small></div><button type="button" className="ghost-button" onClick={refresh} disabled={loading}>刷新</button></div>
    <details className="character-create" open={!entries.length}>
      <summary>添加人物</summary>
      <form className="character-form" onSubmit={submit}>
        <div className="character-form-grid">
          <label className="field"><span>姓名</span><input value={form.name} onChange={event => update('name', event.target.value)} placeholder="玛尔塔" /></label>
          <label className="field"><span>类型</span><select value={form.kind} onChange={event => update('kind', event.target.value)}><option value="commoner">普通领民</option><option value="steward">管家</option><option value="merchant">商人</option><option value="envoy">使者</option><option value="knight">骑士</option><option value="soldier">士兵</option><option value="craftsman">工匠</option><option value="prisoner">俘虏</option><option value="spy">间谍</option></select></label>
          <label className="field"><span>身份/职位</span><input value={form.role} onChange={event => update('role', event.target.value)} placeholder="管家、护卫、商人……" /></label>
          <label className="field"><span>性别</span><input value={form.gender} onChange={event => update('gender', event.target.value)} placeholder="女 / 男 / 未说明" /></label>
          <label className="field"><span>年龄</span><input type="number" min="0" max="130" value={form.age} onChange={event => update('age', event.target.value)} placeholder="成人场景需要 >=18" /></label>
          <label className="field"><span>势力</span><input value={form.faction} onChange={event => update('faction', event.target.value)} placeholder="黑泥堡" /></label>
          <label className="field"><span>位置</span><input value={form.location} onChange={event => update('location', event.target.value)} placeholder="领主堡垒" /></label>
          <label className="field"><span>倾向</span><input type="number" min="-100" max="100" value={form.disposition} onChange={event => update('disposition', event.target.value)} /></label>
        </div>
        <label className="field"><span>与领主关系</span><input value={form.relationship_to_lord} onChange={event => update('relationship_to_lord', event.target.value)} placeholder="畏惧、忠诚、敌意、暧昧……" /></label>
        <label className="field"><span>特质</span><input value={form.traits} onChange={event => update('traits', event.target.value)} placeholder="识字、贪财、伤员，用逗号分隔" /></label>
        <label className="field"><span>人物描述 Markdown</span><textarea value={form.description_md} onChange={event => update('description_md', event.target.value)} placeholder="书记官可展示的人物描述。" /></label>
        {createError && <p className="error">{createError}</p>}
        <button className="primary-button compact" type="submit" disabled={creating}>{creating ? '入册中…' : '加入人物账册'}</button>
      </form>
    </details>
    {loading && <p>书记官正在翻检人物名录……</p>}
    {error && <p className="error">{error}</p>}
    {!loading && !error && !entries.length && <p>尚无非玩家人物记录。与商人、管家、使者或俘虏互动后，书记官会将重要人物写入账册。</p>}
    {!loading && !error && !!entries.length && <div className="character-list">{entries.map(character => <CharacterCard key={character.id} character={character} catalog={catalog} onDescribe={() => onDescribe(character)} onTalk={() => onTalk(character)} onAdultScene={() => onAdultScene(character)} onGrantItem={onGrantItem} onEquipItem={onEquipItem} onUnequipItem={onUnequipItem} onPatchBodyProfile={onPatchBodyProfile} />)}</div>}
  </section></div>
}
const sexPositionLabels: Record<string, string> = { missionary: '正面', standing: '站立', rear: '背后', oral: '口交', anal: '肛交' }
const bodyContentLabels: Record<string, string> = { semen: '精液', urine: '尿液', food: '食物', water: '水', wine: '酒', medicine: '药物', poison: '毒物', blood: '血液', bile: '胆汁', parasite: '寄生物', unknown: '未知内容物' }
const reproductiveBucketLabels: Record<string, string> = { stomach_contents: '胃容物', intestinal_contents: '肠道容物', uterine_contents: '子宫容物' }
const attributeLabels: Record<string, string> = { STR: '力量', DEX: '敏捷', CON: '体质', INT: '智力', WIS: '感知', CHA: '魅力' }
const equipmentSlotLabels: Record<string, string> = {
  head: '头部', neck: '颈部', torso: '躯干', back: '背部',
  left_arm: '左臂', right_arm: '右臂', left_hand: '左手', right_hand: '右手',
  waist: '腰部', left_leg: '左腿', right_leg: '右腿', left_foot: '左脚', right_foot: '右脚',
  left_nipple: '左乳头', right_nipple: '右乳头', nipple_chain: '乳链',
  penis: '阴茎', vagina: '阴道', anus: '肛门',
  accessory_1: '饰品 1', accessory_2: '饰品 2',
}
const defaultEquipmentSlots = ['head','neck','torso','back','left_arm','right_arm','left_hand','right_hand','waist','left_leg','right_leg','left_foot','right_foot','accessory_1','accessory_2']
const bodySlotPresets: Record<'common' | 'male' | 'female', { label: string; slots: string[] }> = {
  common: { label: '通用槽位', slots: defaultEquipmentSlots },
  male: {
    label: '男性全槽位',
    slots: ['head','neck','torso','back','left_arm','right_arm','left_hand','right_hand','waist','left_leg','right_leg','left_foot','right_foot','left_nipple','right_nipple','nipple_chain','penis','anus','accessory_1','accessory_2'],
  },
  female: {
    label: '女性全槽位',
    slots: ['head','neck','torso','back','left_arm','right_arm','left_hand','right_hand','waist','left_leg','right_leg','left_foot','right_foot','left_nipple','right_nipple','nipple_chain','vagina','anus','accessory_1','accessory_2'],
  },
}
function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}
function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') as Record<string, unknown>[] : []
}
function countSummary(value: unknown) {
  const record = asRecord(value)
  return Object.entries(record).map(([key, raw]) => `${sexPositionLabels[key] ?? key} ${Number(raw) || 0}`).join('、')
}
function numberRecord(value: unknown): Record<string, number> {
  return Object.fromEntries(Object.entries(asRecord(value)).map(([key, raw]) => [key, Number(raw) || 0]))
}
function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(item => String(item).trim()).filter(Boolean) : []
}
function itemName(catalog: Catalog | null, itemId: string) {
  return catalog?.items?.[itemId]?.name ?? itemId
}
function itemAllowedSlots(item?: ItemCatalogEntry): string[] {
  if (!item) return []
  if (Array.isArray(item.allowed_slots) && item.allowed_slots.length) return item.allowed_slots
  const legacy = item.slot ? String(item.slot) : ''
  return legacy ? [legacy] : []
}
function EquipmentManager({ character, catalog, owner, onGrantItem, onEquipItem, onUnequipItem, onPatchBodyProfile }: { character: CharacterEntry; catalog: Catalog | null; owner: EquipmentOwner; onGrantItem: (owner: EquipmentOwner, itemId: string, quantity: number) => Promise<void>; onEquipItem: (owner: EquipmentOwner, itemId: string, slot: string) => Promise<void>; onUnequipItem: (owner: EquipmentOwner, slot: string, itemId?: string) => Promise<void>; onPatchBodyProfile: (owner: EquipmentOwner, availableSlots: string[]) => Promise<void> }) {
  const itemEntries = Object.entries(catalog?.items ?? {})
  const firstItemId = itemEntries[0]?.[0] ?? ''
  const [grantItemId, setGrantItemId] = useState(firstItemId)
  const [grantQuantity, setGrantQuantity] = useState('1')
  const [equipItemId, setEquipItemId] = useState(firstItemId)
  const [equipSlot, setEquipSlot] = useState('')
  const [bodyProfileText, setBodyProfileText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const components = asRecord(character.components)
  const bodyProfile = asRecord(components.body_profile)
  const availableSlots = stringArray(bodyProfile.available_slots)
  const normalizedAvailableSlots = availableSlots.length ? availableSlots : defaultEquipmentSlots
  const equipment = asRecord(components.equipment)
  const slots = asRecord(equipment.slots)
  const sources = asArray(equipment.sources)
  const inventoryItems = asArray(asRecord(components.inventory).items)
  const selectedEquipItem = catalog?.items?.[equipItemId]
  const allowedSlots = itemAllowedSlots(selectedEquipItem)
  const equipSlotOptions = allowedSlots.filter(slot => normalizedAvailableSlots.includes(slot))
  const renderedEquipSlotOptions = equipSlotOptions.length ? equipSlotOptions : allowedSlots
  useEffect(() => {
    if (!grantItemId && firstItemId) setGrantItemId(firstItemId)
    if (!equipItemId && firstItemId) setEquipItemId(firstItemId)
  }, [firstItemId, grantItemId, equipItemId])
  useEffect(() => {
    const nextSlot = renderedEquipSlotOptions[0] ?? ''
    if (!equipSlot || !renderedEquipSlotOptions.includes(equipSlot)) setEquipSlot(nextSlot)
  }, [equipItemId, normalizedAvailableSlots.join('|')])
  useEffect(() => {
    setBodyProfileText(normalizedAvailableSlots.join(', '))
  }, [character.id, normalizedAvailableSlots.join('|')])
  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (e) {
      setError(e instanceof Error ? e.message : '装备操作失败')
    } finally {
      setBusy(false)
    }
  }
  const bodySlots = bodyProfileText.split(/[，,\s\n]+/).map(item => item.trim()).filter(Boolean)
  return <details className="equipment-manager">
    <summary>装备管理</summary>
    {!itemEntries.length && <p className="equipment-note">物品 catalog 未加载，无法管理装备。</p>}
    {!!itemEntries.length && <>
      <div className="equipment-control-grid">
        <label className="field"><span>发放物品</span><select value={grantItemId} onChange={event => setGrantItemId(event.target.value)}>{itemEntries.map(([id, item]) => <option key={id} value={id}>{item.name} · {id}</option>)}</select></label>
        <label className="field"><span>数量</span><input type="number" min="1" max="1000" value={grantQuantity} onChange={event => setGrantQuantity(event.target.value)} /></label>
        <button type="button" className="ghost-button equipment-action-button" disabled={busy || !grantItemId} onClick={() => run(() => onGrantItem(owner, grantItemId, Math.max(1, Number(grantQuantity) || 1)))}>入账</button>
      </div>
      <div className="equipment-control-grid">
        <label className="field"><span>装备物品</span><select value={equipItemId} onChange={event => setEquipItemId(event.target.value)}>{itemEntries.map(([id, item]) => <option key={id} value={id}>{item.name} · {id}</option>)}</select></label>
        <label className="field"><span>目标槽位</span><select value={renderedEquipSlotOptions.includes(equipSlot) ? equipSlot : (renderedEquipSlotOptions[0] ?? '')} onChange={event => setEquipSlot(event.target.value)}>{renderedEquipSlotOptions.map(slot => <option key={slot} value={slot}>{equipmentSlotLabels[slot] ?? slot}</option>)}</select></label>
        <button type="button" className="ghost-button equipment-action-button" disabled={busy || !equipItemId || !renderedEquipSlotOptions.length} onClick={() => run(() => onEquipItem(owner, equipItemId, renderedEquipSlotOptions.includes(equipSlot) ? equipSlot : renderedEquipSlotOptions[0]))}>装备</button>
      </div>
      {selectedEquipItem && <p className="equipment-note">允许槽位：{allowedSlots.map(slot => equipmentSlotLabels[slot] ?? slot).join('、') || '无'}；防护 {selectedEquipItem.armor ?? 0} · 伤害 {selectedEquipItem.damage ?? 0} · 重量 {selectedEquipItem.weight ?? 0}</p>}
    </>}
    <div className="component-block equipment-slots-block">
      <b>当前装备</b>
      {sources.length ? <ul>{sources.map((source, index) => {
        const occupied = stringArray(source.occupied_slots)
        const firstSlot = occupied[0] || String(source.slot || '')
        return <li key={`${character.id}-managed-equipment-${index}`}><span>{occupied.map(slot => equipmentSlotLabels[slot] ?? slot).join('、')}：{String(source.name || source.item_id)}</span><button type="button" className="ghost-button" disabled={busy || !firstSlot} onClick={() => run(() => onUnequipItem(owner, firstSlot, String(source.item_id || '')))}>卸下</button></li>
      })}</ul> : <p>未装备物品。</p>}
    </div>
    <div className="component-block">
      <b>背包</b>
      {inventoryItems.length ? <p>{inventoryItems.map(item => `${String(item.name || itemName(catalog, String(item.item_id || '')))} ×${Number(item.quantity) || 1}`).join('；')}</p> : <p>背包为空。</p>}
    </div>
    <div className="component-block">
      <b>身体可用槽位</b>
      <div className="body-preset-actions">
        {Object.entries(bodySlotPresets).map(([presetId, preset]) => <button key={presetId} type="button" className="ghost-button" disabled={busy} onClick={() => setBodyProfileText(preset.slots.join(', '))}>{preset.label}</button>)}
      </div>
      <textarea className="equipment-body-input" value={bodyProfileText} onChange={event => setBodyProfileText(event.target.value)} />
      <p className="equipment-note">用逗号或空格分隔。私密槽位只有已明确成年角色才能装备，且必须在这里声明。</p>
      <button type="button" className="ghost-button" disabled={busy || !bodySlots.length} onClick={() => run(() => onPatchBodyProfile(owner, bodySlots))}>保存身体槽位</button>
    </div>
    {error && <p className="error">{error}</p>}
  </details>
}
function CharacterAttributesAndEquipment({ character }: { character: CharacterEntry }) {
  const components = asRecord(character.components)
  const attributes = asRecord(components.attributes)
  const base = numberRecord(attributes.base)
  const effective = numberRecord(attributes.effective)
  const equipmentModifiers = numberRecord(attributes.equipment_modifiers)
  const inventoryItems = asArray(asRecord(components.inventory).items)
  const equipment = asRecord(components.equipment)
  const slots = asRecord(equipment.slots)
  const sources = asArray(equipment.sources)
  const realmEffects = numberRecord(equipment.realm_effects)
  return <details className="character-components character-equipment" open>
    <summary>属性与装备</summary>
    <div className="attribute-grid">
      {Object.keys(attributeLabels).map(key => {
        const delta = equipmentModifiers[key] ?? 0
        return <div className="attribute-pill" key={key}><b>{key}</b><span>{attributeLabels[key]}</span><strong>{effective[key] ?? base[key] ?? 10}</strong>{delta !== 0 && <em>{delta > 0 ? `+${delta}` : delta}</em>}</div>
      })}
    </div>
    <div className="component-block">
      <b>装备槽</b>
      {Object.keys(slots).length ? <p>{Object.entries(slots).map(([slot, item]) => `${equipmentSlotLabels[slot] ?? slot}：${String(item)}`).join('；')}</p> : <p>未装备物品。</p>}
      {!!sources.length && <ul>{sources.map((source, index) => {
        const occupiedSlots = Array.isArray(source.occupied_slots) ? source.occupied_slots.map(slot => equipmentSlotLabels[String(slot)] ?? String(slot)).join('、') : equipmentSlotLabels[String(source.slot)] ?? String(source.slot)
        return <li key={`${character.id}-equipment-${index}`}>{occupiedSlots}：{String(source.name || source.item_id)}</li>
      })}</ul>}
    </div>
    <div className="component-block">
      <b>背包</b>
      {inventoryItems.length ? <p>{inventoryItems.map(item => `${String(item.name || item.item_id)} ×${Number(item.quantity) || 1}`).join('；')}</p> : <p>背包为空。</p>}
    </div>
    {!!Object.keys(realmEffects).length && <div className="component-block">
      <b>领地加成</b>
      <p>{Object.entries(realmEffects).map(([key, value]) => `${key} ${value > 0 ? '+' : ''}${value}`).join('；')}</p>
    </div>}
  </details>
}
function CharacterAdultComponents({ character }: { character: CharacterEntry }) {
  const components = asRecord(character.components)
  const sexual = asRecord(components.sexual_history)
  const reproductive = asRecord(components.reproductive_contents)
  const hasSexual = Object.keys(sexual).length > 0
  const hasReproductive = Object.keys(reproductive).length > 0
  if (!hasSexual && !hasReproductive) return null
  const partners = asRecord(sexual.partners)
  return <details className="character-components">
    <summary>成人状态统计</summary>
    {hasSexual && <div className="component-block">
      <b>性经历统计</b>
      <p>对象 {Number(sexual.total_partner_count) || 0} 人 · 总次数 {Number(sexual.total_encounter_count) || 0}</p>
      {!!Object.keys(asRecord(sexual.position_totals)).length && <p>姿势总计：{countSummary(sexual.position_totals) || '无'}</p>}
      {!!Object.keys(partners).length && <ul>{Object.entries(partners).map(([id, raw]) => {
        const partner = asRecord(raw)
        return <li key={id}>{String(partner.name_snapshot || id)}：{Number(partner.encounter_count) || 0} 次{!!Object.keys(asRecord(partner.position_counts)).length ? ` · ${countSummary(partner.position_counts)}` : ''}</li>
      })}</ul>}
    </div>}
    {hasReproductive && <div className="component-block">
      <b>当前内容物</b>
      {Object.entries(reproductiveBucketLabels).map(([bucket, label]) => {
        const entries = asArray(reproductive[bucket])
        return <p key={bucket}>{label}：{entries.length ? entries.map(entry => `${bodyContentLabels[String(entry.content_type)] ?? String(entry.content_type || 'unknown')}←${String(entry.source_name_snapshot || entry.source_character_id || 'unknown')} ×${Number(entry.amount) || 1}`).join('；') : '无'}</p>
      })}
    </div>}
  </details>
}
function CharacterCard({ character, catalog, onDescribe, onTalk, onAdultScene, onGrantItem, onEquipItem, onUnequipItem, onPatchBodyProfile }: { character: CharacterEntry; catalog: Catalog | null; onDescribe: () => void; onTalk: () => void; onAdultScene: () => void; onGrantItem: (owner: EquipmentOwner, itemId: string, quantity: number) => Promise<void>; onEquipItem: (owner: EquipmentOwner, itemId: string, slot: string) => Promise<void>; onUnequipItem: (owner: EquipmentOwner, slot: string, itemId?: string) => Promise<void>; onPatchBodyProfile: (owner: EquipmentOwner, availableSlots: string[]) => Promise<void> }) {
  const meta = [character.kind, character.role, character.gender, character.age === null || character.age === undefined ? '' : `${character.age}岁`, character.faction, character.location, character.status].filter(Boolean).join(' · ')
  const details = character.description_md || character.appearance_md || character.personality_md || ''
  const isAdult = Number(character.age) >= 18
  return <article className="character-card">
    <header><div><h3>{character.name}</h3><small>{character.id}</small></div><div className="character-actions"><button type="button" className="ghost-button" onClick={onDescribe}>描述</button><button type="button" className="ghost-button" onClick={onTalk}>交流</button><button type="button" className="ghost-button adult-action" onClick={onAdultScene} disabled={!isAdult} title={isAdult ? '开始成人/性爱场景' : '需要年龄明确且不少于 18 岁'}>性爱场景</button></div></header>
    {meta && <p className="character-meta">{meta}</p>}
    <p>对领主：{character.relationship_to_lord || '未记录'} · 倾向 {character.disposition}</p>
    {!!character.traits?.length && <p>特质：{character.traits.join('、')}</p>}
    {details && <div className="markdown-description character-markdown"><ReactMarkdown skipHtml remarkPlugins={markdownPlugins}>{details}</ReactMarkdown></div>}
    <CharacterAttributesAndEquipment character={character} />
    <EquipmentManager character={character} catalog={catalog} owner={{ type: 'character', characterId: character.id }} onGrantItem={onGrantItem} onEquipItem={onEquipItem} onUnequipItem={onUnequipItem} onPatchBodyProfile={onPatchBodyProfile} />
    {!!character.memories?.length && <details><summary>人物记忆</summary><ul>{character.memories.map((memory, index) => <li key={`${character.id}-memory-${index}`}>{memory}</li>)}</ul></details>}
    <CharacterAdultComponents character={character} />
  </article>
}
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
function TileDetailDrawer({ detail, catalog, factions, close, onRefresh, onViewFaction }: { detail: TileDrawerState; catalog: Catalog | null; factions?: Record<string, { color: string; banner: string; description: string }>; close: () => void; onRefresh: () => void; onViewFaction: (faction: string) => void }) {
  const { tile, source } = detail
  const info = source === 'diplomacy' ? diplomacyTileInfo(catalog, tile.kind) : realmTileInfo(catalog, tile.kind)
  const owner = tile.owner ? factions?.[tile.owner] ?? catalog?.factions?.[tile.owner] : null
  const ownerLabel = tile.owner ? <><b style={{ color: owner?.color }}>{owner?.banner ?? '⚑'} {tile.owner}</b></> : source === 'realm' ? '领地直辖' : '未被明确控制'
  const markdown = detail.text || (detail.loading ? '书记官正在观察这块土地……' : '暂无地块描述。')
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
    <div className="markdown-description tile-description"><ReactMarkdown skipHtml remarkPlugins={markdownPlugins}>{markdown}</ReactMarkdown></div>
    <AgentTracePanel trace={detail.trace} collapsed={false} setCollapsed={() => undefined} running={detail.loading} />
  </div></aside>
}
function FactionDetailPanel({ faction, detail, close }: { faction: string; detail: FactionDetail; close: () => void }) {
  const relationPercent = Math.max(0, Math.min(100, (detail.relation + 100) / 2))
  const factionState = detail.state
  return <div className="modal-shade"><section className="detail-modal faction-detail">
    <button className="close" onClick={close}>×</button>
    <span className="section-label">外交势力详情</span>
    <p><b style={{ color: detail.color }}>{detail.banner} {faction}</b></p>
    {detail.description && <p>{detail.description}</p>}
    <p>姿态：<b style={{ color: detail.color }}>{detail.stance}</b>{detail.at_war && ' · 战争状态'}</p>
    <p className="meter"><small>关系值 {detail.relation}</small><i><i style={{ width: `${relationPercent}%`, background: detail.color }} /></i></p>
    <p>条约：{detail.treaties.length ? detail.treaties.map(t => `${t.name}（剩余 ${t.remaining_turns} 轮）`).join('、') : '无'}</p>
    <p>领地：{detail.owned_tile_count} 处{detail.owned_tile_count > 0 && `（${detail.owned_tiles.map(t => coordLabel(t.x, t.y)).join('、')}）`}</p>
    {factionState && <div className="faction-ledger">
      <h3>势力大盘</h3>
      <p>资源：{namedNumberSummary(factionState.resources, resourceLabels, 10)}</p>
      <p>部队：{namedNumberSummary(factionState.army, undefined, 8)}</p>
      <p>组织度：{factionState.army_status?.organization ?? 100}{factionState.army_status?.routed ? ' · 已溃散' : ''}</p>
      <p>建筑/据点：{buildingSummary(factionState.buildings ?? {})}</p>
      {factionState.workforce && <p>劳力：可用 {factionState.workforce.available} · 已分配 {factionState.workforce.assigned}</p>}
      {!!factionState.laws?.length && <p>法令：{factionState.laws.join('、')}</p>}
    </div>}
  </section></div>
}
function parseAgentEvent(data: string): AgentSseEvent { try { return JSON.parse(data) as AgentSseEvent } catch { return { event: 'run.event', message: data } } }
function traceFromAgentEvent(event: AgentSseEvent): AgentTraceEvent | null {
  const name = String(event.event || event.type || 'run.event')
  const seq = String(event.seq ?? Date.now())
  if (name === 'message.delta') return null
  if (name === 'reasoning.available') return { id: `reasoning-${seq}`, kind: 'reasoning', title: '书记官思路', detail: courtText(event.text || event.message || ''), status: 'complete' }
  if (name.startsWith('tool.')) return { id: `tool-${seq}`, kind: 'tool', title: name === 'tool.started' ? '差役奉命出行' : name.endsWith('failed') ? '差役回报受阻' : '差役回报完成', detail: courtText(event.message || event.name || event.command || ''), status: name === 'tool.started' ? 'running' : name.endsWith('failed') ? 'error' : 'complete' }
  if (name.startsWith('approval.')) return { id: `approval-${seq}`, kind: 'approval', title: name === 'approval.request' ? '令状待批' : '令状已批', detail: courtText(event.message || event.choice || ''), status: name === 'approval.request' ? 'pending' : 'complete' }
  if (name.startsWith('clarify.')) return { id: `clarify-${seq}`, kind: 'clarify', title: name === 'clarify.request' ? '书记官请示' : '领主批示', detail: courtText(event.message || event.response || ''), status: name === 'clarify.request' ? 'pending' : 'complete' }
  if (name.startsWith('state.action_')) return { id: `state-${seq}`, kind: 'state_action', title: name === 'state.action_applied' ? '账册已改' : '账册改写被拒', detail: courtText(event.message || ''), status: name === 'state.action_applied' ? 'complete' : 'error' }
  if (name.startsWith('run.')) return { id: `run-${seq}`, kind: 'run', title: name === 'run.started' ? '书记官开卷' : name === 'run.completed' ? '书记官落笔' : name === 'run.failed' ? '书记官受阻' : name === 'run.cancelled' ? '书记官停笔' : '书记官文书', detail: courtText(event.message || event.error || ''), status: name === 'run.failed' ? 'error' : name === 'run.started' ? 'running' : 'complete' }
  return { id: `event-${seq}`, kind: 'message', title: '来信', detail: courtText(event.message || name), status: 'complete' }
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
