from flask import Flask, render_template, request
import json
import requests
from datetime import datetime

app = Flask(__name__)


def load_proposal_data():
    """Load proposal data from Vercel Blob"""
    try:
        blob_url = "https://4cwblgexlswrqurf.public.blob.vercel-storage.com/proposal_results.json"
        response = requests.get(f"{blob_url}")
        return json.loads(response.content)
    except Exception as e:
        print(f"Error loading data from blob: {e}")
        return {}


def get_end_date(governance_data):
    """Extract end date from governance data"""
    if not governance_data or not isinstance(governance_data, dict):
        return None

    info = governance_data.get('info', {})
    if not info:
        return None

    # Handle Finished case
    if 'Finished' in info:
        return info['Finished'].get('end')
    # Handle Approved case
    elif 'Approved' in info and isinstance(info['Approved'], list) and len(info['Approved']) > 0:
        return info['Approved'][0]
    # Handle Ongoing case
    elif 'Ongoing' in info:
        return info['Ongoing'].get('end')

    return None


def has_ongoing_proposal(info):
    """Check if a network has any ongoing proposals"""
    # Safely check democracy proposals
    democracy_info = info.get('democracy', {})
    if democracy_info and isinstance(democracy_info, dict):
        democracy_inner_info = democracy_info.get('info', {})
        if democracy_inner_info and isinstance(democracy_inner_info, dict):
            if democracy_inner_info.get('Ongoing'):
                return True

    # Safely check opengov proposals
    opengov_info = info.get('opengov', {})
    if opengov_info and isinstance(opengov_info, dict):
        opengov_inner_info = opengov_info.get('info', {})
        if opengov_inner_info and isinstance(opengov_inner_info, dict):
            if opengov_inner_info.get('Ongoing'):
                return True

    return False


def get_status_class(ended_at, has_ongoing=False):
    """Get the status class, considering ongoing proposals"""
    if has_ongoing:
        return 'bg-success'  # Always green for ongoing
    if not ended_at:
        return 'bg-secondary'

    try:
        ended_date = datetime.strptime(ended_at, '%Y-%m-%d')
        days_ago = (datetime.now() - ended_date).days

        if days_ago >= 60:
            return 'bg-danger'
        elif days_ago >= 30:
            return 'bg-warning'
        else:
            return 'bg-success'
    except:
        return 'bg-secondary'


def get_days_since(ended_at, has_ongoing=False):
    """Get days since last activity, considering ongoing proposals"""
    if has_ongoing:
        return -1  # Ongoing proposals should appear first
    if not ended_at:
        return float('inf')
    try:
        ended_date = datetime.strptime(ended_at, '%Y-%m-%d')
        return (datetime.now() - ended_date).days
    except:
        return float('inf')


@app.route('/')
def index():
    data = load_proposal_data()
    sort_order = request.args.get('sort', 'newest')

    processed_data = {}
    for network, info in data.items():
        # Check for ongoing proposals
        is_ongoing = has_ongoing_proposal(info)

        # Get ended_at dates for completed proposals
        democracy_ended = None
        opengov_ended = None

        # Safely check democracy
        democracy_data = info.get('democracy')
        if democracy_data is not None:  # Only try to get ended_at if democracy exists
            democracy_ended = democracy_data.get('ended_at')

        # Safely check opengov
        opengov_data = info.get('opengov')
        if opengov_data is not None:  # Only try to get ended_at if opengov exists
            opengov_ended = opengov_data.get('ended_at')

        # Get the most recent ended_at
        dates = [d for d in [democracy_ended, opengov_ended] if d is not None]
        latest_ended = max(dates) if dates else None

        processed_data[network] = {
            **info,
            'is_ongoing': is_ongoing,
            'latest_ended': latest_ended,
            'days_since': get_days_since(latest_ended, is_ongoing)
        }

    # Sort the data (ongoing first, then by date)
    sorted_data = dict(sorted(
        processed_data.items(),
        key=lambda x: x[1]['days_since'],
        reverse=(sort_order == 'oldest')
    ))

    return render_template('index.html',
                           data=sorted_data,
                           get_status_class=get_status_class,
                           current_sort=sort_order)


if __name__ == '__main__':
    app.run()
