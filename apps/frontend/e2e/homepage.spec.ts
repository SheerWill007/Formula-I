import { test, expect } from '@playwright/test'

/**
 * E2E Tests for Homepage
 */
test.describe('Homepage', () => {
  test('should load successfully', async ({ page }) => {
    await page.goto('/')
    
    // Check that the page loaded
    await expect(page).toHaveTitle(/Formula 1/i)
  })

  test('should display hero section', async ({ page }) => {
    await page.goto('/')
    
    // Check for hero content
    await expect(page.getByText(/Precision in Every Millisecond/i)).toBeVisible()
    await expect(page.getByText(/Enter BoxUp/i)).toBeVisible()
  })

  test('should navigate to dashboard', async ({ page }) => {
    await page.goto('/')
    
    // Click the dashboard button
    await page.getByRole('link', { name: /Enter BoxUp/i }).click()
    
    // Should navigate to dashboard
    await expect(page).toHaveURL('/dashboard')
  })

  test('should display feature sections', async ({ page }) => {
    await page.goto('/')
    
    // Check for feature sections
    await expect(page.getByText(/Technical Mastery/i)).toBeVisible()
    await expect(page.getByText(/Telemetry/i)).toBeVisible()
    await expect(page.getByText(/Strategy/i)).toBeVisible()
    await expect(page.getByText(/AutoML Inference/i)).toBeVisible()
  })

  test('should have working navigation links', async ({ page }) => {
    await page.goto('/')
    
    // Check footer links
    await expect(page.getByRole('link', { name: /GitHub/i })).toBeVisible()
  })
})
