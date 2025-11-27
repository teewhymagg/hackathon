"""
Jira Task Creation Web UI

A Streamlit web interface for creating Jira tasks, epics, and subtasks.
"""
import os
import requests
from typing import List, Dict, Any

import streamlit as st

# Configuration
JIRA_SERVICE_URL = os.environ.get("JIRA_SERVICE_URL", "http://jira-integration:8003")
JIRA_SERVICE_URL_EXTERNAL = os.environ.get("JIRA_SERVICE_URL_EXTERNAL", "http://localhost:18003")

# Try to detect if we're running in Docker (internal network) or standalone
# First try internal URL, fallback to external
try:
    test_response = requests.get(f"{JIRA_SERVICE_URL}/health", timeout=2)
    if test_response.status_code == 200:
        default_url = JIRA_SERVICE_URL
    else:
        default_url = JIRA_SERVICE_URL_EXTERNAL
except:
    default_url = JIRA_SERVICE_URL_EXTERNAL

st.set_page_config(
    page_title="Jira Task Creator",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎯 Jira Task Creator")
st.markdown("Create Jira tasks, epics, and subtasks from your meeting notes or task descriptions")

# Sidebar configuration
st.sidebar.header("⚙️ Configuration")

# Health check
st.sidebar.subheader("Service Status")
try:
    health_url = default_url if "jira_service_url" not in st.session_state else st.session_state.jira_service_url
    health_response = requests.get(f"{health_url}/health", timeout=3)
    if health_response.status_code == 200:
        health_data = health_response.json()
        st.sidebar.success("✅ Jira Service Connected")
        if health_data.get("jira_configured"):
            st.sidebar.success("✅ Jira Configured")
        else:
            st.sidebar.warning("⚠️ Jira Not Configured")
        if health_data.get("openai_configured"):
            st.sidebar.success("✅ OpenAI Configured")
        else:
            st.sidebar.warning("⚠️ OpenAI Not Configured")
    else:
        st.sidebar.error("❌ Service Error")
except Exception as e:
    st.sidebar.error(f"❌ Cannot Connect")
    st.sidebar.caption(f"Error: {str(e)[:50]}")

jira_service_url = st.sidebar.text_input(
    "Jira Service URL",
    value=default_url,
    help="URL of the Jira integration service. Use 'http://jira-integration:8003' for Docker internal, 'http://localhost:18003' for external.",
    key="jira_service_url"
)

st.sidebar.caption("💡 **Tip:** If connection fails, try:")
st.sidebar.caption("• Docker: `http://jira-integration:8003`")
st.sidebar.caption("• Local: `http://localhost:18003`")

# Main interface
tab1, tab2, tab3 = st.tabs(["📝 Manual Task Entry", "🤖 AI-Powered (Meeting)", "📋 Bulk Import"])

# Tab 1: Manual Task Entry
with tab1:
    st.header("Create Tasks Manually")
    st.markdown("Enter tasks directly and create them in Jira")
    
    create_epics = st.checkbox("Create Epics for major initiatives", value=True)
    create_subtasks = st.checkbox("Create Subtasks", value=True)
    
    st.subheader("Epics & Tasks")
    
    num_epics = st.number_input("Number of Epics", min_value=0, max_value=10, value=1, step=1)
    
    epics_data = []
    for i in range(num_epics):
        with st.expander(f"Epic {i+1}", expanded=True):
            epic_name = st.text_input(f"Epic Name (short)", key=f"epic_name_{i}", placeholder="e.g., Auth System")
            epic_summary = st.text_input(f"Epic Summary", key=f"epic_summary_{i}", placeholder="Full epic title")
            epic_description = st.text_area(f"Epic Description", key=f"epic_desc_{i}", placeholder="Describe the epic...")
            epic_priority = st.selectbox(f"Priority", ["высокий", "средний", "низкий"], index=1, key=f"epic_priority_{i}")
            
            st.markdown("**Tasks under this Epic:**")
            num_tasks = st.number_input(f"Number of Tasks", min_value=0, max_value=20, value=1, step=1, key=f"num_tasks_{i}")
            
            tasks_data = []
            for j in range(num_tasks):
                with st.container():
                    task_summary = st.text_input(f"Task {j+1} Summary", key=f"task_summary_{i}_{j}", placeholder="Task title")
                    task_description = st.text_area(f"Task {j+1} Description", key=f"task_desc_{i}_{j}", placeholder="Task description...")
                    task_priority = st.selectbox(f"Priority", ["высокий", "средний", "низкий"], index=1, key=f"task_priority_{i}_{j}")
                    task_assignee = st.text_input(f"Assignee (email/name)", key=f"task_assignee_{i}_{j}", placeholder="Optional")
                    task_due_date = st.text_input(f"Due Date (YYYY-MM-DD)", key=f"task_due_{i}_{j}", placeholder="Optional: 2024-12-31")
                    
                    if create_subtasks:
                        num_subtasks = st.number_input(f"Number of Subtasks", min_value=0, max_value=10, value=0, step=1, key=f"num_subtasks_{i}_{j}")
                        subtasks_data = []
                        for k in range(num_subtasks):
                            subtask_title = st.text_input(f"Subtask {k+1} Title", key=f"subtask_title_{i}_{j}_{k}", placeholder="Subtask title")
                            subtask_desc = st.text_area(f"Subtask {k+1} Description", key=f"subtask_desc_{i}_{j}_{k}", placeholder="Subtask description...")
                            subtask_assignee = st.text_input(f"Assignee", key=f"subtask_assignee_{i}_{j}_{k}", placeholder="Optional")
                            subtask_due = st.text_input(f"Due Date", key=f"subtask_due_{i}_{j}_{k}", placeholder="Optional")
                            
                            if subtask_title:
                                subtasks_data.append({
                                    "title": subtask_title,
                                    "description": subtask_desc,
                                    "assignee": subtask_assignee if subtask_assignee else None,
                                    "due_date": subtask_due if subtask_due else None,
                                })
                        
                        if subtasks_data:
                            task_data = {
                                "summary": task_summary,
                                "description": task_description,
                                "priority": task_priority,
                                "assignee": task_assignee if task_assignee else None,
                                "due_date": task_due_date if task_due_date else None,
                                "subtasks": subtasks_data
                            }
                        else:
                            task_data = {
                                "summary": task_summary,
                                "description": task_description,
                                "priority": task_priority,
                                "assignee": task_assignee if task_assignee else None,
                                "due_date": task_due_date if task_due_date else None,
                                "subtasks": []
                            }
                    else:
                        task_data = {
                            "summary": task_summary,
                            "description": task_description,
                            "priority": task_priority,
                            "assignee": task_assignee if task_assignee else None,
                            "due_date": task_due_date if task_due_date else None,
                        }
                    
                    if task_summary:
                        tasks_data.append(task_data)
            
            if epic_name and epic_summary:
                epics_data.append({
                    "name": epic_name,
                    "summary": epic_summary,
                    "description": epic_description,
                    "priority": epic_priority,
                    "tasks": tasks_data
                })
    
    st.subheader("Standalone Tasks")
    num_standalone = st.number_input("Number of Standalone Tasks", min_value=0, max_value=20, value=0, step=1)
    
    standalone_tasks = []
    for i in range(num_standalone):
        task_summary = st.text_input(f"Task {i+1} Summary", key=f"standalone_summary_{i}", placeholder="Task title")
        task_description = st.text_area(f"Task {i+1} Description", key=f"standalone_desc_{i}", placeholder="Task description...")
        task_priority = st.selectbox(f"Priority", ["высокий", "средний", "низкий"], index=1, key=f"standalone_priority_{i}")
        task_assignee = st.text_input(f"Assignee", key=f"standalone_assignee_{i}", placeholder="Optional")
        task_due_date = st.text_input(f"Due Date", key=f"standalone_due_{i}", placeholder="Optional: 2024-12-31")
        
        if task_summary:
            standalone_tasks.append({
                "summary": task_summary,
                "description": task_description,
                "priority": task_priority,
                "assignee": task_assignee if task_assignee else None,
                "due_date": task_due_date if task_due_date else None,
            })
    
    st.subheader("Action Items")
    num_actions = st.number_input("Number of Action Items", min_value=0, max_value=20, value=0, step=1)
    
    action_items = []
    for i in range(num_actions):
        action_desc = st.text_input(f"Action {i+1}", key=f"action_desc_{i}", placeholder="Action description")
        action_owner = st.text_input(f"Owner", key=f"action_owner_{i}", placeholder="Optional")
        action_priority = st.selectbox(f"Priority", ["высокий", "средний", "низкий"], index=1, key=f"action_priority_{i}")
        action_due = st.text_input(f"Due Date", key=f"action_due_{i}", placeholder="Optional")
        
        if action_desc:
            action_items.append({
                "description": action_desc,
                "owner": action_owner if action_owner else None,
                "priority": action_priority,
                "due_date": action_due if action_due else None,
            })
    
    if st.button("🚀 Create Tasks in Jira", type="primary", use_container_width=True):
        if not epics_data and not standalone_tasks and not action_items:
            st.error("Please add at least one task, epic, or action item!")
        else:
            with st.spinner("Creating tasks in Jira..."):
                try:
                    payload = {
                        "llm_response": {
                            "epics": epics_data if create_epics else [],
                            "standalone_tasks": standalone_tasks,
                            "action_items": action_items,
                            "task_breakdown": [] if create_epics else epics_data  # Backward compatibility
                        },
                        "create_subtasks": create_subtasks
                    }
                    
                    response = requests.post(
                        f"{jira_service_url}/jira/create-tasks",
                        json=payload,
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"✅ Successfully created {len(result.get('created_tasks', []))} issues in Jira!")
                        
                        # Display created tasks
                        st.subheader("Created Issues")
                        for task in result.get("created_tasks", []):
                            with st.expander(f"{task.get('issue_type')}: {task.get('issue_key')}"):
                                st.markdown(f"**URL:** [{task.get('issue_url')}]({task.get('issue_url')})")
                                if task.get("parent_key"):
                                    st.markdown(f"**Parent:** {task.get('parent_key')}")
                                if task.get("child_keys"):
                                    st.markdown(f"**Children:** {', '.join(task.get('child_keys', []))}")
                        
                        if result.get("errors"):
                            st.warning("Some errors occurred:")
                            for error in result["errors"]:
                                st.error(error)
                    else:
                        st.error(f"Failed to create tasks: {response.text}")
                        
                except requests.exceptions.ConnectionError as e:
                    st.error(f"❌ Cannot connect to Jira service at {jira_service_url}")
                    st.warning("**Troubleshooting:**")
                    st.markdown("""
                    1. **Check if the service is running:**
                       ```bash
                       docker compose ps jira-integration
                       ```
                    
                    2. **If using Docker, try the internal URL:**
                       - Change URL in sidebar to: `http://jira-integration:8003`
                    
                    3. **If running locally, try:**
                       - Change URL in sidebar to: `http://localhost:18003`
                    
                    4. **Check service logs:**
                       ```bash
                       docker compose logs jira-integration
                       ```
                    """)
                except requests.exceptions.RequestException as e:
                    st.error(f"Error connecting to Jira service: {str(e)}")
                    st.info(f"Make sure the Jira service is running at: {jira_service_url}")

# Tab 2: AI-Powered (Meeting)
with tab2:
    st.header("AI-Powered Task Creation")
    st.markdown("Enter meeting transcript or summary, and let AI generate structured Jira tasks")
    
    meeting_summary = st.text_area(
        "Meeting Summary",
        placeholder="Brief summary of the meeting...",
        height=100
    )
    
    meeting_transcript = st.text_area(
        "Meeting Transcript (Optional)",
        placeholder="Full transcript of the meeting...",
        height=300,
        help="If provided, AI will analyze the full transcript. Otherwise, only the summary will be used."
    )
    
    ai_options_col1, ai_options_col2 = st.columns(2)
    with ai_options_col1:
        ai_create_epics = st.checkbox("Create Epics", value=True, key="ai_epics")
    with ai_options_col2:
        ai_create_subtasks = st.checkbox("Create Subtasks", value=True, key="ai_subtasks")
    
    if st.button("🤖 Generate & Create Tasks with AI", type="primary", use_container_width=True):
        if not meeting_summary and not meeting_transcript:
            st.error("Please provide at least a meeting summary or transcript!")
        else:
            with st.spinner("🤖 AI is analyzing the meeting and generating tasks..."):
                try:
                    payload = {
                        "meeting_summary": meeting_summary if meeting_summary else None,
                        "meeting_transcript": meeting_transcript if meeting_transcript else None,
                        "create_epics": ai_create_epics,
                        "create_subtasks": ai_create_subtasks,
                        "meeting_metadata": {}
                    }
                    
                    response = requests.post(
                        f"{jira_service_url}/jira/process-meeting",
                        json=payload,
                        timeout=120  # Longer timeout for AI processing
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"✅ Successfully created {len(result.get('created_tasks', []))} issues in Jira!")
                        
                        # Show LLM response preview
                        if result.get("llm_response"):
                            with st.expander("📋 AI-Generated Structure (Preview)", expanded=False):
                                st.json(result["llm_response"])
                        
                        # Display created tasks
                        st.subheader("Created Issues")
                        for task in result.get("created_tasks", []):
                            with st.expander(f"{task.get('issue_type')}: {task.get('issue_key')}"):
                                st.markdown(f"**URL:** [{task.get('issue_url')}]({task.get('issue_url')})")
                                if task.get("parent_key"):
                                    st.markdown(f"**Parent:** {task.get('parent_key')}")
                                if task.get("child_keys"):
                                    st.markdown(f"**Children:** {', '.join(task.get('child_keys', []))}")
                        
                        if result.get("errors"):
                            st.warning("Some errors occurred:")
                            for error in result["errors"]:
                                st.error(error)
                    else:
                        error_detail = response.text
                        st.error(f"Failed to create tasks: {error_detail}")
                        if "OPENAI_API_KEY" in error_detail:
                            st.info("💡 Make sure OPENAI_API_KEY is configured in the Jira service.")
                        
                except requests.exceptions.ConnectionError as e:
                    st.error(f"❌ Cannot connect to Jira service at {jira_service_url}")
                    st.warning("**Troubleshooting:**")
                    st.markdown("""
                    1. **Check if the service is running:**
                       ```bash
                       docker compose ps jira-integration
                       ```
                    
                    2. **If using Docker, try the internal URL:**
                       - Change URL in sidebar to: `http://jira-integration:8003`
                    
                    3. **If running locally, try:**
                       - Change URL in sidebar to: `http://localhost:18003`
                    
                    4. **Check service logs:**
                       ```bash
                       docker compose logs jira-integration
                       ```
                    """)
                except requests.exceptions.RequestException as e:
                    st.error(f"Error connecting to Jira service: {str(e)}")
                    st.info(f"Make sure the Jira service is running at: {jira_service_url}")

# Tab 3: Bulk Import
with tab3:
    st.header("Bulk Import Tasks")
    st.markdown("Import tasks from JSON or paste structured data")
    
    import_format = st.radio(
        "Import Format",
        ["JSON", "Plain Text (one task per line)"],
        horizontal=True
    )
    
    if import_format == "JSON":
        json_input = st.text_area(
            "JSON Data",
            placeholder='{"epics": [...], "standalone_tasks": [...], "action_items": [...]}',
            height=400
        )
        
        if st.button("📥 Import & Create Tasks", type="primary"):
            if not json_input:
                st.error("Please provide JSON data!")
            else:
                try:
                    import json
                    data = json.loads(json_input)
                    
                    with st.spinner("Creating tasks in Jira..."):
                        payload = {
                            "llm_response": data,
                            "create_subtasks": True
                        }
                        
                        response = requests.post(
                            f"{jira_service_url}/jira/create-tasks",
                            json=payload,
                            timeout=60
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            st.success(f"✅ Successfully created {len(result.get('created_tasks', []))} issues!")
                            
                            for task in result.get("created_tasks", []):
                                st.markdown(f"- [{task.get('issue_key')}]({task.get('issue_url')})")
                        else:
                            st.error(f"Failed: {response.text}")
                            
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {str(e)}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    else:  # Plain Text
        text_input = st.text_area(
            "Task List (one per line)",
            placeholder="Task 1 description\nTask 2 description\nTask 3 description",
            height=300
        )
        
        bulk_priority = st.selectbox("Default Priority", ["высокий", "средний", "низкий"], index=1)
        
        if st.button("📥 Import & Create Tasks", type="primary"):
            if not text_input:
                st.error("Please provide task descriptions!")
            else:
                tasks = [line.strip() for line in text_input.split("\n") if line.strip()]
                
                if tasks:
                    with st.spinner(f"Creating {len(tasks)} tasks in Jira..."):
                        try:
                            standalone_tasks = [
                                {
                                    "summary": task,
                                    "description": task,
                                    "priority": bulk_priority
                                }
                                for task in tasks
                            ]
                            
                            payload = {
                                "llm_response": {
                                    "standalone_tasks": standalone_tasks,
                                    "epics": [],
                                    "action_items": []
                                },
                                "create_subtasks": False
                            }
                            
                            response = requests.post(
                                f"{jira_service_url}/jira/create-tasks",
                                json=payload,
                                timeout=60
                            )
                            
                            if response.status_code == 200:
                                result = response.json()
                                st.success(f"✅ Successfully created {len(result.get('created_tasks', []))} tasks!")
                                
                                for task in result.get("created_tasks", []):
                                    st.markdown(f"- [{task.get('issue_key')}]({task.get('issue_url')})")
                            else:
                                st.error(f"Failed: {response.text}")
                                
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #666;'>
    <small>Jira Task Creator • Powered by Jira Integration Service</small>
</div>
""", unsafe_allow_html=True)

