/**
 * LLM Analyzer Service
 * Analyzes transcriptions using OpenAI API to detect meeting issues
 */

import { log } from '../utils';
import { TranscriptionEntry } from './transcription-buffer';

export interface AnalysisIssue {
  type: 'missing_assignment' | 'missing_deadline' | 'other';
  description: string;
  suggested_message: string;
  confidence?: number;
}

export interface AnalysisResult {
  issues: AnalysisIssue[];
  hasIssues: boolean;
}

export interface LLMAnalyzerConfig {
  apiKey: string;
  model?: string;
  analysisIntervalSeconds?: number;
}

export class LLMAnalyzer {
  private config: Required<LLMAnalyzerConfig>;
  private apiKey: string;

  constructor(config: LLMAnalyzerConfig) {
    if (!config.apiKey) {
      throw new Error('OpenAI API key is required');
    }

    this.apiKey = config.apiKey;
    this.config = {
      apiKey: config.apiKey,
      model: config.model || 'gpt-4o-mini',
      analysisIntervalSeconds: config.analysisIntervalSeconds || 10,
    };
  }

  /**
   * Analyze transcriptions and detect issues
   */
  async analyze(transcriptions: TranscriptionEntry[]): Promise<AnalysisResult> {
    if (!transcriptions || transcriptions.length === 0) {
      return { issues: [], hasIssues: false };
    }

    // Combine transcriptions into a single text
    const transcriptText = transcriptions
      .map((entry) => entry.text)
      .join(' ')
      .trim();

    if (!transcriptText || transcriptText.length < 10) {
      // Too short to analyze meaningfully
      return { issues: [], hasIssues: false };
    }

    try {
      log(`[LLM Analyzer] Analyzing ${transcriptions.length} transcriptions (${transcriptText.length} chars)`);

      const prompt = this.buildPrompt(transcriptText);
      const response = await this.callOpenAI(prompt);

      if (!response || !response.choices || response.choices.length === 0) {
        log('[LLM Analyzer] No response from OpenAI');
        return { issues: [], hasIssues: false };
      }

      const content = response.choices[0].message?.content;
      const finishReason = response.choices[0].finish_reason;
      
      if (!content) {
        if (finishReason === 'length') {
          log(`[LLM Analyzer] ERROR: Model hit token limit (finish_reason: length). Consider using a non-reasoning model (gpt-4o-mini) or increasing max_completion_tokens.`);
          log(`[LLM Analyzer] Current model: ${this.config.model}, completion_tokens: ${response.usage?.completion_tokens}, reasoning_tokens: ${response.usage?.completion_tokens_details?.reasoning_tokens || 'N/A'}`);
        } else {
          log(`[LLM Analyzer] Empty content in OpenAI response. Finish reason: ${finishReason}. Full response: ${JSON.stringify(response, null, 2)}`);
        }
        return { issues: [], hasIssues: false };
      }
      
      log(`[LLM Analyzer] Received response content (${content.length} chars): ${content.substring(0, 200)}...`);

      // Parse JSON response
      let analysisResult: AnalysisResult;
      try {
        const parsed = JSON.parse(content);
        analysisResult = {
          issues: parsed.issues || [],
          hasIssues: (parsed.issues || []).length > 0,
        };
      } catch (parseError) {
        log(`[LLM Analyzer] Failed to parse JSON response: ${parseError}`);
        // Try to extract JSON from markdown code blocks
        const jsonMatch = content.match(/```(?:json)?\s*(\{[\s\S]*\})\s*```/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[1]);
          analysisResult = {
            issues: parsed.issues || [],
            hasIssues: (parsed.issues || []).length > 0,
          };
        } else {
          return { issues: [], hasIssues: false };
        }
      }

      log(`[LLM Analyzer] Found ${analysisResult.issues.length} issues`);
      return analysisResult;
    } catch (error: any) {
      log(`[LLM Analyzer] Error analyzing transcriptions: ${error.message}`);
      return { issues: [], hasIssues: false };
    }
  }

  /**
   * Build the prompt for OpenAI
   */
  private buildPrompt(transcriptText: string): string {
    return `Analyze the following meeting transcript and identify any issues related to task management and action items.

Transcript:
${transcriptText}

Check for the following issues:
1. Tasks mentioned but not assigned to someone (e.g., "we need to do X" or "нужно сделать X" without "assigned to John" or "Иван сделает")
2. Tasks mentioned but without a deadline (e.g., "we need to do X" or "нужно сделать X" without "by Friday" or "к пятнице" or "на следующей неделе")
3. Action items without clear owners or deadlines

You MUST respond with a valid JSON object. Do not include any text outside the JSON. Use this exact format:
{
  "issues": [
    {
      "type": "missing_assignment" | "missing_deadline" | "other",
      "description": "Brief description of the issue",
      "suggested_message": "A concise, helpful message to send to the meeting chat (max 100 characters, in Russian if transcript is in Russian)"
    }
  ]
}

If no issues are found, you MUST still return: {"issues": []}

Important:
- Always return valid JSON, even if there are no issues
- Only report issues that are clear and actionable
- Keep suggested messages short, professional, and helpful
- Don't repeat the same issue multiple times
- Focus on the most recent and relevant issues
- Use Russian for suggested messages if the transcript is in Russian`;
  }

  /**
   * Call OpenAI API
   */
  private async callOpenAI(prompt: string): Promise<any> {
    const url = 'https://api.openai.com/v1/chat/completions';

    // Build request body based on model capabilities
    const isNewModel = this.config.model.includes('gpt-5') || this.config.model.includes('o1');
    const requestBody: any = {
      model: this.config.model,
      messages: [
        {
          role: 'system',
          content:
            'You are a helpful meeting assistant that analyzes transcripts to identify missing task assignments and deadlines. Respond only with valid JSON.',
        },
        {
          role: 'user',
          content: prompt,
        },
      ],
    };
    
    // Newer models (gpt-5-nano, o1) don't support custom temperature - only default (1)
    if (!isNewModel) {
      requestBody.temperature = 0.3; // Lower temperature for more consistent, factual responses
    }
    
    // Use max_completion_tokens for newer models, max_tokens for older models
    // Reasoning models (gpt-5-nano, o1) need significantly more tokens because they use reasoning tokens
    // They typically use ~500-1000 tokens for reasoning, then need tokens for the actual output
    if (isNewModel) {
      // Reasoning models need much more tokens: reasoning tokens + output tokens
      // Increased to 8000 to allow extensive reasoning (~4000-5000 tokens) and sufficient output tokens (~3000-4000)
      requestBody.max_completion_tokens = 8000;
    } else {
      requestBody.max_tokens = 500;
    }
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`OpenAI API error: ${response.status} ${errorText}`);
    }

    return await response.json();
  }

  /**
   * Get configuration
   */
  getConfig(): Required<LLMAnalyzerConfig> {
    return { ...this.config };
  }
}

