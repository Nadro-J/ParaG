from upstash_redis import Redis
from pywebpush import webpush, WebPushException
import json
import time
from typing import List, Tuple, Dict


class ChainNotificationService:
    def __init__(
            self,
            redis_url: str,
            redis_token: str,
            vapid_private_key: str,
            vapid_email: str
    ):
        """
        Initialize the notification service

        Args:
            redis_url: Upstash Redis URL
            redis_token: Upstash Redis Token
            vapid_private_key: VAPID private key for web push
            vapid_email: Email for VAPID claims
        """
        self.redis = Redis(url=redis_url, token=redis_token)
        self.vapid_private_key = vapid_private_key
        self.vapid_claims = {
            "sub": f"mailto:{vapid_email}"
        }

    def get_all_subscriptions(self) -> Dict[str, List[Dict]]:
        """
        Get all subscription details organized by chain

        Returns:
            Dict mapping chain names to lists of subscription info
        """
        try:
            # Get all chain keys
            chain_keys = self.redis.keys("chain:*:subscribers")
            all_subscriptions = {}

            for chain_key in chain_keys:
                # Extract chain name from key (chain:chainname:subscribers)
                chain = chain_key.split(':')[1]
                user_ids = self.redis.smembers(chain_key)

                chain_subscriptions = []
                for user_id in user_ids:
                    sub_key = f"sub:{user_id}:{chain}"
                    sub_data = self.redis.get(sub_key)

                    if sub_data:
                        subscription_info = json.loads(sub_data)
                        # Add user_id to subscription info for reference
                        subscription_info['user_id'] = user_id
                        chain_subscriptions.append(subscription_info)

                if chain_subscriptions:  # Only add chains that have active subscriptions
                    all_subscriptions[chain] = chain_subscriptions

            # Print summary
            total_chains = len(all_subscriptions)
            total_subscriptions = sum(len(subs) for subs in all_subscriptions.values())
            print(f"\nSubscription Summary:")
            print(f"Total chains with subscribers: {total_chains}")
            print(f"Total subscriptions: {total_subscriptions}")

            # Print per-chain details
            for chain, subscriptions in all_subscriptions.items():
                print(f"\n{chain.title()}: {len(subscriptions)} subscribers")
                for sub in subscriptions:
                    endpoint = sub.get('endpoint', 'Unknown endpoint')
                    print(f"- User ID: {sub.get('user_id', 'Unknown')}")
                    print(f"  Endpoint: {endpoint[:60]}...")  # Truncate long endpoints

            return all_subscriptions

        except Exception as e:
            print(f"Error fetching subscriptions: {e}")
            return {}

    def send_push_notification(self, subscription_info: Dict, message: str, chain: str) -> bool:
        """
        Send a push notification to a single subscriber

        Args:
            subscription_info: Dictionary containing subscription information
            message: Message to send
            chain: Chain identifier

        Returns:
            bool: True if successful or temporary error, False if subscription expired
        """
        try:
            notification_data = {
                'message': message,
                'chain': chain.title()
            }

            print(f"Attempting to send notification to endpoint: {subscription_info['endpoint'][:60]}...")
            print(f"Message: {notification_data['message']}")

            webpush(
                subscription_info=subscription_info,
                data=json.dumps(notification_data),
                vapid_private_key=self.vapid_private_key,
                vapid_claims=self.vapid_claims
            )
            print(f"Successfully sent notification to {subscription_info['endpoint']}")
            return True
        except WebPushException as e:
            if e.response.status_code == 410:
                print(f"Subscription expired: {subscription_info['endpoint']}")
                return False
            else:
                print(f"Push failed ({e.response.status_code}): {str(e)}")
                print(f"Endpoint: {subscription_info['endpoint']}")
                return True

    def notify_chain_subscribers(self, chain: str, message: str, delay: float = 0.1) -> Tuple[int, int, int]:
        """
        Send notification to all subscribers of a specific chain

        Args:
            chain: Chain identifier
            message: Message to send
            delay: Delay between notifications to prevent rate limiting

        Returns:
            Tuple[int, int, int]: (success_count, fail_count, cleaned_count)
        """
        chain = chain.lower()
        chain_key = f"chain:{chain}:subscribers"
        user_ids = self.redis.smembers(chain_key)

        if not user_ids:
            print(f"No subscribers found for chain: {chain}")
            return (0, 0, 0)

        success_count = 0
        fail_count = 0
        expired_subscriptions = []

        for user_id in user_ids:
            # Get subscription info
            sub_key = f"sub:{user_id}:{chain}"
            sub_data = self.redis.get(sub_key)

            if sub_data:
                subscription_info = json.loads(sub_data)
                success = self.send_push_notification(subscription_info, message, chain)

                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    expired_subscriptions.append((user_id, chain))

                # Add delay to prevent rate limiting
                if delay > 0:
                    time.sleep(delay)

        # Clean up expired subscriptions
        cleaned_count = self._cleanup_expired_subscriptions(expired_subscriptions)

        return success_count, fail_count, cleaned_count

    def notify_multiple_chains(self, chains: List[str], message: str, delay: float = 0.1) -> Dict[str, Tuple[int, int, int]]:
        """
        Send notifications to multiple chains

        Args:
            chains: List of chain identifiers
            message: Message to send
            delay: Delay between notifications

        Returns:
            Dict mapping chain to (success_count, fail_count, cleaned_count)
        """
        results = {}
        for chain in chains:
            results[chain] = self.notify_chain_subscribers(chain, message, delay)
        return results

    def _cleanup_expired_subscriptions(self, expired_subscriptions: List[Tuple[str, str]]) -> int:
        """
        Remove expired subscriptions from Redis

        Returns:
            int: Number of subscriptions cleaned up
        """
        for user_id, chain in expired_subscriptions:
            sub_key = f"sub:{user_id}:{chain}"
            chain_key = f"chain:{chain}:subscribers"
            user_chains_key = f"user:{user_id}:chains"

            # Remove from all relevant sets
            self.redis.delete(sub_key)
            self.redis.srem(chain_key, user_id)
            self.redis.srem(user_chains_key, chain)

        return len(expired_subscriptions)

    def clear_all_subscriptions(self) -> int:
        """
        Clear all subscriptions from Redis

        Returns:
            int: Number of subscriptions cleared
        """
        try:
            # Get all chain subscriber sets
            chain_keys = self.redis.keys("chain:*:subscribers")
            # Get all user subscription data
            sub_keys = self.redis.keys("sub:*")
            # Get all user chain sets
            user_chain_keys = self.redis.keys("user:*:chains")

            total_keys = len(chain_keys) + len(sub_keys) + len(user_chain_keys)

            # Delete all related keys
            for key in chain_keys + sub_keys + user_chain_keys:
                self.redis.delete(key)

            print(f"Cleared {total_keys} subscription-related keys")
            return total_keys

        except Exception as e:
            print(f"Error clearing subscriptions: {e}")
            return 0
