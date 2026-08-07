import { test, expect } from '@playwright/test'

test.describe('Purchase Orders page', () => {
  test('shows PO heading', async ({ page }) => {
    await page.goto('/purchase-orders')
    await expect(page.getByRole('heading', { name: 'Purchase Orders' })).toBeVisible()
    await expect(page.getByText(/Nothing here goes to a supplier/)).toBeVisible()
  })

  test('shows history section', async ({ page }) => {
    await page.goto('/purchase-orders')
    await expect(page.getByText('History')).toBeVisible()
  })

  test('shows pending section if there are pending orders', async ({ page }) => {
    await page.goto('/purchase-orders')
    const pendingSection = page.getByText(/Awaiting your decision/)
    const emptyHistory = page.getByText('No PO history yet')
    await expect(pendingSection.or(emptyHistory)).toBeVisible()
  })
})
