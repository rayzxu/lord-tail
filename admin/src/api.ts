export type ContentType = { id: string; label: string; editable: boolean; editor: string; count: number }
export type ContentSummary = { content_type: string; id: string; title: string; status: string; schema_version: number; content_version: number; tags: string[]; source_file: string; revision: string }
export type ValidationIssue = { severity: 'error' | 'warning' | 'info'; code: string; path: string; message: string; suggestion?: string }
export type Validation = { valid: boolean; errors: ValidationIssue[]; warnings: ValidationIssue[]; info: ValidationIssue[] }
export type Draft = { id: string; content_type: string; content_id: string; operation: string; base_revision: string; document: Record<string, unknown>; status: string; revision: string; validation: Validation; created_at: string; updated_at: string }
export type Reference = { source_type?: string; source_id?: string; target_type?: string; target_id?: string; path: string; kind?: string }
export type ReferenceReport = { incoming: Reference[]; outgoing: Reference[]; can_hard_delete: boolean }
export type ContentDetail = ContentSummary & { document: Record<string, unknown>; references: ReferenceReport }
export type GraphPreview = { reachable_nodes: string[]; terminal_nodes: string[]; path_count: number; paths: string[][]; max_blocking_decisions: number }

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) } })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : detail?.code ? `${detail.code}: ${detail.errors?.[0]?.message ?? ''}` : `请求失败：HTTP ${response.status}`)
  }
  return response.status === 204 ? undefined as T : response.json()
}

export const adminApi = {
  health: () => fetch('/admin-health').then(response => response.json()),
  meta: () => request<{ registry_revision: string }>('/admin-api/v1/meta'),
  contentTypes: () => request<{ content_types: ContentType[] }>('/admin-api/v1/content-types'),
  list: (type: string, query = '') => request<{ content: ContentSummary[]; total: number }>(`/admin-api/v1/content/${encodeURIComponent(type)}?query=${encodeURIComponent(query)}`),
  detail: (type: string, id: string) => request<ContentDetail>(`/admin-api/v1/content/${encodeURIComponent(type)}/${encodeURIComponent(id)}`),
  drafts: () => request<{ drafts: Draft[] }>('/admin-api/v1/drafts'),
  draft: (id: string) => request<Draft>(`/admin-api/v1/drafts/${encodeURIComponent(id)}`),
  createDraft: (payload: { content_type: string; content_id: string; operation: 'create' | 'update'; document?: Record<string, unknown> }) => request<Draft>('/admin-api/v1/drafts', { method: 'POST', body: JSON.stringify(payload) }),
  updateDraft: (draft: Draft, document: Record<string, unknown>) => request<Draft>(`/admin-api/v1/drafts/${encodeURIComponent(draft.id)}`, { method: 'PUT', body: JSON.stringify({ document, expected_revision: draft.revision }) }),
  deleteDraft: (id: string) => request<void>(`/admin-api/v1/drafts/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  validateDraft: (id: string) => request<Validation>(`/admin-api/v1/drafts/${encodeURIComponent(id)}/validate`, { method: 'POST' }),
  previewDraft: (id: string) => request<{ validation: Validation; graph?: GraphPreview; character?: Record<string, unknown>; item?: Record<string, unknown> }>(`/admin-api/v1/drafts/${encodeURIComponent(id)}/preview`, { method: 'POST' }),
  diffDraft: (id: string) => request<{ diff: string }>(`/admin-api/v1/drafts/${encodeURIComponent(id)}/diff`),
  publishDraft: (draft: Draft, summary: string) => request<{ published: boolean; registry_revision: string; restart_required: boolean; warnings: string[] }>(`/admin-api/v1/drafts/${encodeURIComponent(draft.id)}/publish`, { method: 'POST', body: JSON.stringify({ expected_revision: draft.revision, summary, idempotency_key: `${draft.id}:${draft.revision}` }) }),
  archive: (item: ContentSummary, archived: boolean) => request<Record<string, unknown>>(`/admin-api/v1/content/${encodeURIComponent(item.content_type)}/${encodeURIComponent(item.id)}/${archived ? 'archive' : 'restore'}`, { method: 'POST', body: JSON.stringify({ expected_revision: item.revision, summary: archived ? 'Admin 归档' : 'Admin 恢复' }) }),
  deleteProposal: (type: string, id: string) => request<{ incoming: Reference[]; can_hard_delete: boolean; revision: string; proposal_token?: string }>(`/admin-api/v1/content/${encodeURIComponent(type)}/${encodeURIComponent(id)}/delete-proposal`, { method: 'POST' }),
  hardDelete: (type: string, id: string, revision: string, proposalToken: string) => request<Record<string, unknown>>(`/admin-api/v1/content/${encodeURIComponent(type)}/${encodeURIComponent(id)}/delete`, { method: 'POST', body: JSON.stringify({ expected_revision: revision, proposal_token: proposalToken, confirmation: `DELETE ${type}/${id}` }) }),
  revisions: () => request<{ revisions: Record<string, unknown>[] }>('/admin-api/v1/revisions'),
  rollbackRevision: (id: string) => request<Record<string, unknown>>(`/admin-api/v1/revisions/${encodeURIComponent(id)}/rollback`, { method: 'POST', body: JSON.stringify({ summary: `Admin 回滚 ${id}` }) }),
  audit: () => request<{ audit: Record<string, unknown>[] }>('/admin-api/v1/audit'),
}
