import { test, expect } from '@playwright/test'

test.describe('Inventory page', () => {
  test('shows inventory heading and table', async ({ page }) => {
    await page.goto('/inventory')
    await expect(page.getByRole('heading', { name: 'Inventory' })).toBeVisible()
    await expect(page.getByText('All SKUs and stock levels')).toBeVisible()
  })

  test('shows table headers', async ({ page }) => {
    await page.goto('/inventory')
    await expect(page.getByRole('columnheader', { name: 'SKU' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Title' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Stock' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Location' })).toBeVisible()
  })

  test('shows empty state or SKU data', async ({ page }) => {
    await page.goto('/inventory')
    const emptyState = page.getByRole('cell', { name: /No SKUs found/ })
    const skuRow = page
      .locator('tbody tr')
      .filter({ hasNotText: 'No SKUs found' })
      .first()
    await expect(emptyState.or(skuRow)).toBeVisible()
  })
})
