from typing import List, Dict, Optional
from datetime import datetime


def format_date(dt: datetime) -> str:
    """Format datetime for display."""
    if not dt:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M")


def format_date_short(dt: datetime) -> str:
    """Format datetime as short date."""
    if not dt:
        return "N/A"
    return dt.strftime("%Y-%m-%d")


def days_until(dt: datetime) -> int:
    """Calculate days until deadline."""
    if not dt:
        return None
    delta = dt - datetime.now(dt.tzinfo)
    return delta.days


def format_email_html(
    user_name: Optional[str],
    upcoming_deadlines: List[Dict],
    last_meeting_summary: Optional[Dict],
) -> str:
    """Format email as HTML."""
    name = user_name or "there"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #4A90E2;
                color: white;
                padding: 20px;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 20px;
                border-radius: 0 0 5px 5px;
            }}
            .section {{
                margin-bottom: 30px;
            }}
            .section-title {{
                color: #4A90E2;
                font-size: 20px;
                font-weight: bold;
                margin-bottom: 15px;
                border-bottom: 2px solid #4A90E2;
                padding-bottom: 5px;
            }}
            .deadline-item {{
                background-color: white;
                padding: 15px;
                margin-bottom: 10px;
                border-left: 4px solid #4A90E2;
                border-radius: 4px;
            }}
            .deadline-item.urgent {{
                border-left-color: #E74C3C;
            }}
            .deadline-item.warning {{
                border-left-color: #F39C12;
            }}
            .deadline-description {{
                font-weight: bold;
                margin-bottom: 5px;
            }}
            .deadline-meta {{
                color: #666;
                font-size: 14px;
            }}
            .meeting-summary {{
                background-color: white;
                padding: 15px;
                border-radius: 4px;
            }}
            .meeting-meta {{
                color: #666;
                font-size: 14px;
                margin-bottom: 10px;
            }}
            .summary-text {{
                white-space: pre-wrap;
            }}
            .no-data {{
                color: #999;
                font-style: italic;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                color: #666;
                font-size: 12px;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📅 Daily Reminder</h1>
            <p>Hello {name}!</p>
        </div>
        <div class="content">
    """
    
    # Upcoming Deadlines Section
    html += '<div class="section">'
    html += '<div class="section-title">⏰ Upcoming Deadlines</div>'
    
    if upcoming_deadlines:
        for deadline in upcoming_deadlines:
            days = days_until(deadline['due_date'])
            urgency_class = ""
            if days is not None:
                if days <= 1:
                    urgency_class = "urgent"
                elif days <= 3:
                    urgency_class = "warning"
            
            html += f'<div class="deadline-item {urgency_class}">'
            html += f'<div class="deadline-description">{deadline["description"]}</div>'
            html += '<div class="deadline-meta">'
            
            if deadline.get('owner'):
                html += f'👤 Owner: {deadline["owner"]}<br>'
            if deadline.get('priority'):
                html += f'⚡ Priority: {deadline["priority"]}<br>'
            
            html += f'📅 Due: {format_date(deadline["due_date"])}'
            if days is not None:
                if days == 0:
                    html += ' <strong>(Today!)</strong>'
                elif days == 1:
                    html += ' <strong>(Tomorrow!)</strong>'
                else:
                    html += f' ({days} days)'
            
            html += '<br>'
            html += f'📋 Meeting: {deadline["meeting_platform"]} meeting on {format_date_short(deadline["meeting_start_time"])}'
            html += '</div></div>'
    else:
        html += '<div class="no-data">No upcoming deadlines in the next 7 days. Great job! 🎉</div>'
    
    html += '</div>'
    
    # Last Meeting Summary Section
    html += '<div class="section">'
    html += '<div class="section-title">📝 Last Meeting Summary</div>'
    
    if last_meeting_summary:
        html += '<div class="meeting-summary">'
        html += '<div class="meeting-meta">'
        html += f'📅 Date: {format_date(last_meeting_summary["end_time"])}<br>'
        html += f'🌐 Platform: {last_meeting_summary["platform"]}<br>'
        if last_meeting_summary.get('platform_specific_id'):
            html += f'🔗 Meeting ID: {last_meeting_summary["platform_specific_id"]}<br>'
        if last_meeting_summary.get('goal'):
            html += f'🎯 Goal: {last_meeting_summary["goal"]}<br>'
        if last_meeting_summary.get('sentiment'):
            html += f'😊 Sentiment: {last_meeting_summary["sentiment"]}<br>'
        if last_meeting_summary.get('transcript_count'):
            html += f'💬 Transcript segments: {last_meeting_summary["transcript_count"]}<br>'
        html += '</div>'
        
        # Summary
        html += '<div class="summary-text">'
        html += '<strong>Summary:</strong><br>'
        html += f'{last_meeting_summary["summary"]}'
        html += '</div>'
        
        # Blockers
        if last_meeting_summary.get('blockers') and len(last_meeting_summary['blockers']) > 0:
            html += '<div style="margin-top: 15px; padding: 10px; background-color: #fff3cd; border-left: 4px solid #ffc107; border-radius: 4px;">'
            html += '<strong>🚧 Blockers:</strong><ul style="margin: 5px 0; padding-left: 20px;">'
            for blocker in last_meeting_summary['blockers']:
                blocker_text = blocker if isinstance(blocker, str) else blocker.get('description', str(blocker))
                html += f'<li>{blocker_text}</li>'
            html += '</ul></div>'
        
        # Deadlines from meeting metadata
        if last_meeting_summary.get('deadlines') and len(last_meeting_summary['deadlines']) > 0:
            html += '<div style="margin-top: 15px; padding: 10px; background-color: #d1ecf1; border-left: 4px solid #17a2b8; border-radius: 4px;">'
            html += '<strong>📅 Deadlines Mentioned:</strong><ul style="margin: 5px 0; padding-left: 20px;">'
            for deadline in last_meeting_summary['deadlines']:
                deadline_text = deadline if isinstance(deadline, str) else deadline.get('description', str(deadline))
                html += f'<li>{deadline_text}</li>'
            html += '</ul></div>'
        
        # Key Highlights
        if last_meeting_summary.get('highlights') and len(last_meeting_summary['highlights']) > 0:
            html += '<div style="margin-top: 15px;">'
            html += '<strong>💡 Key Highlights:</strong>'
            html += '<div style="margin-top: 10px;">'
            for highlight in last_meeting_summary['highlights'][:5]:  # Top 5 highlights
                label_emoji = {
                    'обновление': '📊',
                    'решение': '✅',
                    'блокер': '🚧',
                    'другое': '💬',
                }.get(highlight.get('label', '').lower(), '💬')
                
                html += '<div style="margin-bottom: 10px; padding: 8px; background-color: #f8f9fa; border-radius: 4px;">'
                if highlight.get('speaker'):
                    html += f'<strong>{label_emoji} {highlight["speaker"]}:</strong> '
                html += f'{highlight.get("text", "")[:200]}'
                if len(highlight.get("text", "")) > 200:
                    html += '...'
                html += '</div>'
            html += '</div></div>'
        
        html += '</div>'
    else:
        html += '<div class="no-data">No meeting summaries available yet.</div>'
    
    html += '</div>'
    
    # Footer
    html += """
            <div class="footer">
                <p>This is an automated email from AI Scrum Master.</p>
                <p>You are receiving this because you have active meetings with deadlines.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def format_email_text(
    user_name: Optional[str],
    upcoming_deadlines: List[Dict],
    last_meeting_summary: Optional[Dict],
) -> str:
    """Format email as plain text."""
    name = user_name or "there"
    
    text = f"""
Daily Reminder
==============

Hello {name}!

UPCOMING DEADLINES
------------------
"""
    
    if upcoming_deadlines:
        for deadline in upcoming_deadlines:
            days = days_until(deadline['due_date'])
            text += f"\n• {deadline['description']}\n"
            
            if deadline.get('owner'):
                text += f"  Owner: {deadline['owner']}\n"
            if deadline.get('priority'):
                text += f"  Priority: {deadline['priority']}\n"
            
            text += f"  Due: {format_date(deadline['due_date'])}"
            if days is not None:
                if days == 0:
                    text += " (Today!)"
                elif days == 1:
                    text += " (Tomorrow!)"
                else:
                    text += f" ({days} days)"
            text += "\n"
            
            text += f"  Meeting: {deadline['meeting_platform']} meeting on {format_date_short(deadline['meeting_start_time'])}\n"
    else:
        text += "\nNo upcoming deadlines in the next 7 days. Great job! 🎉\n"
    
    text += "\n\nLAST MEETING SUMMARY\n"
    text += "--------------------\n"
    
    if last_meeting_summary:
        text += f"\nDate: {format_date(last_meeting_summary['end_time'])}\n"
        text += f"Platform: {last_meeting_summary['platform']}\n"
        if last_meeting_summary.get('platform_specific_id'):
            text += f"Meeting ID: {last_meeting_summary['platform_specific_id']}\n"
        if last_meeting_summary.get('goal'):
            text += f"Goal: {last_meeting_summary['goal']}\n"
        if last_meeting_summary.get('sentiment'):
            text += f"Sentiment: {last_meeting_summary['sentiment']}\n"
        if last_meeting_summary.get('transcript_count'):
            text += f"Transcript segments: {last_meeting_summary['transcript_count']}\n"
        
        text += f"\nSummary:\n{last_meeting_summary['summary']}\n"
        
        # Blockers
        if last_meeting_summary.get('blockers') and len(last_meeting_summary['blockers']) > 0:
            text += "\nBlockers:\n"
            for blocker in last_meeting_summary['blockers']:
                blocker_text = blocker if isinstance(blocker, str) else blocker.get('description', str(blocker))
                text += f"  - {blocker_text}\n"
        
        # Deadlines
        if last_meeting_summary.get('deadlines') and len(last_meeting_summary['deadlines']) > 0:
            text += "\nDeadlines Mentioned:\n"
            for deadline in last_meeting_summary['deadlines']:
                deadline_text = deadline if isinstance(deadline, str) else deadline.get('description', str(deadline))
                text += f"  - {deadline_text}\n"
        
        # Highlights
        if last_meeting_summary.get('highlights') and len(last_meeting_summary['highlights']) > 0:
            text += "\nKey Highlights:\n"
            for highlight in last_meeting_summary['highlights'][:5]:
                label_emoji = {
                    'обновление': '📊',
                    'решение': '✅',
                    'блокер': '🚧',
                    'другое': '💬',
                }.get(highlight.get('label', '').lower(), '💬')
                
                if highlight.get('speaker'):
                    text += f"  {label_emoji} {highlight['speaker']}: "
                text += f"{highlight.get('text', '')[:200]}\n"
    else:
        text += "\nNo meeting summaries available yet.\n"
    
    text += "\n\n---\n"
    text += "This is an automated email from AI Scrum Master.\n"
    text += "You are receiving this because you have active meetings with deadlines.\n"
    
    return text

