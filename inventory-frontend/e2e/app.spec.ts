import { test, expect } from '@playwright/test'

test.describe('App shell', () => {
  test('loads the dashboard by default', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  })

  test('has working navigation sidebar', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Inventory Employee')).toBeVisible()

    await page.click('a[href="/inventory"]')
    await expect(page.getByRole('heading', { name: 'Inventory' })).toBeVisible()

    await page.click('a[href="/purchase-orders"]')
    await expect(page.getByRole('heading', { name: 'Purchase Orders' })).toBeVisible()

    await page.click('a[href="/analytics"]')
    await expect(page.getByRole('heading', { name: 'Analytics' })).toBeVisible()

    await page.click('a[href="/settings"]')
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  })

  test('highlights active nav item', async ({ page }) => {
    await page.goto('/inventory')
    const inventoryLinks = page.locator('a[href="/inventory"]')
    await expect(inventoryLinks.first()).toHaveClass(/text-accent/)
  })
})
