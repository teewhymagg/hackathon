/**
 * Transcription Buffer Service
 * Stores transcriptions with timestamps and provides methods to retrieve recent transcriptions
 */

export interface TranscriptionEntry {
  text: string;
  timestamp: number;
}

export class TranscriptionBuffer {
  private transcriptions: TranscriptionEntry[] = [];
  private maxEntries: number = 1000; // Prevent unbounded growth

  /**
   * Add a transcription to the buffer
   */
  addTranscription(text: string, timestamp?: number): void {
    if (!text || text.trim().length === 0) {
      return;
    }

    const entry: TranscriptionEntry = {
      text: text.trim(),
      timestamp: timestamp || Date.now(),
    };

    this.transcriptions.push(entry);

    // Keep only the most recent entries
    if (this.transcriptions.length > this.maxEntries) {
      this.transcriptions = this.transcriptions.slice(-this.maxEntries);
    }
  }

  /**
   * Get transcriptions from the last N seconds
   */
  getRecentTranscriptions(windowSeconds: number): TranscriptionEntry[] {
    const now = Date.now();
    const cutoffTime = now - windowSeconds * 1000;

    return this.transcriptions.filter((entry) => entry.timestamp >= cutoffTime);
  }

  /**
   * Get all transcriptions as a single text string
   */
  getRecentTranscriptionsAsText(windowSeconds: number): string {
    const recent = this.getRecentTranscriptions(windowSeconds);
    return recent.map((entry) => entry.text).join(' ');
  }

  /**
   * Get all transcriptions
   */
  getAllTranscriptions(): TranscriptionEntry[] {
    return [...this.transcriptions];
  }

  /**
   * Clear all transcriptions
   */
  clear(): void {
    this.transcriptions = [];
  }

  /**
   * Get count of transcriptions
   */
  getCount(): number {
    return this.transcriptions.length;
  }
}

