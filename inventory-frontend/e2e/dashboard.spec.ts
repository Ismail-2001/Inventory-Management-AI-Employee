import { test, expect } from '@playwright/test'

test.describe('Dashboard page', () => {
  test('shows dashboard heading and sync button', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Run Sync/ })).toBeVisible()
  })

  test('shows metric cards', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Accepted (as-is)', { exact: true })).toBeVisible()
    await expect(page.getByText('Edited then Approved', { exact: true })).toBeVisible()
    await expect(page.getByText('Rejected', { exact: true })).toBeVisible()
    await expect(page.getByText('Forecast Error', { exact: true })).toBeVisible()
  })

  test('shows recent sync section', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Recent Sync', { exact: true })).toBeVisible()
    await expect(page.getByText('Run a sync to see results', { exact: true })).toBeVisible()
  })

  test('shows forecast accuracy section', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Forecast Accuracy', { exact: true })).toBeVisible()
  })

  test('supports date range filtering', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: '7d' })).toBeVisible()
    await expect(page.getByRole('button', { name: '30d' })).toBeVisible()
    await expect(page.getByRole('button', { name: '90d' })).toBeVisible()
    await page.getByRole('button', { name: '7d' }).click()
    await expect(page.getByRole('button', { name: '7d' })).toHaveAttribute('aria-pressed', 'true')
  })
})
