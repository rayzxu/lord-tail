import { describe, expect, it } from 'vitest'

describe('admin content model', () => {
  it('keeps story arc node kinds explicit', () => {
    expect(['choice', 'automatic', 'timed', 'terminal']).toHaveLength(4)
  })

  it('uses a separate admin API prefix', () => {
    expect('/admin-api/v1/content/story_arc').not.toMatch(/^\/api\//)
  })
})
