import { useEffect, useState, type ReactNode } from 'react'
import './workflow.css'

type Json = Record<string, unknown>
type StoryletNode = Json & { id?: string; node_key?: string; title?: string; choices?: Json[] }

const labels: Record<string, string> = {
  id: '定义 ID', node_key: '节点 Key', title: '标题', category: '分类', source_kind: '来源类型',
  priority: '优先级', base_weight: '基础权重', cooldown_days: '冷却天数', blocking: '阻塞事件',
  scene_type: '场景类型', triggers: '触发条件', roles: '角色选角规则', parameters: '冻结参数',
  narrative_template_md: '本地 Markdown 模板', choices: '玩家选项', effects: '确定性效果',
  description_md: '后果说明', confirm: '需要确认', op: '操作', required: '必需', distinct: '人物不可重复',
}

function labelFor(key: string) { return labels[key] ?? key.replaceAll('_', ' ') }
function defaultArrayValue(path: string): unknown {
  if (path.endsWith('.effects')) return { op: 'append_history' }
  if (path.endsWith('.choices')) return { id: 'new_choice', label: '新选项', description_md: '说明确定性后果。', confirm: false, effects: [{ op: 'append_history' }] }
  return ''
}

export default function StoryletEditor({ document, onChange }: { document: Json; onChange: (next: Json) => void }) {
  const nodes = Array.isArray(document.nodes) ? document.nodes as StoryletNode[] : []
  const [selectedIndex, setSelectedIndex] = useState(0)
  useEffect(() => { if (selectedIndex >= nodes.length) setSelectedIndex(Math.max(0, nodes.length - 1)) }, [nodes.length])
  const selected = nodes[selectedIndex]
  function patchRoot(key: string, value: unknown) { onChange({ ...document, [key]: value }) }
  function updateNode(next: StoryletNode) { patchRoot('nodes', nodes.map((node, index) => index === selectedIndex ? next : node)) }
  function addNode() {
    let index = nodes.length + 1, key = `node_${index}`
    while (nodes.some(node => node.node_key === key)) { index += 1; key = `node_${index}` }
    const next: StoryletNode = {
      id: String(document.chain_id ?? ''), node_key: key, title: '新 Storylet 节点', category: 'daily',
      source_kind: 'realm', priority: 'minor', base_weight: 1, cooldown_days: 30, blocking: true,
      scene_type: 'daily', triggers: {}, roles: {}, parameters: {},
      narrative_template_md: '## 新事件\n\n等待领主裁断。',
      choices: [{ id: 'acknowledge', label: '知晓', description_md: '书记官记录此事。', confirm: false, effects: [{ op: 'append_history' }] }],
    }
    patchRoot('nodes', [...nodes, next]); setSelectedIndex(nodes.length)
  }
  function removeNode(index: number) {
    if (!window.confirm(`删除 Storylet 节点 ${nodes[index]?.node_key ?? index}？`)) return
    patchRoot('nodes', nodes.filter((_, nodeIndex) => nodeIndex !== index)); setSelectedIndex(Math.max(0, index - 1))
  }
  function duplicateNode(index: number) {
    const source = structuredClone(nodes[index])
    let suffix = 2, key = `${source.node_key || 'node'}_copy`
    while (nodes.some(node => node.node_key === key)) { key = `${source.node_key || 'node'}_copy_${suffix++}` }
    source.node_key = key
    patchRoot('nodes', [...nodes.slice(0, index + 1), source, ...nodes.slice(index + 1)]); setSelectedIndex(index + 1)
  }

  return <div className="storylet-editor">
    <div className="storylet-root form-grid">
      <label>Chain ID<input value={String(document.chain_id ?? '')} onChange={event => patchRoot('chain_id', event.target.value)} /></label>
      <label>Schema<input value={String(document.schema_version ?? 1)} disabled /></label>
    </div>
    <div className="storylet-workspace">
      <aside className="storylet-node-list">
        <header><div><small>Storylet Nodes</small><b>{nodes.length} 个节点</b></div><button type="button" onClick={addNode}>+ 节点</button></header>
        {nodes.map((node, index) => <button type="button" key={`${node.node_key}-${index}`} className={selectedIndex === index ? 'active' : ''} onClick={() => setSelectedIndex(index)}><b>{node.title || node.node_key || `节点 ${index + 1}`}</b><code>{node.node_key || 'missing_key'}</code><span>{String(node.priority ?? 'minor')} · {String(node.scene_type ?? 'daily')}</span></button>)}
      </aside>
      <main className="storylet-node-form">
        {!selected ? <div className="empty">尚无节点，点击“+ 节点”创建。</div> : <>
          <header><div><small>节点表单</small><h2>{selected.title || selected.node_key}</h2></div><div><button type="button" onClick={() => duplicateNode(selectedIndex)}>复制节点</button><button className="danger" type="button" onClick={() => removeNode(selectedIndex)}>删除节点</button></div></header>
          <section className="storylet-basics form-grid">
            <Field label="定义 ID"><input value={String(selected.id ?? '')} onChange={event => updateNode({ ...selected, id: event.target.value })} /></Field>
            <Field label="节点 Key"><input value={String(selected.node_key ?? '')} onChange={event => updateNode({ ...selected, node_key: event.target.value })} /></Field>
            <Field label="标题"><input value={String(selected.title ?? '')} onChange={event => updateNode({ ...selected, title: event.target.value })} /></Field>
            <Field label="分类"><input value={String(selected.category ?? '')} onChange={event => updateNode({ ...selected, category: event.target.value })} /></Field>
            <Field label="来源类型"><select value={String(selected.source_kind ?? 'realm')} onChange={event => updateNode({ ...selected, source_kind: event.target.value })}><option>realm</option><option>character</option><option>scheduled</option></select></Field>
            <Field label="优先级"><select value={String(selected.priority ?? 'minor')} onChange={event => updateNode({ ...selected, priority: event.target.value })}><option>major</option><option>minor</option></select></Field>
            <Field label="基础权重"><input type="number" value={Number(selected.base_weight ?? 1)} onChange={event => updateNode({ ...selected, base_weight: Number(event.target.value) })} /></Field>
            <Field label="冷却天数"><input type="number" min="0" value={Number(selected.cooldown_days ?? 0)} onChange={event => updateNode({ ...selected, cooldown_days: Number(event.target.value) })} /></Field>
            <Field label="场景类型"><input value={String(selected.scene_type ?? 'daily')} onChange={event => updateNode({ ...selected, scene_type: event.target.value })} /></Field>
            <label className="check"><input type="checkbox" checked={!!selected.blocking} onChange={event => updateNode({ ...selected, blocking: event.target.checked })} />阻塞时间推进</label>
            <label className="wide">本地 Markdown 模板<textarea rows={7} value={String(selected.narrative_template_md ?? '')} onChange={event => updateNode({ ...selected, narrative_template_md: event.target.value })} /></label>
          </section>
          <AutoSection title="触发条件" hint="事件导演只有在这些条件同时满足时才会选择此节点。" value={selected.triggers ?? {}} path="node.triggers" onChange={value => updateNode({ ...selected, triggers: value })} />
          <AutoSection title="角色选角规则" hint="每个字段是一种剧情角色，值为该角色的匹配与生成人物规则。" value={selected.roles ?? {}} path="node.roles" onChange={value => updateNode({ ...selected, roles: value })} />
          <AutoSection title="冻结参数" hint="进入事件时生成一次并冻结，后续描述与效果共享同一份事实。" value={selected.parameters ?? {}} path="node.parameters" onChange={value => updateNode({ ...selected, parameters: value })} />
          <ChoiceForm choices={Array.isArray(selected.choices) ? selected.choices : []} onChange={choices => updateNode({ ...selected, choices })} />
        </>}
      </main>
    </div>
  </div>
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label>{label}{children}</label> }

function AutoSection({ title, hint, value, path, onChange }: { title: string; hint: string; value: unknown; path: string; onChange: (value: Json) => void }) {
  return <section className="auto-section"><header><div><h3>{title}</h3><p>{hint}</p></div></header><AutoValue value={value} path={path} onChange={next => onChange(next as Json)} /></section>
}

function ChoiceForm({ choices, onChange }: { choices: Json[]; onChange: (choices: Json[]) => void }) {
  function patch(index: number, key: string, value: unknown) { onChange(choices.map((choice, choiceIndex) => choiceIndex === index ? { ...choice, [key]: value } : choice)) }
  return <section className="auto-section choices-form"><header><div><h3>玩家选项</h3><p>选项文字、确定性效果和可选确认步骤。</p></div><button type="button" onClick={() => onChange([...choices, defaultArrayValue('node.choices') as Json])}>+ 选项</button></header>{choices.map((choice, index) => <article key={`${choice.id}-${index}`}>
    <header><b>{String(choice.label || choice.id || `选项 ${index + 1}`)}</b><button className="danger text" type="button" onClick={() => onChange(choices.filter((_, choiceIndex) => choiceIndex !== index))}>删除</button></header>
    <div className="form-grid"><Field label="Choice ID"><input value={String(choice.id ?? '')} onChange={event => patch(index, 'id', event.target.value)} /></Field><Field label="按钮文字"><input value={String(choice.label ?? '')} onChange={event => patch(index, 'label', event.target.value)} /></Field><label className="check"><input type="checkbox" checked={!!choice.confirm} onChange={event => patch(index, 'confirm', event.target.checked)} />需要二次确认</label><label className="wide">后果说明<textarea rows={3} value={String(choice.description_md ?? '')} onChange={event => patch(index, 'description_md', event.target.value)} /></label></div>
    <div className="nested-effects"><b>Effects</b><AutoValue value={Array.isArray(choice.effects) ? choice.effects : []} path="node.choices.effects" onChange={value => patch(index, 'effects', value)} /></div>
  </article>)}</section>
}

function AutoValue({ value, path, onChange, removable }: { value: unknown; path: string; onChange: (value: unknown) => void; removable?: () => void }) {
  if (Array.isArray(value)) return <div className="auto-array">{value.map((item, index) => <div className="auto-array-item" key={index}><span className="item-index">#{index + 1}</span><AutoValue value={item} path={`${path}[${index}]`} onChange={next => onChange(value.map((current, itemIndex) => itemIndex === index ? next : current))} removable={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))} /></div>)}<button type="button" onClick={() => onChange([...value, defaultArrayValue(path)])}>+ 添加一项</button></div>
  if (value && typeof value === 'object') {
    const object = value as Json
    return <div className="auto-object">{Object.entries(object).map(([key, child]) => <div className="auto-field" key={key}><header><label>{labelFor(key)}</label><button className="danger text" type="button" onClick={() => { const next = { ...object }; delete next[key]; onChange(next) }}>移除字段</button></header><AutoValue value={child} path={`${path}.${key}`} onChange={nextValue => onChange({ ...object, [key]: nextValue })} /></div>)}<button type="button" onClick={() => { const key = window.prompt('新增字段名（必须与后端注册项一致）'); if (key && !(key in object)) onChange({ ...object, [key]: '' }) }}>+ 添加字段</button>{removable && <button className="danger text remove-item" type="button" onClick={removable}>删除此项</button>}</div>
  }
  const content = typeof value === 'boolean'
    ? <label className="check"><input type="checkbox" checked={value} onChange={event => onChange(event.target.checked)} />{value ? '是' : '否'}</label>
    : typeof value === 'number'
      ? <input type="number" value={value} onChange={event => onChange(Number(event.target.value))} />
      : String(value ?? '').includes('\n') || path.endsWith('text')
        ? <textarea rows={3} value={String(value ?? '')} onChange={event => onChange(event.target.value)} />
        : <input value={String(value ?? '')} onChange={event => onChange(event.target.value)} />
  return <div className="auto-scalar">{content}{removable && <button className="danger text" type="button" onClick={removable}>删除</button>}</div>
}
