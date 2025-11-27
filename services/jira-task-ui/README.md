# Jira Task Creator Web UI

A user-friendly web interface for creating Jira tasks, epics, and subtasks. This Streamlit application provides three ways to create tasks in Jira.

## Features

- **Manual Task Entry**: Create tasks, epics, and subtasks with a form-based interface
- **AI-Powered Creation**: Enter meeting transcripts/summaries and let AI generate structured tasks
- **Bulk Import**: Import tasks from JSON or plain text

## Access

Once the service is running, access the web interface at:
- **Local**: http://localhost:18004
- **Docker**: http://localhost:18004 (or configured port)

## Usage

### Tab 1: Manual Task Entry

1. Configure options:
   - Enable/disable Epic creation
   - Enable/disable Subtask creation

2. Create Epics:
   - Enter Epic name, summary, description
   - Set priority
   - Add tasks under each epic
   - Add subtasks under each task (if enabled)

3. Add Standalone Tasks:
   - Tasks not linked to any epic
   - Set priority, assignee, due date

4. Add Action Items:
   - Quick action items
   - Set owner and priority

5. Click "🚀 Create Tasks in Jira"

### Tab 2: AI-Powered (Meeting)

1. Enter meeting summary (required)
2. Optionally enter full meeting transcript
3. Configure options:
   - Create Epics
   - Create Subtasks
4. Click "🤖 Generate & Create Tasks with AI"

The AI will:
- Analyze the meeting content
- Generate structured tasks, epics, and subtasks
- Create them automatically in Jira

### Tab 3: Bulk Import

**JSON Format:**
```json
{
  "epics": [
    {
      "name": "Epic Name",
      "summary": "Epic Summary",
      "description": "Description",
      "priority": "высокий",
      "tasks": [...]
    }
  ],
  "standalone_tasks": [...],
  "action_items": [...]
}
```

**Plain Text Format:**
- One task per line
- Each line becomes a standalone task
- Set default priority for all tasks

## Configuration

The UI connects to the Jira integration service. Configure the service URL in the sidebar if needed.

## Requirements

- Jira integration service must be running
- Jira credentials must be configured
- For AI-powered features: OpenAI API key must be configured

## Example Workflow

1. **From Meeting:**
   - Go to "AI-Powered (Meeting)" tab
   - Paste meeting summary or transcript
   - Click "Generate & Create Tasks with AI"
   - Review created tasks and links

2. **Manual Entry:**
   - Go to "Manual Task Entry" tab
   - Create an Epic with name "User Authentication"
   - Add tasks: "Set up OAuth2", "Implement login flow"
   - Add subtasks under each task
   - Click "Create Tasks in Jira"

3. **Bulk Import:**
   - Go to "Bulk Import" tab
   - Paste list of tasks (one per line)
   - Set priority
   - Click "Import & Create Tasks"

## Troubleshooting

- **"Error connecting to Jira service"**: Make sure the Jira integration service is running
- **"OPENAI_API_KEY not configured"**: Set the API key in the Jira service environment
- **Tasks not created**: Check Jira service logs for detailed error messages

