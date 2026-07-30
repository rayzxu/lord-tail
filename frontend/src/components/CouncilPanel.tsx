import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  CouncilMeeting,
  ManagementAiState,
  ManagementDecision,
  ManagementMode,
  RealmAnalysis,
  StrategicDirective,
} from '../api'

const modeLabels: Record<ManagementMode, string> = {
  delegated: '委托管家执行',
  advisory: '大臣呈递候选',
  manual: '领主亲自裁决',
}

const metricLabels: Record<string, string> = {
  food_net_turn: '每轮粮食净变',
  food_runway_days: '粮食可维持天数',
  gold_net_turn: '每轮金币净变',
  gold_runway_days: '金库可维持天数',
  housing_vacant: '空余住房',
  employment_rate: '就业率',
  army_size: '兵力',
  organization: '组织度',
  military_readiness: '战备值',
  external_threat: '外部威胁',
  average_relation: '平均关系',
  hostile_neighbors: '敌对邻国',
  friendly_neighbors: '友好邻国',
  war_risk: '战争风险',
  morale: '民心',
  authority: '统治力',
}

function valueText(key: string, value: unknown) {
  if (value === null || value === undefined) return '稳定/未知'
  if (key === 'employment_rate' || key === 'war_risk') return `${Math.round(Number(value) * 100)}%`
  return typeof value === 'number' && !Number.isInteger(value) ? value.toFixed(2) : String(value)
}

type Props = {
  meeting: CouncilMeeting | null
  directive: StrategicDirective | null
  management: ManagementAiState | null
  analysis: RealmAnalysis | null
  decision: ManagementDecision | null
  loading: boolean
  error: string
  close: () => void
  resolveMeeting: (proposalId: string, mode: ManagementMode) => Promise<void>
  setMode: (mode: ManagementMode) => Promise<void>
  requestReview: () => Promise<void>
  loadAdvice: () => Promise<void>
  acceptAdvice: (decisionId: string, actionId: string) => Promise<void>
}

export default function CouncilPanel(props: Props) {
  const [proposalId, setProposalId] = useState('')
  const [mode, setLocalMode] = useState<ManagementMode>(props.management?.mode ?? 'delegated')

  useEffect(() => {
    setProposalId(props.meeting?.proposals[0]?.id ?? '')
  }, [props.meeting?.id])
  useEffect(() => {
    setLocalMode(props.management?.mode ?? 'delegated')
  }, [props.management?.mode])

  return <div className="modal-shade">
    <section className="detail-modal council-panel">
      <button className="close" onClick={props.close}>×</button>
      <div className="section-head">
        <div>
          <span className="section-label">领主议会与战略方针</span>
          <small>账册负责数值与合法性，大臣只陈奏理由和风险</small>
        </div>
      </div>
      {props.loading && <p>大臣正在铺开账册……</p>}
      {props.error && <p className="error">{props.error}</p>}

      {props.meeting
        ? <CouncilMeetingView
            meeting={props.meeting}
            proposalId={proposalId}
            setProposalId={setProposalId}
            mode={mode}
            setMode={setLocalMode}
            submit={() => props.resolveMeeting(proposalId, mode)}
            loading={props.loading}
          />
        : <DirectiveView
            directive={props.directive}
            management={props.management}
            analysis={props.analysis}
            decision={props.decision}
            loading={props.loading}
            setMode={props.setMode}
            requestReview={props.requestReview}
            loadAdvice={props.loadAdvice}
            acceptAdvice={props.acceptAdvice}
          />}
    </section>
  </div>
}

function CouncilMeetingView({
  meeting,
  proposalId,
  setProposalId,
  mode,
  setMode,
  submit,
  loading,
}: {
  meeting: CouncilMeeting
  proposalId: string
  setProposalId: (value: string) => void
  mode: ManagementMode
  setMode: (value: ManagementMode) => void
  submit: () => void
  loading: boolean
}) {
  return <>
    <div className="council-opening">
      <b>{meeting.reason === 'initial' ? '首次议事' : meeting.reason === 'emergency' ? '紧急议事' : '方针复议'}</b>
      <span>第 {meeting.opened_time.calendar_day} 日 {meeting.opened_time.clock_24}</span>
    </div>
    {!!meeting.crisis_summary.length && <div className="council-crisis">
      <strong>必须正视的危机</strong>
      <ul>{meeting.crisis_summary.map(item => <li key={item}>{item}</li>)}</ul>
    </div>}
    <div className="proposal-grid">
      {meeting.proposals.map(proposal => <label className={`proposal-card ${proposalId === proposal.id ? 'selected' : ''}`} key={proposal.id}>
        <input type="radio" name="proposal" checked={proposalId === proposal.id} onChange={() => setProposalId(proposal.id)} />
        <small>{proposal.minister} · {proposal.domain}</small>
        <h3>{proposal.title}</h3>
        <div className="council-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{proposal.speech_md}</ReactMarkdown></div>
        <dl>
          <dt>目标</dt><dd>{Object.entries(proposal.targets).map(([key, value]) => `${metricLabels[key] ?? key} ≥ ${value}`).join(' · ') || '保持储备'}</dd>
          <dt>预算</dt><dd>最多动用现有金币的 {Math.round(Number(proposal.budget_limits.gold_spend_ratio ?? 0) * 100)}%，最低保留 {proposal.budget_limits.minimum_gold_reserve ?? 0}</dd>
          <dt>风险</dt><dd>{proposal.risks.join(' ')}</dd>
        </dl>
      </label>)}
    </div>
    <div className="management-mode-picker">
      <strong>执行方式</strong>
      {(['delegated', 'advisory', 'manual'] as ManagementMode[]).map(item => <label key={item}>
        <input type="radio" name="management-mode" checked={mode === item} onChange={() => setMode(item)} />
        <span>{modeLabels[item]}</span>
      </label>)}
    </div>
    <button type="button" className="primary-button" disabled={!proposalId || loading} onClick={submit}>盖印采纳方针</button>
  </>
}

function DirectiveView({
  directive,
  management,
  analysis,
  decision,
  loading,
  setMode,
  requestReview,
  loadAdvice,
  acceptAdvice,
}: {
  directive: StrategicDirective | null
  management: ManagementAiState | null
  analysis: RealmAnalysis | null
  decision: ManagementDecision | null
  loading: boolean
  setMode: (mode: ManagementMode) => Promise<void>
  requestReview: () => Promise<void>
  loadAdvice: () => Promise<void>
  acceptAdvice: (decisionId: string, actionId: string) => Promise<void>
}) {
  if (!directive) return <div className="empty-council">
    <p>当前没有生效的战略方针。</p>
    <button type="button" className="primary-button" onClick={requestReview} disabled={loading}>召集大臣</button>
  </div>
  const remaining = Math.max(0, directive.duration_strategic_turns - directive.executed_strategic_turns)
  const metrics = analysis?.metrics ?? {}
  return <>
    <div className="directive-banner">
      <small>{directive.domain} · {directive.status}</small>
      <h2>{directive.title}</h2>
      <p>第 {directive.started_time.calendar_day} 日至第 {directive.expires_time.calendar_day} 日 · 预计剩余 {remaining} 个九日回合</p>
      <div className="directive-progress"><i style={{ width: `${Math.min(100, directive.executed_strategic_turns / Math.max(1, directive.duration_strategic_turns) * 100)}%` }} /></div>
    </div>
    <div className="strategy-metrics">
      {Object.entries(metrics).filter(([key]) => key in metricLabels).slice(0, 12).map(([key, value]) => <div className="stat-card" key={key}>
        <small>{metricLabels[key]}</small><b>{valueText(key, value)}</b>
      </div>)}
    </div>
    <div className="directive-targets">
      <h3>方针目标</h3>
      {Object.entries(directive.targets).map(([key, target]) => {
        const progress = directive.progress?.[key]
        return <p key={key}><span>{progress?.completed ? '✓' : '○'} {metricLabels[key] ?? key}</span><b>{valueText(key, progress?.actual)} / {target}</b></p>
      })}
    </div>
    <div className="management-toolbar">
      <label>领地管理方式
        <select value={management?.mode ?? 'delegated'} onChange={event => setMode(event.target.value as ManagementMode)} disabled={loading}>
          {Object.entries(modeLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
        </select>
      </label>
      <button type="button" className="ghost-button" onClick={loadAdvice} disabled={loading}>让大臣列出候选</button>
      <button type="button" className="ghost-button" onClick={requestReview} disabled={loading}>要求复议</button>
    </div>
    {management?.last_decision && <div className="last-decision">
      <small>上一轮管家行动</small>
      <b>{management.last_decision.selected_label}</b>
      <p>{management.last_decision.reason}</p>
    </div>}
    {decision && <div className="advice-list">
      <h3>大臣候选方案</h3>
      {decision.candidates.map(candidate => <article key={candidate.action.action_id}>
        <header><b>{candidate.label}</b><span>评分 {candidate.score.toFixed(2)}</span></header>
        <p>{candidate.reason}</p>
        <small>后续：{candidate.planned_sequence.join(' → ')}</small>
        <button type="button" className="ghost-button" onClick={() => acceptAdvice(decision.id, candidate.action.action_id)} disabled={loading}>采纳此项</button>
      </article>)}
    </div>}
  </>
}
