from flask import Flask, render_template, request, jsonify
from pywebpush import webpush, WebPushException
from upstash_redis import Redis
from dotenv import load_dotenv
from datetime import datetime
from functools import wraps
from pathlib import Path
import requests
import hashlib
import json
import os

load_dotenv()


app = Flask(__name__)

redis = Redis(url=os.environ.get('KV_REST_API_URL'), token=os.environ.get('KV_REST_API_TOKEN'))
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
VAPID_CLAIMS = {
    "sub": "mailto:unused@unused.com"
}

# Rate limiting configuration
RATE_LIMIT_SUBSCRIBE = 5      # 5 subscription changes
RATE_LIMIT_WINDOW = 60        # per 1 minute

if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
    print("Warning: VAPID keys not found in environment variables!")


def get_user_id(subscription_info):
    """Generate a unique user ID from subscription endpoint"""
    return hashlib.sha256(subscription_info['endpoint'].encode()).hexdigest()


def find_logo(network):
    """Find logo file regardless of extension or case"""
    logos_dir = os.path.join('static', 'logos')
    network = network.lower()

    # Check for both .png and .svg extensions
    for ext in ['.png', '.svg', '.PNG', '.SVG']:
        # Use Path for case-insensitive matching
        possible_files = list(Path(logos_dir).glob(f'{network}{ext}'))
        if possible_files:
            # Return the path relative to static directory
            return f'logos/{possible_files[0].name}'

    return None  # Return None if no logo found


def rate_limit(limit_key, limit_count):
    """Rate limiting decorator"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get subscription info and user ID
            subscription_info = request.get_json()
            if not subscription_info:
                return jsonify({'status': 'error', 'message': 'No subscription info provided'}), 400

            user_id = get_user_id(subscription_info)

            # Create rate limit key specific to user and action
            rate_key = f"rate:{user_id}:{limit_key}"

            # Get current request count
            current = redis.get(rate_key)

            if current is None:
                # First request in window
                redis.setex(rate_key, RATE_LIMIT_WINDOW, 1)
            elif int(current) >= limit_count:
                # Rate limit exceeded
                ttl = redis.ttl(rate_key)
                return jsonify({
                    'status': 'error',
                    'message': f'Rate limit exceeded. Please try again in {ttl} seconds'
                }), 429
            else:
                # Increment request count
                redis.incr(rate_key)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


@app.route('/subscribe/<chain>', methods=['POST'])
@rate_limit('subscribe', RATE_LIMIT_SUBSCRIBE)
def subscribe(chain):
    subscription_info = request.get_json()
    user_id = get_user_id(subscription_info)

    # Store subscription info
    sub_key = f"sub:{user_id}:{chain}"
    redis.set(sub_key, json.dumps(subscription_info))

    # Add to chain's subscriber set
    chain_key = f"chain:{chain}:subscribers"
    redis.sadd(chain_key, user_id)

    # Add to user's subscribed chains set
    user_chains_key = f"user:{user_id}:chains"
    redis.sadd(user_chains_key, chain)

    return jsonify({'status': 'success'})


@app.route('/unsubscribe/<chain>', methods=['POST'])
@rate_limit('subscribe', RATE_LIMIT_SUBSCRIBE)  # Using same limit as subscribe
def unsubscribe(chain):
    subscription_info = request.get_json()
    user_id = get_user_id(subscription_info)

    # Remove subscription info
    sub_key = f"sub:{user_id}:{chain}"
    redis.delete(sub_key)

    # Remove from chain's subscriber set
    chain_key = f"chain:{chain}:subscribers"
    redis.srem(chain_key, user_id)

    # Remove from user's subscribed chains
    user_chains_key = f"user:{user_id}:chains"
    redis.srem(user_chains_key, chain)

    return jsonify({'status': 'success'})


@app.route('/subscriptions', methods=['POST'])
def get_subscriptions():
    """Get subscriptions for current user"""
    subscription_info = request.get_json()
    user_id = get_user_id(subscription_info)

    # Get user's subscribed chains
    user_chains_key = f"user:{user_id}:chains"
    subscribed_chains = redis.smembers(user_chains_key)

    print(user_chains_key)
    print(subscribed_chains)

    return jsonify(list(subscribed_chains) if subscribed_chains else [])


def get_chain_subscriptions(chain):
    """Get all subscriptions for a specific chain"""
    subscriptions = []
    chain_key = f"chain:{chain}:subscribers"

    # Get all user IDs subscribed to this chain
    user_ids = redis.smembers(chain_key)

    for user_id in user_ids:
        sub_key = f"sub:{user_id}:{chain}"
        sub_data = redis.get(sub_key)
        if sub_data:
            subscriptions.append(json.loads(sub_data))

    return subscriptions


def send_web_push(subscription_info, message):
    try:
        webpush(
            subscription_info=subscription_info,
            data=message,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
    except WebPushException as e:
        print(f"Web Push Failed: {e}")
        if e.response.status_code == 410:
            user_id = get_user_id(subscription_info)
            cleanup_invalid_subscription(user_id)


def cleanup_invalid_subscription(user_id):
    """Remove all subscriptions for a user"""
    # Get user's subscribed chains
    user_chains_key = f"user:{user_id}:chains"
    chains = redis.smembers(user_chains_key)

    for chain in chains:
        # Remove from chain's subscriber set
        chain_key = f"chain:{chain}:subscribers"
        redis.srem(chain_key, user_id)

        # Remove subscription info
        sub_key = f"sub:{user_id}:{chain}"
        redis.delete(sub_key)

    # Remove user's chain set
    redis.delete(user_chains_key)


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
                           current_sort=sort_order,
                           find_logo=find_logo,
                           vapid_public_key=VAPID_PUBLIC_KEY)


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        ssl_context='adhoc'  # This enables HTTPS with a self-signed certificate
    )