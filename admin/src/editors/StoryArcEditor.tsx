import { memo, useEffect, useMemo, useState } from 'react'
import {
  Background, BackgroundVariant, Connection, Controls, Edge, Handle, MarkerType,
  MiniMap, Node, NodeChange, NodeProps, Position, ReactFlow, ReactFlowInstance, applyNodeChanges,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import './workflow.css'

type Json = Record<string, unknown>
type Choice = { id: string; label: string; description_md: string; confirm?: boolean; effects?: Json[]; transition: { to: string; when?: Json } }
type Transition = { to: string; when?: Json; priority?: number }
type ArcNode = { kind: string; title?: string; blocking?: boolean; scene_type?: string; presentation?: 'transition_log' | 'silent'; narrative_template_md?: string; choices?: Choice[]; effects?: Json[]; transition?: Transition; transitions?: Transition[]; after_hours?: number; after_days?: number }
type FlowData = { title: string; authoredId: string; kind: string; blocking: boolean; entry: boolean; level: number; ports: { id: string; label: string; target?: string }[] }
type FlowNode = Node<FlowData, 'storyArc'>

function asNodes(document: Json): Record<string, ArcNode> {
  return document.nodes && typeof document.nodes === 'object' && !Array.isArray(document.nodes) ? document.nodes as Record<string, ArcNode> : {}
}

function layout(document: Json): Record<string, { x: number; y: number }> {
  const value = document.editor_layout
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  const nodes = (value as Json).nodes
  return nodes && typeof nodes === 'object' && !Array.isArray(nodes) ? nodes as Record<string, { x: number; y: number }> : {}
}

function levelLayout(nodes: Record<string, ArcNode>, entry: string) {
  const ids = Object.keys(nodes)
  const outgoing = Object.fromEntries(ids.map(id => [id, portsFor(nodes[id]).map(port => port.target).filter((target): target is string => !!target && !!nodes[target])]))
  const indegree = Object.fromEntries(ids.map(id => [id, 0]))
  for (const targets of Object.values(outgoing)) for (const target of targets) indegree[target] += 1
  const level: Record<string, number> = Object.fromEntries(ids.map(id => [id, 0]))
  const queue = ids.filter(id => indegree[id] === 0).sort((left, right) => Number(right === entry) - Number(left === entry))
  const visited = new Set<string>()
  while (queue.length) {
    const source = queue.shift()!
    visited.add(source)
    for (const target of outgoing[source]) {
      level[target] = Math.max(level[target], level[source] + 1)
      indegree[target] -= 1
      if (indegree[target] === 0) queue.push(target)
    }
  }
  const fallbackLevel = Math.max(0, ...Object.values(level)) + 1
  for (const id of ids) if (!visited.has(id)) level[id] = fallbackLevel
  const groups = new Map<number, string[]>()
  for (const id of ids) groups.set(level[id], [...(groups.get(level[id]) ?? []), id])
  const largestGroup = Math.max(1, ...[...groups.values()].map(group => group.length))
  const positions: Record<string, { x: number; y: number }> = {}
  for (const [nodeLevel, group] of groups) group.forEach((id, index) => {
    positions[id] = { x: 60 + nodeLevel * 360, y: 60 + (index + (largestGroup - group.length) / 2) * 230 }
  })
  return { positions, levels: level }
}

function portsFor(node: ArcNode) {
  const choices = (node.choices ?? []).map((choice, index) => ({ id: `choice:${index}`, label: choice.label || choice.id, target: choice.transition?.to }))
  const direct = node.transition ? [{ id: 'transition', label: node.kind === 'automatic' ? '自动迁移' : '迁移', target: node.transition.to }] : []
  const conditional = (node.transitions ?? []).map((edge, index) => ({ id: `conditional:${index}`, label: edge.when ? `条件 ${index + 1}` : 'fallback', target: edge.to }))
  return [...choices, ...direct, ...conditional]
}

const StoryArcNode = memo(function StoryArcNode({ data, selected }: NodeProps<FlowNode>) {
  return <div className={`flow-story-node ${data.kind} ${selected ? 'selected' : ''}`}>
    <Handle type="target" position={Position.Left} className="flow-target" />
    <header><span>{data.entry ? '◆' : nodeIcon(data.kind)}</span><div><b>{data.title}</b><code>{data.authoredId}</code></div></header>
    <div className="flow-node-tags"><em>Level {data.level}</em><em>{data.kind}</em>{data.blocking && <em>blocking</em>}</div>
    <div className="flow-ports">{data.ports.length ? data.ports.map(port => <div className="flow-port" key={port.id} title={port.target ? `当前连接：${port.target}` : '拖动圆点连接到目标节点'}>
      <span>{port.label}</span><small>{port.target ? `→ ${port.target}` : '未连接'}</small>
      <Handle type="source" position={Position.Right} id={port.id} style={{ top: '50%' }} />
    </div>) : <small className="no-port">没有出口</small>}</div>
  </div>
})

function nodeIcon(kind: string) { return kind === 'terminal' ? '■' : kind === 'timed' ? '◷' : kind === 'automatic' ? '●' : '◇' }

export default function StoryArcEditor({ document, onChange }: { document: Json; onChange: (next: Json) => void }) {
  const authoredNodes = asNodes(document)
  const nodeIds = Object.keys(authoredNodes)
  const entry = String(document.entry_node ?? '')
  const [selectedId, setSelectedId] = useState(entry || nodeIds[0] || '')
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<FlowNode, Edge> | null>(null)
  const selected = authoredNodes[selectedId]
  const flowNodesFromDocument = useMemo<FlowNode[]>(() => {
    const automatic = levelLayout(authoredNodes, entry)
    const saved = layout(document)
    const editorLayout = document.editor_layout as Json | undefined
    const positions = editorLayout?.mode === 'manual' ? saved : automatic.positions
    return nodeIds.map((id, index) => ({
      id, type: 'storyArc',
      position: positions[id] ?? automatic.positions[id] ?? { x: 60, y: 60 + index * 230 },
      data: { title: authoredNodes[id].title || id, authoredId: id, kind: authoredNodes[id].kind, blocking: !!authoredNodes[id].blocking, entry: id === entry, level: automatic.levels[id], ports: portsFor(authoredNodes[id]) },
      selected: id === selectedId,
    }))
  }, [document, selectedId])
  const [flowNodes, setFlowNodes] = useState<FlowNode[]>(flowNodesFromDocument)
  useEffect(() => setFlowNodes(flowNodesFromDocument), [flowNodesFromDocument])

  const flowEdges = useMemo<Edge[]>(() => nodeIds.flatMap(source => portsFor(authoredNodes[source]).filter(port => port.target && authoredNodes[port.target]).map(port => ({
    id: `${source}:${port.id}`, source, sourceHandle: port.id, target: String(port.target), label: port.label,
    type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed }, className: 'story-flow-edge',
  }))), [document])

  function changeRoot(key: string, value: unknown) { onChange({ ...document, [key]: value }) }
  function changeNode(patch: Partial<ArcNode>) {
    if (!selected) return
    onChange({ ...document, nodes: { ...authoredNodes, [selectedId]: { ...selected, ...patch } } })
  }
  function persistPositions(current: FlowNode[]) {
    const positions = Object.fromEntries(current.map(node => [node.id, { x: Math.round(node.position.x), y: Math.round(node.position.y) }]))
    changeRoot('editor_layout', { ...(document.editor_layout as Json ?? {}), mode: 'manual', nodes: positions })
  }
  function applyLevelLayout(nextNodes = authoredNodes, nextEntry = entry) {
    const positions = levelLayout(nextNodes, nextEntry).positions
    onChange({ ...document, nodes: nextNodes, entry_node: nextEntry, editor_layout: { ...(document.editor_layout as Json ?? {}), mode: 'levels', nodes: positions } })
    requestAnimationFrame(() => flowInstance?.fitView({ padding: 0.12, duration: 250 }))
  }
  function onFlowNodesChange(changes: NodeChange<FlowNode>[]) { setFlowNodes(current => applyNodeChanges(changes, current)) }
  function connect(connection: Connection) {
    if (!connection.source || !connection.target || connection.source === connection.target) return
    const node = authoredNodes[connection.source]
    if (!node) return
    const handle = connection.sourceHandle ?? 'transition'
    let nextNode: ArcNode
    if (handle.startsWith('choice:')) {
      const index = Number(handle.split(':')[1])
      nextNode = { ...node, choices: (node.choices ?? []).map((choice, choiceIndex) => choiceIndex === index ? { ...choice, transition: { ...choice.transition, to: connection.target! } } : choice) }
    } else if (handle.startsWith('conditional:')) {
      const index = Number(handle.split(':')[1])
      nextNode = { ...node, transitions: (node.transitions ?? []).map((edge, edgeIndex) => edgeIndex === index ? { ...edge, to: connection.target! } : edge) }
    } else {
      nextNode = { ...node, transition: { ...node.transition, to: connection.target } }
    }
    applyLevelLayout({ ...authoredNodes, [connection.source]: nextNode })
  }
  function disconnect(edges: Edge[]) {
    const nextNodes = structuredClone(authoredNodes)
    for (const edge of edges) {
      const node = nextNodes[edge.source]
      const handle = edge.sourceHandle ?? 'transition'
      if (!node) continue
      if (handle.startsWith('choice:')) {
        const index = Number(handle.split(':')[1])
        node.choices = (node.choices ?? []).map((choice, choiceIndex) => choiceIndex === index ? { ...choice, transition: { ...choice.transition, to: '' } } : choice)
      } else if (handle.startsWith('conditional:')) {
        const index = Number(handle.split(':')[1])
        node.transitions = (node.transitions ?? []).filter((_, edgeIndex) => edgeIndex !== index)
      } else node.transition = undefined
    }
    applyLevelLayout(nextNodes)
  }
  function addNode(kind: string) {
    let index = nodeIds.length + 1, id = `${kind}_${index}`
    while (authoredNodes[id]) { index += 1; id = `${kind}_${index}` }
    const terminal = kind === 'terminal'
    const next: ArcNode = { kind, title: `新${kind}节点`, blocking: ['choice', 'timed'].includes(kind), narrative_template_md: '## 新的一幕\n\n请在此填写本地 Markdown。', effects: terminal ? [{ op: 'resolve_entry_event' }] : [] }
    if (['choice', 'timed'].includes(kind)) next.choices = []
    if (kind === 'automatic') next.transition = { to: '' }
    if (kind === 'timed') next.after_hours = 1
    applyLevelLayout({ ...authoredNodes, [id]: next })
    setSelectedId(id)
  }
  function removeNodes(ids: string[]) {
    const removing = new Set(ids)
    const next: Record<string, ArcNode> = {}
    for (const [id, node] of Object.entries(authoredNodes)) {
      if (removing.has(id)) continue
      next[id] = {
        ...node,
        transition: node.transition && removing.has(node.transition.to) ? undefined : node.transition,
        transitions: (node.transitions ?? []).filter(edge => !removing.has(edge.to)),
        choices: node.choices?.map(choice => removing.has(choice.transition?.to) ? { ...choice, transition: { ...choice.transition, to: '' } } : choice),
      }
    }
    const nextEntry = removing.has(entry) ? Object.keys(next)[0] ?? '' : entry
    applyLevelLayout(next, nextEntry)
    setSelectedId(nextEntry)
  }
  function addChoice() {
    if (!selected) return
    const current = selected.choices ?? []
    let index = current.length + 1, id = `choice_${index}`
    while (current.some(choice => choice.id === id)) { index += 1; id = `choice_${index}` }
    changeNode({ choices: [...current, { id, label: '新裁断', description_md: '说明确定性后果。', effects: [], transition: { to: '' } }] })
  }
  function patchChoice(index: number, patch: Partial<Choice>) { changeNode({ choices: (selected?.choices ?? []).map((choice, choiceIndex) => choiceIndex === index ? { ...choice, ...patch } : choice) }) }
  function removeChoice(index: number) {
    if (!selected) return
    applyLevelLayout({ ...authoredNodes, [selectedId]: { ...selected, choices: (selected.choices ?? []).filter((_, choiceIndex) => choiceIndex !== index) } })
  }

  return <div className="arc-editor">
    <div className="arc-toolbar">
      <label>剧情标题<input value={String(document.title ?? '')} onChange={event => changeRoot('title', event.target.value)} /></label>
      <label>入口<select value={entry} onChange={event => applyLevelLayout(authoredNodes, event.target.value)}>{nodeIds.map(id => <option key={id}>{id}</option>)}</select></label>
      <label>最大关键裁断<input type="number" min="1" value={Number(document.max_blocking_decisions ?? 3)} onChange={event => changeRoot('max_blocking_decisions', Number(event.target.value))} /></label>
      <div className="node-add"><button type="button" className="level-layout-button" onClick={() => applyLevelLayout()}>⇥ 按 Level 排列</button>{['choice', 'automatic', 'timed', 'terminal'].map(kind => <button type="button" key={kind} onClick={() => addNode(kind)}>+ {kind}</button>)}</div>
    </div>
    <div className="arc-workspace">
      <section className="flow-graph-board" aria-label="剧情图拖拽画布">
        <ReactFlow<FlowNode, Edge> nodes={flowNodes} edges={flowEdges} nodeTypes={{ storyArc: StoryArcNode }} onInit={setFlowInstance} onNodesChange={onFlowNodesChange} onNodeClick={(_, node) => setSelectedId(node.id)} onNodeDragStop={(_, node) => persistPositions(flowNodes.map(item => item.id === node.id ? node : item))} onConnect={connect} onEdgesDelete={disconnect} onNodesDelete={nodes => removeNodes(nodes.map(node => node.id))} fitView minZoom={0.2} maxZoom={1.8} snapToGrid snapGrid={[20, 20]}>
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#4b3c2e" />
          <MiniMap pannable zoomable nodeColor={node => node.data.kind === 'terminal' ? '#713e38' : node.data.kind === 'timed' ? '#514267' : '#765333'} maskColor="#090807aa" />
          <Controls showInteractive={false} />
        </ReactFlow>
        <div className="flow-help">默认按 Level 从左到右排列 · 可手动拖动 · 从出口圆点拖到目标节点建立箭头</div>
      </section>
      <aside className="node-inspector">
        {!selected && <p>选择一个节点开始编辑。</p>}
        {selected && <>
          <header><div><small>节点 Inspector</small><h3>{selectedId}</h3></div><button className="danger" type="button" onClick={() => { if (window.confirm(`删除节点 ${selectedId} 及关联箭头？`)) removeNodes([selectedId]) }}>删除节点</button></header>
          <label>类型<select value={selected.kind} onChange={event => changeNode({ kind: event.target.value })}>{['choice', 'automatic', 'timed', 'terminal'].map(kind => <option key={kind}>{kind}</option>)}</select></label>
          <label>标题<input value={selected.title ?? ''} onChange={event => changeNode({ title: event.target.value })} /></label>
          <label className="check"><input type="checkbox" checked={!!selected.blocking} onChange={event => changeNode({ blocking: event.target.checked })} />阻塞型裁断</label>
          <label>场景类型<input value={selected.scene_type ?? String(document.scene_type ?? 'daily')} onChange={event => changeNode({ scene_type: event.target.value })} /></label>
          {selected.kind === 'timed' && <div className="inline"><label>延时天<input type="number" min="0" value={selected.after_days ?? 0} onChange={event => changeNode({ after_days: Number(event.target.value) })} /></label><label>延时小时<input type="number" min="0" value={selected.after_hours ?? 0} onChange={event => changeNode({ after_hours: Number(event.target.value) })} /></label></div>}
          <label>本地 Markdown<textarea rows={7} value={selected.narrative_template_md ?? ''} onChange={event => changeNode({ narrative_template_md: event.target.value })} /></label>
          {['choice', 'timed'].includes(selected.kind) && <div className="choice-editor"><div className="section-heading"><b>合法选择 / 箭头出口</b><button type="button" onClick={addChoice}>+ 添加选择</button></div>{(selected.choices ?? []).map((choice, index) => <article key={`${choice.id}-${index}`}>
            <div className="inline"><label>choice id<input value={choice.id} onChange={event => patchChoice(index, { id: event.target.value })} /></label><label>当前目标<input value={choice.transition?.to ?? ''} readOnly placeholder="在画布拖箭头连接" /></label></div>
            <label>按钮文字<input value={choice.label} onChange={event => patchChoice(index, { label: event.target.value })} /></label>
            <label>后果说明<textarea rows={2} value={choice.description_md} onChange={event => patchChoice(index, { description_md: event.target.value })} /></label>
            <label>Effects JSON<textarea rows={3} value={JSON.stringify(choice.effects ?? [], null, 2)} onChange={event => { try { patchChoice(index, { effects: JSON.parse(event.target.value) }) } catch { /* keep last valid */ } }} /></label>
            <button className="danger text" type="button" onClick={() => removeChoice(index)}>删除此选择和箭头</button>
          </article>)}</div>}
          {selected.kind === 'automatic' && <>
            <label>过场展示<select value={selected.presentation ?? 'transition_log'} onChange={event => changeNode({ presentation: event.target.value as 'transition_log' | 'silent' })}><option value="transition_log">写入剧情过场</option><option value="silent">静默规则节点</option></select></label>
            <p className="inspector-hint">从出口拖动箭头设置目标。条件边必须填写唯一整数优先级；无条件 fallback 不填优先级。</p>
            <div className="choice-editor"><div className="section-heading"><b>条件迁移</b><button type="button" onClick={() => changeNode({ transitions: [...(selected.transitions ?? []), { to: '', when: { fact_equals: { key: 'value' } }, priority: ((selected.transitions ?? []).length + 1) * 10 }] })}>+ 添加条件边</button></div>
              {(selected.transitions ?? []).map((edge, index) => <article key={index}>
                <div className="inline"><label>优先级<input type="number" value={edge.priority ?? ''} onChange={event => changeNode({ transitions: (selected.transitions ?? []).map((row, rowIndex) => rowIndex === index ? { ...row, priority: Number(event.target.value) } : row) })} /></label><label>当前目标<input value={edge.to} readOnly placeholder="在画布拖箭头连接" /></label></div>
                <label>Condition JSON<textarea rows={3} value={JSON.stringify(edge.when ?? {}, null, 2)} onChange={event => { try { const when = JSON.parse(event.target.value); changeNode({ transitions: (selected.transitions ?? []).map((row, rowIndex) => rowIndex === index ? { ...row, when } : row) }) } catch { /* keep last valid */ } }} /></label>
                <button className="danger text" type="button" onClick={() => changeNode({ transitions: (selected.transitions ?? []).filter((_, rowIndex) => rowIndex !== index) })}>删除条件边</button>
              </article>)}
            </div>
          </>}
          <label>节点 Effects JSON<textarea rows={4} value={JSON.stringify(selected.effects ?? [], null, 2)} onChange={event => { try { changeNode({ effects: JSON.parse(event.target.value) }) } catch { /* keep last valid */ } }} /></label>
        </>}
      </aside>
    </div>
  </div>
}
