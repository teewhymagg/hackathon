import { Page } from 'playwright';
import { log } from '../utils';
import {
  googleChatButtonSelectors,
  googleChatInputSelectors,
  googleChatSendButtonSelectors,
  googleChatPanelSelectors
} from '../platforms/googlemeet/selectors';

/**
 * Google Meet Chat Service
 * Handles opening chat panel and sending messages
 */
export class GoogleMeetChatService {
  private page: Page | null = null;

  constructor(page: Page) {
    this.page = page;
  }

  /**
   * Check if chat panel is currently open
   */
  async isChatOpen(): Promise<boolean> {
    if (!this.page) {
      log('[Chat] Page not available');
      return false;
    }

    try {
      // Check if any chat panel selector is visible
      for (const selector of googleChatPanelSelectors) {
        try {
          const element = await this.page.locator(selector).first();
          if (await element.isVisible({ timeout: 1000 })) {
            return true;
          }
        } catch {
          // Continue to next selector
        }
      }

      // Also check if chat input is visible (more reliable indicator)
      for (const selector of googleChatInputSelectors) {
        try {
          const element = await this.page.locator(selector).first();
          if (await element.isVisible({ timeout: 1000 })) {
            return true;
          }
        } catch {
          // Continue to next selector
        }
      }

      return false;
    } catch (error: any) {
      log(`[Chat] Error checking if chat is open: ${error.message}`);
      return false;
    }
  }

  /**
   * Open the chat panel by clicking the chat button
   */
  async openChatPanel(): Promise<boolean> {
    if (!this.page) {
      log('[Chat] Page not available');
      return false;
    }

    // Check if already open
    if (await this.isChatOpen()) {
      log('[Chat] Chat panel is already open');
      return true;
    }

    try {
      log('[Chat] Attempting to open chat panel...');

      // Try each chat button selector until one works
      for (let i = 0; i < googleChatButtonSelectors.length; i++) {
        const selector = googleChatButtonSelectors[i];
        try {
          log(`[Chat] Trying chat button selector ${i + 1}/${googleChatButtonSelectors.length}: ${selector}`);
          
          const button = await this.page.locator(selector).first();
          await button.waitFor({ state: 'visible', timeout: 5000 });
          
          // Check if button is actually visible and clickable
          if (await button.isVisible()) {
            await button.click({ timeout: 2000 });
            log(`[Chat] Clicked chat button with selector: ${selector}`);
            
            // Wait a bit for chat panel to open
            await this.page.waitForTimeout(1000);
            
            // Verify chat opened
            if (await this.isChatOpen()) {
              log('[Chat] Chat panel opened successfully');
              return true;
            } else {
              log('[Chat] Chat button clicked but panel did not open');
            }
          }
        } catch (error: any) {
          log(`[Chat] Selector ${selector} failed: ${error.message}`);
          // Continue to next selector
        }
      }

      log('[Chat] Failed to open chat panel with all selectors');
      return false;
    } catch (error: any) {
      log(`[Chat] Error opening chat panel: ${error.message}`);
      return false;
    }
  }

  /**
   * Send a message to the Google Meet chat
   * @param message The message text to send
   */
  async sendChatMessage(message: string): Promise<boolean> {
    if (!this.page) {
      log('[Chat] Page not available');
      return false;
    }

    if (!message || message.trim().length === 0) {
      log('[Chat] Empty message, skipping');
      return false;
    }

    try {
      log(`[Chat] Attempting to send message: "${message}"`);

      // Ensure chat panel is open
      if (!(await this.isChatOpen())) {
        log('[Chat] Chat panel not open, opening it first...');
        const opened = await this.openChatPanel();
        if (!opened) {
          log('[Chat] Failed to open chat panel');
          return false;
        }
        // Wait a bit more for chat input to be ready
        await this.page.waitForTimeout(500);
      }

      // Find and fill chat input
      let inputFound = false;
      for (let i = 0; i < googleChatInputSelectors.length; i++) {
        const selector = googleChatInputSelectors[i];
        try {
          log(`[Chat] Trying chat input selector ${i + 1}/${googleChatInputSelectors.length}: ${selector}`);
          
          const input = await this.page.locator(selector).first();
          await input.waitFor({ state: 'visible', timeout: 5000 });
          
          if (await input.isVisible()) {
            // Clear any existing text
            await input.click();
            await this.page.waitForTimeout(200);
            
            // Handle contenteditable div vs textarea
            const tagName = await input.evaluate((el) => el.tagName.toLowerCase());
            if (tagName === 'div' || tagName === 'span') {
              // Contenteditable div - use innerHTML/textContent
              await input.fill('');
              await input.type(message, { delay: 50 });
            } else {
              // Regular textarea/input
              await input.fill(message);
            }
            
            log(`[Chat] Typed message into input: ${selector}`);
            inputFound = true;
            
            // Wait a bit for text to be entered
            await this.page.waitForTimeout(300);
            break;
          }
        } catch (error: any) {
          log(`[Chat] Input selector ${selector} failed: ${error.message}`);
          // Continue to next selector
        }
      }

      if (!inputFound) {
        log('[Chat] Failed to find chat input with all selectors');
        return false;
      }

      // Find and click send button
      let sendSuccess = false;
      for (let i = 0; i < googleChatSendButtonSelectors.length; i++) {
        const selector = googleChatSendButtonSelectors[i];
        try {
          log(`[Chat] Trying send button selector ${i + 1}/${googleChatSendButtonSelectors.length}: ${selector}`);
          
          const sendButton = await this.page.locator(selector).first();
          await sendButton.waitFor({ state: 'visible', timeout: 3000 });
          
          if (await sendButton.isVisible()) {
            await sendButton.click({ timeout: 2000 });
            log(`[Chat] Clicked send button: ${selector}`);
            sendSuccess = true;
            
            // Wait a bit to ensure message was sent
            await this.page.waitForTimeout(500);
            break;
          }
        } catch (error: any) {
          log(`[Chat] Send button selector ${selector} failed: ${error.message}`);
          // Continue to next selector
        }
      }

      // Alternative: Try pressing Enter if send button not found
      if (!sendSuccess) {
        log('[Chat] Send button not found, trying Enter key...');
        try {
          // Focus on input again and press Enter
          for (const selector of googleChatInputSelectors) {
            try {
              const input = await this.page.locator(selector).first();
              if (await input.isVisible()) {
                await input.press('Enter');
                log('[Chat] Pressed Enter to send message');
                sendSuccess = true;
                await this.page.waitForTimeout(500);
                break;
              }
            } catch {
              // Continue
            }
          }
        } catch (error: any) {
          log(`[Chat] Error pressing Enter: ${error.message}`);
        }
      }

      if (sendSuccess) {
        log(`[Chat] Message sent successfully: "${message}"`);
        return true;
      } else {
        log('[Chat] Failed to send message - no send button or Enter key worked');
        return false;
      }
    } catch (error: any) {
      log(`[Chat] Error sending chat message: ${error.message}`);
      return false;
    }
  }
}

/**
 * Convenience function to send a chat message
 * @param page Playwright page instance
 * @param message Message text to send
 */
export async function sendChatMessage(page: Page, message: string): Promise<boolean> {
  const chatService = new GoogleMeetChatService(page);
  return await chatService.sendChatMessage(message);
}

/**
 * Convenience function to open chat panel
 * @param page Playwright page instance
 */
export async function openChatPanel(page: Page): Promise<boolean> {
  const chatService = new GoogleMeetChatService(page);
  return await chatService.openChatPanel();
}

