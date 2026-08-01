import { expect, test, type APIRequestContext } from '@playwright/test'

async function draftIds(request: APIRequestContext) {
  const response = await request.get('http://127.0.0.1:18001/admin-api/v1/drafts')
  return (await response.json()).drafts.map((draft: { id: string }) => draft.id) as string[]
}

async function discardNewDrafts(request: APIRequestContext, before: string[]) {
  const after = await draftIds(request)
  await Promise.all(after.filter(id => !before.includes(id)).map(id => request.delete(`http://127.0.0.1:18001/admin-api/v1/drafts/${id}`)))
}

test('browse registry, create and discard an isolated draft', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByText('Admin API 已连接')).toBeVisible()

  await page.getByRole('button', { name: /物品与装备/ }).click()
  await expect(page.getByRole('heading', { name: '物品与装备' })).toBeVisible()
  page.once('dialog', dialog => dialog.accept('e2e_discarded_item'))
  await page.getByRole('button', { name: '+ 新增物品与装备' }).click()
  await expect(page.getByRole('heading', { name: 'e2e_discarded_item' })).toBeVisible()
  await page.getByLabel('名称').fill('E2E 测试短剑')
  await expect(page.getByText(/草稿已保存/)).toBeVisible()

  const drafts = await request.get('http://127.0.0.1:18001/admin-api/v1/drafts')
  const body = await drafts.json()
  const draft = body.drafts.find((item: { content_id: string }) => item.content_id === 'e2e_discarded_item')
  expect(draft).toBeTruthy()
  await request.delete(`http://127.0.0.1:18001/admin-api/v1/drafts/${draft.id}`)
})

test('story arc uses draggable nodes and connectable arrow handles', async ({ page, request }) => {
  const before = await draftIds(request)
  try {
    await page.goto('/')
    const row = page.locator('.table-row').filter({ hasText: 'spring_caravan_visit' })
    await row.getByRole('button', { name: '编辑' }).click()
    await expect(page.getByLabel('剧情图拖拽画布')).toBeVisible()
    await expect(page.locator('.react-flow__node')).toHaveCount(7)
    await expect(page.locator('.react-flow__edge').first()).toBeVisible()
    const entryBox = await page.getByTestId('rf__node-arrival_gate').boundingBox()
    const middleBox = await page.getByTestId('rf__node-trade_hearing').boundingBox()
    const terminalBox = await page.getByTestId('rf__node-visit_resolved').boundingBox()
    expect(entryBox!.x).toBeLessThan(middleBox!.x)
    expect(middleBox!.x).toBeLessThan(terminalBox!.x)
    await expect(page.getByRole('button', { name: /按 Level 排列/ })).toBeVisible()
    const edgeCount = await page.locator('.react-flow__edge').count()

    await page.getByRole('button', { name: '+ automatic' }).click()
    await page.locator('.react-flow__controls-fitview').click()
    await expect(page.locator('.react-flow__node')).toHaveCount(8)
    const source = page.locator('.react-flow__node.selected .react-flow__handle.source')
    const target = page.getByTestId('rf__node-arrival_gate').locator('.react-flow__handle.target')
    await source.dragTo(target)
    await expect(page.locator('.react-flow__edge')).toHaveCount(edgeCount + 1)
  } finally {
    await discardNewDrafts(request, before)
  }
})

test('storylet nodes render as structured forms instead of JSON textarea', async ({ page, request }) => {
  const before = await draftIds(request)
  try {
    await page.goto('/')
    await page.getByRole('button', { name: /Storylet/ }).click()
    const row = page.locator('.table-row').filter({ hasText: 'petition_building_credit' })
    await row.getByRole('button', { name: '编辑' }).click()
    await expect(page.getByText('Storylet Nodes')).toBeVisible()
    await expect(page.getByRole('heading', { name: '触发条件' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '角色选角规则' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '冻结参数' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '玩家选项' })).toBeVisible()
    await expect(page.getByText('resource minimum')).toBeVisible()
    await expect(page.locator('.storylet-node-form textarea.code')).toHaveCount(0)
  } finally {
    await discardNewDrafts(request, before)
  }
})
