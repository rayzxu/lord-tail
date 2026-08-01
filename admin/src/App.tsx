import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { adminApi, ContentDetail, ContentSummary, ContentType, Draft, Validation } from './api'
import StoryArcEditor from './editors/StoryArcEditor'
import StructuredEditor from './editors/StructuredEditor'

type View = 'content' | 'drafts' | 'revisions' | 'audit'

export default function App() {
  const [types, setTypes] = useState<ContentType[]>([])
  const [activeType, setActiveType] = useState('story_arc')
  const [view, setView] = useState<View>('content')
  const [registryRevision, setRegistryRevision] = useState('')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [toast, setToast] = useState('')

  async function bootstrap() {
    const [meta, contentTypes] = await Promise.all([adminApi.meta(), adminApi.contentTypes()])
    setRegistryRevision(meta.registry_revision); setTypes(contentTypes.content_types)
  }
  useEffect(() => { void bootstrap().catch(error => setToast(error.message)) }, [])

  const selectedType = types.find(item => item.id === activeType)
  return <div className="admin-shell">
    <aside className="admin-sidebar">
      <div className="admin-brand"><span>♜</span><div><small>Lord Tail</small><b>书记官内容工坊</b></div></div>
      <nav><button className={view === 'content' ? 'active' : ''} onClick={() => setView('content')}>内容总览</button>{types.map(type => <button key={type.id} className={view === 'content' && activeType === type.id ? 'active nested' : 'nested'} onClick={() => { setActiveType(type.id); setView('content'); setDraft(null) }}><span>{type.label}</span><em>{type.count}</em></button>)}</nav>
      <nav className="secondary-nav"><button className={view === 'drafts' ? 'active' : ''} onClick={() => { setView('drafts'); setDraft(null) }}>草稿箱</button><button className={view === 'revisions' ? 'active' : ''} onClick={() => { setView('revisions'); setDraft(null) }}>发布历史</button><button className={view === 'audit' ? 'active' : ''} onClick={() => { setView('audit'); setDraft(null) }}>审计日志</button></nav>
    </aside>
    <main className="admin-main">
      <header className="admin-topbar"><div><small>内容注册表</small><code title={registryRevision}>{registryRevision.slice(0, 24)}…</code></div><div><span className="health-dot" />Admin API 已连接</div></header>
      {draft ? <DraftEditor draft={draft} onDraft={setDraft} close={() => { setDraft(null); void bootstrap() }} notify={setToast} /> : <>
        {view === 'content' && selectedType && <ContentList type={selectedType} openDraft={setDraft} notify={setToast} />}
        {view === 'drafts' && <DraftList openDraft={setDraft} notify={setToast} />}
        {view === 'revisions' && <LogView kind="revisions" />}
        {view === 'audit' && <LogView kind="audit" />}
      </>}
    </main>
    {toast && <div className="toast" onAnimationEnd={() => setToast('')}>{toast}</div>}
  </div>
}

function ContentList({ type, openDraft, notify }: { type: ContentType; openDraft: (draft: Draft) => void; notify: (text: string) => void }) {
  const [items, setItems] = useState<ContentSummary[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<ContentDetail | null>(null)
  async function load() { setLoading(true); try { setItems((await adminApi.list(type.id, query)).content) } catch (error) { notify(error instanceof Error ? error.message : '读取失败') } finally { setLoading(false) } }
  useEffect(() => { void load() }, [type.id])
  async function create() {
    const id = window.prompt(`新建${type.label}的稳定 id（不可随意改名）`)
    if (!id) return
    try { openDraft(await adminApi.createDraft({ content_type: type.id, content_id: id, operation: 'create' })) } catch (error) { notify(error instanceof Error ? error.message : '创建失败') }
  }
  async function edit(item: ContentSummary) { try { openDraft(await adminApi.createDraft({ content_type: type.id, content_id: item.id, operation: 'update' })) } catch (error) { notify(error instanceof Error ? error.message : '创建草稿失败') } }
  async function archive(item: ContentSummary) { try { await adminApi.archive(item, item.status !== 'archived'); await load(); notify(item.status === 'archived' ? '内容已恢复' : '内容已归档') } catch (error) { notify(error instanceof Error ? error.message : '归档失败') } }
  async function remove(item: ContentSummary) {
    try {
      const proposal = await adminApi.deleteProposal(type.id, item.id)
      if (!proposal.can_hard_delete || !proposal.proposal_token) { notify(`不能删除：仍有 ${proposal.incoming.length} 处引用`); return }
      if (!window.confirm(`永久删除 ${type.id}/${item.id}？此操作只允许未被引用的内容。`)) return
      await adminApi.hardDelete(type.id, item.id, proposal.revision, proposal.proposal_token); await load(); notify('内容已永久删除')
    } catch (error) { notify(error instanceof Error ? error.message : '删除失败') }
  }
  return <section className="content-page">
    <header className="page-heading"><div><small>内容类型</small><h1>{type.label}</h1><p>共 {items.length} 份已发布卷宗 · 编辑会先创建草稿</p></div><button className="primary" onClick={create}>+ 新增{type.label}</button></header>
    <div className="content-tools"><input placeholder="搜索 id 或标题" value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void load() }} /><button onClick={() => void load()}>搜索</button></div>
    {loading ? <p className="empty">正在展开卷宗…</p> : !items.length ? <p className="empty">尚无内容。</p> : <div className="content-table"><div className="table-row table-head"><span>ID / 标题</span><span>版本</span><span>引用源</span><span>状态</span><span>操作</span></div>{items.map(item => <div className="table-row" key={item.id}><button className="title-cell" onClick={() => void adminApi.detail(type.id, item.id).then(setDetail)}><b>{item.title}</b><code>{item.id}</code></button><span>schema {item.schema_version}<small>v{item.content_version}</small></span><span><code>{item.source_file}</code></span><span className={`status ${item.status}`}>{item.status}</span><div className="row-actions"><button onClick={() => void edit(item)}>编辑</button><button onClick={() => void archive(item)}>{item.status === 'archived' ? '恢复' : '归档'}</button><button className="danger" onClick={() => void remove(item)}>删除</button></div></div>)}</div>}
    {detail && <DetailDrawer detail={detail} close={() => setDetail(null)} edit={() => void edit(detail)} />}
  </section>
}

function DetailDrawer({ detail, close, edit }: { detail: ContentDetail; close: () => void; edit: () => void }) {
  return <div className="drawer-shade" onMouseDown={event => { if (event.target === event.currentTarget) close() }}><aside className="detail-drawer"><header><div><small>{detail.content_type}</small><h2>{detail.title}</h2><code>{detail.id}</code></div><button onClick={close}>×</button></header><div className="detail-actions"><button className="primary" onClick={edit}>创建编辑草稿</button></div><section><h3>引用影响</h3><p>被 {detail.references.incoming.length} 处内容/存档引用，引用其他内容 {detail.references.outgoing.length} 处。</p>{detail.references.incoming.map((reference, index) => <code className="reference" key={index}>{reference.source_type}/{reference.source_id} · {reference.path}</code>)}</section><section><h3>已发布 JSON</h3><pre>{JSON.stringify(detail.document, null, 2)}</pre></section></aside></div>
}

function DraftList({ openDraft, notify }: { openDraft: (draft: Draft) => void; notify: (text: string) => void }) {
  const [drafts, setDrafts] = useState<Draft[]>([])
  async function load() { try { setDrafts((await adminApi.drafts()).drafts) } catch (error) { notify(error instanceof Error ? error.message : '草稿读取失败') } }
  useEffect(() => { void load() }, [])
  return <section className="content-page"><header className="page-heading"><div><small>未发布工作区</small><h1>草稿箱</h1><p>浏览器编辑只写入这里，发布后才改变正式 JSON。</p></div></header><div className="draft-grid">{drafts.map(draft => <article key={draft.id}><span className={draft.validation.valid ? 'valid' : 'invalid'}>{draft.validation.valid ? '可发布' : `${draft.validation.errors.length} 个错误`}</span><small>{draft.content_type}</small><h3>{draft.content_id}</h3><code>{draft.id}</code><p>{new Date(draft.updated_at).toLocaleString()}</p><div><button onClick={() => openDraft(draft)}>继续编辑</button><button className="danger" onClick={async () => { if (window.confirm('删除未发布草稿？')) { await adminApi.deleteDraft(draft.id); await load() } }}>丢弃</button></div></article>)}</div></section>
}

function DraftEditor({ draft: initial, onDraft, close, notify }: { draft: Draft; onDraft: (draft: Draft) => void; close: () => void; notify: (text: string) => void }) {
  const [draft, setDraft] = useState(initial)
  const [document, setDocument] = useState<Record<string, unknown>>(initial.document)
  const [mode, setMode] = useState<'form' | 'json'>('form')
  const [jsonText, setJsonText] = useState(JSON.stringify(initial.document, null, 2))
  const [jsonError, setJsonError] = useState('')
  const [saveState, setSaveState] = useState<'saved' | 'dirty' | 'saving'>('saved')
  const [preview, setPreview] = useState<{ graph?: { paths: string[][]; path_count: number; max_blocking_decisions: number }; validation?: Validation } | null>(null)
  const [diff, setDiff] = useState('')
  const [summary, setSummary] = useState('')
  const lastSaved = useRef(JSON.stringify(initial.document))
  useEffect(() => { onDraft(draft) }, [draft])
  useEffect(() => {
    const serialized = JSON.stringify(document)
    if (serialized === lastSaved.current) return
    setSaveState('dirty')
    const timer = window.setTimeout(async () => {
      setSaveState('saving')
      try { const saved = await adminApi.updateDraft(draft, document); setDraft(saved); lastSaved.current = JSON.stringify(document); setSaveState('saved') }
      catch (error) { setSaveState('dirty'); notify(error instanceof Error ? error.message : '草稿保存失败') }
    }, 700)
    return () => window.clearTimeout(timer)
  }, [document])
  function changeDocument(next: Record<string, unknown>) { setDocument(next); setJsonText(JSON.stringify(next, null, 2)); setJsonError('') }
  function changeJson(value: string) { setJsonText(value); try { const parsed = JSON.parse(value); if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('根节点必须是对象'); setDocument(parsed); setJsonError('') } catch (error) { setJsonError(error instanceof Error ? error.message : 'JSON 无效') } }
  async function ensureSaved() {
    if (JSON.stringify(document) === lastSaved.current) return draft
    const saved = await adminApi.updateDraft(draft, document); setDraft(saved); lastSaved.current = JSON.stringify(document); setSaveState('saved'); return saved
  }
  async function validateAndPreview() { try { const saved = await ensureSaved(); setPreview(await adminApi.previewDraft(saved.id)); setDraft(await adminApi.draft(saved.id)) } catch (error) { notify(error instanceof Error ? error.message : '预览失败') } }
  async function publish() { try { const saved = await ensureSaved(); const result = await adminApi.publishDraft(saved, summary); notify(result.restart_required ? `已发布；${result.warnings.join('；')}` : '发布成功，游戏注册表已热重载'); close() } catch (error) { notify(error instanceof Error ? error.message : '发布失败') } }
  return <section className="draft-editor-page">
    <header className="draft-header"><button onClick={close}>← 返回</button><div><small>{draft.operation === 'create' ? '新建内容' : '编辑草稿'} · {draft.content_type}</small><h1>{draft.content_id}</h1></div><span className={`save-state ${saveState}`}>{saveState === 'saved' ? '草稿已保存' : saveState === 'saving' ? '保存中…' : '有未保存修改'}</span><div className="draft-actions"><button onClick={() => void adminApi.diffDraft(draft.id).then(value => setDiff(value.diff))}>查看 Diff</button><button onClick={() => void validateAndPreview()}>校验与预览</button><button className="primary" disabled={!draft.validation.valid || !!jsonError || saveState === 'saving'} onClick={() => void publish()}>发布</button></div></header>
    <div className="editor-tabs"><button className={mode === 'form' ? 'active' : ''} onClick={() => setMode('form')}>图形/表单</button><button className={mode === 'json' ? 'active' : ''} onClick={() => setMode('json')}>高级 JSON</button><label>发布摘要<input value={summary} onChange={event => setSummary(event.target.value)} placeholder="说明这次内容改动" /></label></div>
    <div className="editor-body"><main className="editor-surface">{mode === 'json' ? <><textarea className="json-editor" value={jsonText} onChange={event => changeJson(event.target.value)} />{jsonError && <p className="error">JSON 尚未保存：{jsonError}</p>}</> : draft.content_type === 'story_arc' ? <StoryArcEditor document={document} onChange={changeDocument} /> : <StructuredEditor type={draft.content_type} document={document} onChange={changeDocument} />}</main><aside className="validation-panel"><h3>校验结果</h3><ValidationView validation={preview?.validation ?? draft.validation} />{preview?.graph && <section><h4>路径分析</h4><p>{preview.graph.path_count} 条 choice 路径 · 最多 {preview.graph.max_blocking_decisions} 次关键裁断</p>{preview.graph.paths.slice(0, 20).map((path, index) => <code className="path" key={index}>{path.join(' → ')}</code>)}</section>}<section><h4>Markdown 预览</h4><div className="markdown-preview"><ReactMarkdown remarkPlugins={[remarkGfm]}>{findNarrative(document)}</ReactMarkdown></div></section></aside></div>
    {diff && <div className="diff-modal"><section><header><h2>草稿与已发布版本</h2><button onClick={() => setDiff('')}>×</button></header><pre>{diff || '没有差异'}</pre></section></div>}
  </section>
}

function ValidationView({ validation }: { validation: Validation }) {
  const rows = [...validation.errors, ...validation.warnings, ...validation.info]
  return <div className="validation-list"><span className={validation.valid ? 'validation-ok' : 'validation-bad'}>{validation.valid ? '✓ 可以发布' : `✕ ${validation.errors.length} 个错误阻止发布`}</span>{rows.map((issue, index) => <article key={`${issue.code}-${index}`} className={issue.severity}><b>{issue.code}</b><code>{issue.path || 'root'}</code><p>{issue.message}</p></article>)}</div>
}

function findNarrative(document: Record<string, unknown>) {
  if (typeof document.description_md === 'string') return document.description_md
  const nodes = document.nodes
  if (Array.isArray(nodes)) return String((nodes[0] as Record<string, unknown> | undefined)?.narrative_template_md ?? '')
  if (nodes && typeof nodes === 'object') return String(Object.values(nodes as Record<string, Record<string, unknown>>)[0]?.narrative_template_md ?? '')
  return ''
}

function LogView({ kind }: { kind: 'revisions' | 'audit' }) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  async function load() { const value = kind === 'revisions' ? await adminApi.revisions() : await adminApi.audit(); setRows(kind === 'revisions' ? (value as { revisions: Record<string, unknown>[] }).revisions : (value as { audit: Record<string, unknown>[] }).audit) }
  useEffect(() => { void load() }, [kind])
  return <section className="content-page"><header className="page-heading"><div><small>不可变维护记录</small><h1>{kind === 'revisions' ? '发布历史' : '审计日志'}</h1></div></header><div className="log-list">{rows.map((row, index) => <article key={String(row.id ?? index)}><header><b>{String(row.action ?? row.content_type ?? 'revision')}</b><time>{String(row.time ?? '')}</time></header><code>{String(row.content_type ?? '')}/{String(row.content_id ?? '')}</code><p>{String(row.summary ?? '')}</p>{kind === 'revisions' && row.before_document != null && <button onClick={async () => { const id = String(row.id); if (window.confirm(`把 ${String(row.content_type)}/${String(row.content_id)} 回滚到 ${id} 发布前？此操作会产生新的 revision。`)) { await adminApi.rollbackRevision(id); await load() } }}>回滚到发布前</button>}<pre>{JSON.stringify(row, null, 2)}</pre></article>)}</div></section>
}
