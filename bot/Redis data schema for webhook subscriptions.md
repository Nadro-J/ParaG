# Redis Data Schema - Webhook subscriptions

## Overview
The subscription system uses Redis to store two main types of data:
1. Webhook details (using Redis SET)
2. Chain-to-webhook mappings (using Redis SETS)

## Data Structures

### 1. Webhook Details
**Key Pattern:** `webhook:{webhook_id}`  
**Type:** String (JSON)  
**Example Key:** `webhook:1318642690853830667`

```json
{
    "webhook_url": "https://discord.com/api/webhooks/1318642690853830667/token",
    "channel_id": "1318426821007507476",
    "channel_name": "governance",
    "guild_id": "1013749210765590548",
    "guild_name": "Server Name",
    "chain": "Hydration"
}
```

### 2. Chain Webhook Mappings
**Key Pattern:** `chain:{chain_name}:webhooks`  
**Type:** Set  
**Example Key:** `chain:Hydration:webhooks`  
**Content:** Set of webhook IDs as strings

```
SMEMBERS chain:Hydration:webhooks
1. "1318642690853830667"
2. "1318642690853830668"
```

## Operations

### Subscribe
When a new subscription is created:
1. Create webhook details:
   ```redis
   SET webhook:{webhook_id} {json_data}
   ```
2. Add webhook to chain's set:
   ```redis
   SADD chain:{chain}:webhooks {webhook_id}
   ```

### Unsubscribe
When unsubscribing:
1. Remove webhook details:
   ```redis
   DEL webhook:{webhook_id}
   ```
2. Remove from chain's set:
   ```redis
   SREM chain:{chain}:webhooks {webhook_id}
   ```

### List Subscriptions
To get all subscriptions for a chain:
1. Get webhook IDs:
   ```redis
   SMEMBERS chain:{chain}:webhooks
   ```
2. For each ID, get details:
   ```redis
   GET webhook:{webhook_id}
   ```

## Important Notes

1. All webhook IDs are stored as strings to prevent floating-point precision issues
2. Channel and Guild IDs are also stored as strings
3. Chain names maintain their original case
4. Webhook URLs include the token and should be treated as sensitive data

## Example Queries

### Get All Webhooks for a Chain
```python
chain_key = f"chain:{chain}:webhooks"
webhook_ids = redis.smembers(chain_key)
```

### Get Webhook Details
```python
webhook_key = f"webhook:{webhook_id}"
webhook_data = redis.get(webhook_key)
if webhook_data:
    webhook_info = json.loads(webhook_data)
```

### Check if Webhook Exists in Chain Set
```python
chain_key = f"chain:{chain}:webhooks"
exists = redis.sismember(chain_key, str(webhook_id))
```