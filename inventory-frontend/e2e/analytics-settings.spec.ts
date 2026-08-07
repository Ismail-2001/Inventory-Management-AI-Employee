import { test, expect } from '@playwright/test'

test.describe('Analytics page', () => {
  test('shows analytics heading and action buttons', async ({ page }) => {
    await page.goto('/analytics')
    await expect(page.getByRole('heading', { name: 'Analytics' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Evaluate Outcomes/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /Run Weekly Report/ })).toBeVisible()
  })

  test('shows chart sections', async ({ page }) => {
    await page.goto('/analytics')
    await expect(page.getByText('PO Acceptance Rates')).toBeVisible()
    await expect(page.getByText('Forecast Error Distribution')).toBeVisible()
  })
})

test.describe('Settings page', () => {
  test('shows settings heading and sections', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
    await expect(page.getByText('API Configuration')).toBeVisible()
    await expect(page.getByText('Services')).toBeVisible()
    await expect(page.getByText('Environment')).toBeVisible()
    await expect(page.getByText('About')).toBeVisible()
  })

  test('shows service statuses', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByText('Shopify Sync')).toBeVisible()
    await expect(page.getByText('Postgres Database')).toBeVisible()
    await expect(page.getByText('LangGraph Agent')).toBeVisible()
  })
})
