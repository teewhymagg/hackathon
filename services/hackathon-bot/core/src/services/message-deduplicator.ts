/**
 * Message Deduplicator Service
 * Prevents sending duplicate messages within a time window
 */

export class MessageDeduplicator {
  private recentMessages: Map<string, number> = new Map();
  private deduplicationWindowMs: number;

  constructor(deduplicationWindowSeconds: number = 300) {
    // Default: 5 minutes (300 seconds)
    this.deduplicationWindowMs = deduplicationWindowSeconds * 1000;
  }

  /**
   * Check if a message should be sent (not a duplicate)
   */
  shouldSend(message: string): boolean {
    const normalized = this.normalizeMessage(message);
    const lastSent = this.recentMessages.get(normalized);
    const now = Date.now();

    if (lastSent && now - lastSent < this.deduplicationWindowMs) {
      return false; // Too recent, don't send
    }

    // Update timestamp and allow sending
    this.recentMessages.set(normalized, now);
    return true;
  }

  /**
   * Normalize message for comparison
   */
  private normalizeMessage(message: string): string {
    return message
      .toLowerCase()
      .trim()
      .replace(/\s+/g, ' ') // Normalize whitespace
      .replace(/[^\w\s]/g, ''); // Remove punctuation for better matching
  }

  /**
   * Clear old entries (older than deduplication window)
   */
  cleanup(): void {
    const now = Date.now();
    for (const [key, timestamp] of this.recentMessages.entries()) {
      if (now - timestamp >= this.deduplicationWindowMs) {
        this.recentMessages.delete(key);
      }
    }
  }

  /**
   * Clear all entries
   */
  clear(): void {
    this.recentMessages.clear();
  }
}

