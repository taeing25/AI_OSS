#!/usr/bin/env python3
"""
Measure and track lead time for issues and pull requests.

Lead time = time from creation to closure/completion.
This script:
1. Tracks when issues/PRs are created and closed
2. Calculates lead time in hours and days
3. Records metrics to JSON file
4. Generates reports and analytics
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from github import Github, GithubException

# Configuration
METRICS_DIR = Path('.github/metrics')
METRICS_FILE = METRICS_DIR / 'lead_time_metrics.json'
REPORT_FILE = METRICS_DIR / 'lead_time_report.md'

def get_github_client():
    """Initialize GitHub client."""
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable not set")
    return Github(token)

def ensure_metrics_dir():
    """Create metrics directory if it doesn't exist."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

def load_metrics() -> Dict:
    """Load existing metrics from file."""
    if METRICS_FILE.exists():
        with open(METRICS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_metrics(metrics: Dict):
    """Save metrics to file."""
    ensure_metrics_dir()
    with open(METRICS_FILE, 'w') as f:
        json.dump(metrics, f, indent=2)

def calculate_lead_time(created_at, closed_at) -> Dict:
    """Calculate lead time between two dates."""
    if not created_at or not closed_at:
        return {'hours': None, 'days': None, 'status': 'incomplete'}
    
    # Handle both string and datetime objects
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    if isinstance(closed_at, str):
        closed_at = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
    
    # Make timezone-aware comparison
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=None)
    if closed_at.tzinfo is None:
        closed_at = closed_at.replace(tzinfo=None)
    
    delta = closed_at - created_at
    hours = delta.total_seconds() / 3600
    days = hours / 24
    
    return {
        'hours': round(hours, 2),
        'days': round(days, 2),
        'status': 'completed'
    }

def process_issues(repo):
    """Process all issues and track lead time."""
    metrics = load_metrics()
    
    print("📋 Processing issues...")
    
    # Get all closed issues
    issues = repo.get_issues(state='closed', sort='updated')
    
    updated_count = 0
    for issue in issues:
        issue_num = issue.number
        
        # Skip PRs (they have pull_request attribute)
        if issue.pull_request:
            continue
        
        # Check if we need to update
        existing = metrics.get(f'issue_{issue_num}', {})
        
        if issue.closed_at:
            lead_time = calculate_lead_time(
                issue.created_at,
                issue.closed_at
            )
            
            metric_data = {
                'type': 'issue',
                'number': issue_num,
                'title': issue.title,
                'created_at': issue.created_at.isoformat(),
                'closed_at': issue.closed_at.isoformat(),
                'lead_time_hours': lead_time['hours'],
                'lead_time_days': lead_time['days'],
                'labels': [label.name for label in issue.labels],
                'status': lead_time['status']
            }
            
            if metric_data != existing:
                metrics[f'issue_{issue_num}'] = metric_data
                updated_count += 1
                print(f"  ✅ Issue #{issue_num}: {lead_time['hours']} hours ({lead_time['days']} days)")
    
    save_metrics(metrics)
    return updated_count

def process_pull_requests(repo):
    """Process all pull requests and track lead time."""
    metrics = load_metrics()
    
    print("\n🔄 Processing pull requests...")
    
    # Get all closed PRs
    prs = repo.get_pulls(state='closed', sort='updated')
    
    updated_count = 0
    for pr in prs:
        pr_num = pr.number
        
        # Check if we need to update
        existing = metrics.get(f'pr_{pr_num}', {})
        
        if pr.merged_at or pr.closed_at:
            close_time = pr.merged_at if pr.merged_at else pr.closed_at
            lead_time = calculate_lead_time(
                pr.created_at,
                close_time
            )
            
            metric_data = {
                'type': 'pull_request',
                'number': pr_num,
                'title': pr.title,
                'created_at': pr.created_at.isoformat(),
                'closed_at': (pr.merged_at or pr.closed_at).isoformat(),
                'merged': pr.merged,
                'lead_time_hours': lead_time['hours'],
                'lead_time_days': lead_time['days'],
                'labels': [label.name for label in pr.labels],
                'status': 'merged' if pr.merged else 'closed'
            }
            
            if metric_data != existing:
                metrics[f'pr_{pr_num}'] = metric_data
                updated_count += 1
                status = "merged" if pr.merged else "closed"
                print(f"  ✅ PR #{pr_num} ({status}): {lead_time['hours']} hours ({lead_time['days']} days)")
    
    save_metrics(metrics)
    return updated_count

def generate_report(metrics: Dict):
    """Generate lead time report."""
    print("\n📊 Generating report...")
    
    ensure_metrics_dir()
    
    # Extract metrics
    issues = [m for k, m in metrics.items() if k.startswith('issue_') and m.get('status') == 'completed']
    prs = [m for k, m in metrics.items() if k.startswith('pr_')]
    
    # Calculate statistics
    def calc_stats(items):
        if not items:
            return {}
        times = [item['lead_time_hours'] for item in items if item['lead_time_hours']]
        if not times:
            return {}
        return {
            'count': len(items),
            'avg_hours': round(sum(times) / len(times), 2),
            'avg_days': round(sum(times) / len(times) / 24, 2),
            'min_hours': min(times),
            'max_hours': max(times),
        }
    
    issue_stats = calc_stats(issues)
    pr_stats = calc_stats(prs)
    
    # Generate markdown report
    report_lines = [
        "# Lead Time Metrics Report\n",
        f"_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n"
    ]
    
    if issue_stats:
        report_lines.extend([
            "## Issues\n",
            f"- **Total Closed**: {issue_stats['count']}",
            f"- **Average Lead Time**: {issue_stats['avg_hours']} hours ({issue_stats['avg_days']} days)",
            f"- **Fastest**: {issue_stats['min_hours']} hours",
            f"- **Slowest**: {issue_stats['max_hours']} hours\n"
        ])
    
    if pr_stats:
        report_lines.extend([
            "## Pull Requests\n",
            f"- **Total Merged/Closed**: {pr_stats['count']}",
            f"- **Average Lead Time**: {pr_stats['avg_hours']} hours ({pr_stats['avg_days']} days)",
            f"- **Fastest**: {pr_stats['min_hours']} hours",
            f"- **Slowest**: {pr_stats['max_hours']} hours\n"
        ])
    
    if issue_stats or pr_stats:
        report_lines.append("## Recent Items\n")
        
        # Show recent items sorted by lead time
        all_items = sorted(
            issues + prs,
            key=lambda x: x.get('lead_time_hours', 0),
            reverse=True
        )[:10]
        
        report_lines.append("| Type | Number | Title | Lead Time |")
        report_lines.append("|------|--------|-------|-----------|")
        
        for item in all_items:
            item_type = "Issue" if item['type'] == 'issue' else "PR"
            lead_time = f"{item['lead_time_hours']} hrs"
            title = item['title'][:40] + "..." if len(item['title']) > 40 else item['title']
            report_lines.append(f"| {item_type} | #{item['number']} | {title} | {lead_time} |")
    
    report_lines.append("")  # Final newline
    
    report_content = '\n'.join(report_lines)
    
    with open(REPORT_FILE, 'w') as f:
        f.write(report_content)
    
    print(f"✅ Report saved to {REPORT_FILE}")

def main():
    """Main function."""
    print("🚀 Starting Lead Time Measurement...\n")
    
    try:
        # Initialize GitHub client
        gh = get_github_client()
        repo = gh.get_repo(os.getenv('GITHUB_REPOSITORY'))
        
        print(f"Repository: {repo.full_name}\n")
        
        # Process issues and PRs
        issue_updates = process_issues(repo)
        pr_updates = process_pull_requests(repo)
        
        # Load and generate report
        metrics = load_metrics()
        generate_report(metrics)
        
        # Summary
        total_updates = issue_updates + pr_updates
        print(f"\n✨ Summary:")
        print(f"  - Issues updated: {issue_updates}")
        print(f"  - PRs updated: {pr_updates}")
        print(f"  - Total metrics tracked: {len(metrics)}")
        
        if total_updates > 0:
            print(f"\n📝 Changes detected - metrics have been updated")
        else:
            print(f"\n✅ No changes needed")
    
    except GithubException as e:
        print(f"❌ GitHub API Error: {e}")
        exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)

if __name__ == '__main__':
    main()
