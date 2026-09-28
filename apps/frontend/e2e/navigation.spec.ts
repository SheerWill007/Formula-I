import { test, expect } from '@playwright/test'

/**
 * E2E Tests for Navigation
 */
test.describe('Navigation', () => {
  test('should navigate through main pages', async ({ page }) => {
    await page.goto('/')
    
    // Navigate to Dashboard
    await page.getByRole('link', { name: /Dashboard/i }).first().click()
    await expect(page).toHaveURL('/dashboard')
    
    // Navigate to Sessions
    await page.getByRole('link', { name: /Sessions/i }).first().click()
    await expect(page).toHaveURL('/sessions')
    
    // Navigate to Schedule
    await page.getByRole('link', { name: /Calendar|Schedule/i }).first().click()
    await expect(page).toHaveURL('/schedule')
    
    // Navigate to Standings
    await page.getByRole('link', { name: /Standings/i }).first().click()
    await expect(page).toHaveURL('/standings')
  })

  test('should show active state on current page', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Dashboard link should have active styling
    const dashboardLink = page.getByRole('link', { name: /Dashboard/i }).first()
    
    // Check if it has active styling (color should be red #E10600)
    const color = await dashboardLink.evaluate((el) => 
      window.getComputedStyle(el).color
    )
    
    // Should have red color for active state
    expect(color).toMatch(/rgb\(225,\s*6,\s*0\)/)
  })

  test('should have working bottom navigation on mobile', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/')
    
    // Bottom nav should be visible
    const bottomNav = page.locator('nav').last()
    await expect(bottomNav).toBeVisible()
    
    // Should have navigation links
    await expect(bottomNav.getByRole('link', { name: /Home/i })).toBeVisible()
    await expect(bottomNav.getByRole('link', { name: /Dashboard/i })).toBeVisible()
  })

  test('should keep mobile navigation usable without horizontal overflow', async ({ page }) => {
    for (const width of [320, 375, 390, 412]) {
      await page.setViewportSize({ width, height: 844 })
      await page.goto('/')

      const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth)
      expect(pageWidth, `homepage overflows at ${width}px`).toBeLessThanOrEqual(width)

      const menuButton = page.getByRole('button', { name: 'Open menu' })
      await expect(menuButton).toBeVisible()
      await menuButton.click()
      await expect(page.getByRole('dialog', { name: 'Site navigation' })).toBeVisible()
      await expect(page.getByRole('dialog').getByRole('link', { name: 'Predictions' })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(page.getByRole('dialog', { name: 'Site navigation' })).toBeHidden()
    }

    await page.setViewportSize({ width: 1024, height: 768 })
    await page.goto('/')
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeHidden()
    await expect(page.locator('.topbar-nav-links')).toBeVisible()
    const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(pageWidth, 'homepage overflows at 1024px').toBeLessThanOrEqual(1024)
  })

  test('should navigate back to home from logo', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Click on logo
    await page.locator('a[href="/"]').first().click()
    
    // Should navigate to home
    await expect(page).toHaveURL('/')
  })
})
