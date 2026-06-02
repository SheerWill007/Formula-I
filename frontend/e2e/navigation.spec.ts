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

  test('should navigate back to home from logo', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Click on logo
    await page.locator('a[href="/"]').first().click()
    
    // Should navigate to home
    await expect(page).toHaveURL('/')
  })
})
