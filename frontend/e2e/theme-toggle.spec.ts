import { test, expect } from '@playwright/test'

/**
 * E2E Tests for Theme Toggle Functionality
 */
test.describe('Theme Toggle', () => {
  test('should toggle between light and dark themes', async ({ page }) => {
    await page.goto('/')
    
    // Get the html element to check data-theme attribute
    const html = page.locator('html')
    
    // Default should be dark theme
    await expect(html).toHaveAttribute('data-theme', 'dark')
    
    // Find and click the theme toggle button
    const themeButton = page.locator('button[title*="light mode"], button[title*="dark mode"]')
    await themeButton.click()
    
    // Should switch to light theme
    await expect(html).toHaveAttribute('data-theme', 'light')
    
    // Click again to switch back
    await themeButton.click()
    await expect(html).toHaveAttribute('data-theme', 'dark')
  })

  test('should apply theme colors to the page', async ({ page }) => {
    await page.goto('/')
    
    // Check that CSS variables are applied
    const body = page.locator('body')
    
    // In dark mode, background should be dark
    const bgColor = await body.evaluate((el) => 
      window.getComputedStyle(el).backgroundColor
    )
    
    // Should have a dark background (rgb values close to black)
    expect(bgColor).toMatch(/rgb\(0,\s*0,\s*0\)/)
  })

  test('should persist theme across navigation', async ({ page }) => {
    await page.goto('/')
    
    const html = page.locator('html')
    const themeButton = page.locator('button[title*="light mode"], button[title*="dark mode"]')
    
    // Switch to light theme
    await themeButton.click()
    await expect(html).toHaveAttribute('data-theme', 'light')
    
    // Navigate to dashboard
    await page.goto('/dashboard')
    
    // Theme should still be light
    await expect(html).toHaveAttribute('data-theme', 'light')
  })
})
