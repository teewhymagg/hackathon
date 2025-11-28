#!/usr/bin/env python3
"""Delete Jira issues created by meeting sync for testing purposes"""
import os
import sys
from jira import JIRA, JIRAError
from dotenv import load_dotenv

load_dotenv()

def delete_meeting_issues(delete_all=False):
    """Delete all issues with meeting-generated label, or all issues in project"""
    jira_base_url = os.environ.get("JIRA_BASE_URL")
    jira_email = os.environ.get("JIRA_USER_EMAIL")
    jira_token = os.environ.get("JIRA_API_TOKEN")
    project_key = os.environ.get("JIRA_PROJECT_KEY")
    
    if not all([jira_base_url, jira_email, jira_token, project_key]):
        print("Error: Missing required environment variables:")
        print("  - JIRA_BASE_URL")
        print("  - JIRA_USER_EMAIL")
        print("  - JIRA_API_TOKEN")
        print("  - JIRA_PROJECT_KEY")
        print("\nMake sure your .env file is configured.")
        sys.exit(1)
    
    jira = JIRA(
        server=jira_base_url,
        basic_auth=(jira_email, jira_token)
    )
    
    # Find issues - either all in project or just meeting-generated
    if delete_all:
        jql = f'project = {project_key}'
        print(f"⚠️  DELETING ALL ISSUES IN PROJECT {project_key}!")
    else:
        jql = f'project = {project_key} AND labels = meeting-generated'
        print(f"Searching for meeting-generated issues with JQL: {jql}")
    
    try:
        issues = jira.search_issues(jql, maxResults=1000)
        print(f"\nFound {len(issues)} issues to delete")
        
        if len(issues) == 0:
            print("No issues found. Nothing to delete.")
            return
        
        # Show what will be deleted
        print("\nIssues to delete:")
        for issue in issues[:10]:  # Show first 10
            print(f"  - {issue.key}: {issue.fields.summary[:60]}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")
        
        # Confirm
        print(f"\n⚠️  This will permanently delete {len(issues)} issues!")
        response = input("Type 'yes' to confirm: ")
        if response.lower() != 'yes':
            print("Cancelled. No issues deleted.")
            return
        
        deleted = 0
        failed = 0
        
        for issue in issues:
            try:
                print(f"Deleting {issue.key}...", end=" ", flush=True)
                issue.delete()
                print("✓")
                deleted += 1
            except JIRAError as e:
                print(f"✗ Error: {e.status_code} - {e.text}")
                failed += 1
            except Exception as e:
                print(f"✗ Error: {e}")
                failed += 1
        
        print(f"\n{'='*50}")
        print(f"✓ Successfully deleted {deleted} issues")
        if failed > 0:
            print(f"✗ Failed to delete {failed} issues")
        print(f"{'='*50}")
            
    except JIRAError as e:
        print(f"\nError searching issues: {e.status_code} - {e.text}")
        print("\nPossible issues:")
        print("  - Invalid Jira credentials")
        print("  - Project key doesn't exist")
        print("  - No permission to search issues")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Delete Jira issues")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Delete ALL issues in the project (not just meeting-generated)"
    )
    args = parser.parse_args()
    
    delete_meeting_issues(delete_all=args.all)

