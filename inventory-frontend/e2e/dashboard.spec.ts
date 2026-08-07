import { test, expect } from '@playwright/test'

test.describe('Dashboard page', () => {
  test('shows dashboard heading and sync button', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Run Sync/ })).toBeVisible()
  })

  test('shows metric cards', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Accepted (as-is)')).toBeVisible()
    await expect(page.getByText('Edited then Approved')).toBeVisible()
    await expect(page.getByText('Rejected')).toBeVisible()
    await expect(page.getByText('Forecast Error')).toBeVisible()
  })

  test('shows recent sync section', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Recent Sync')).toBeVisible()
    await expect(page.getByText('Run a sync to see results')).toBeVisible()
  })

  test('shows forecast accuracy section', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Forecast Accuracy')).toBeVisible()
  })
})
