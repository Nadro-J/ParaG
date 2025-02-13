import os
import json
import yaml
import discord
from upstash_redis import Redis
from discord.ui import Button, View
from discord import app_commands, ButtonStyle
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class ConfirmSubscriptionView(View):
    def __init__(self, original_interaction, chain, existing_chain, callback):
        super().__init__(timeout=60)  # Button expires after 60 seconds
        self.original_interaction = original_interaction
        self.callback = callback

        # Add confirm button
        confirm_button = Button(
            style=ButtonStyle.danger,
            label="Acknowledge Overwrite",
            custom_id="confirm_subscribe"
        )
        confirm_button.callback = self.button_callback
        self.add_item(confirm_button)

        # Add cancel button
        cancel_button = Button(
            style=ButtonStyle.secondary,
            label="Cancel",
            custom_id="cancel_subscribe"
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

    async def button_callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.original_interaction.user.id:
            for button in self.children:
                button.disabled = True
            await interaction.response.edit_message(view=self)
            await self.callback()
        else:
            await interaction.response.send_message(
                "Only the command user can confirm this action.",
                ephemeral=True
            )

    async def cancel_callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.original_interaction.user.id:
            try:
                # Use defer to acknowledge the interaction first
                await interaction.response.defer()

                await interaction.edit_original_response(content="Cancelled", view=None)

                try:
                    await interaction.delete_original_response()
                except discord.NotFound:
                    pass
            except Exception as e:
                try:
                    await interaction.followup.send("Cancelled", ephemeral=True)
                except:
                    pass
        else:
            await interaction.response.send_message(
                "Only the command user can cancel this action.",
                ephemeral=True
            )


class ChainUpdateBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.redis = Redis(
            url=os.environ.get('KV_REST_API_URL'),
            token=os.environ.get('KV_REST_API_TOKEN')
        )

    async def setup_hook(self):
        await self.tree.sync()


class ChainCommands(app_commands.Group):
    def __init__(self, bot: ChainUpdateBot):
        super().__init__(name="alerts", description="Subscribe to governance alerts")
        self.bot = bot


    @staticmethod
    def is_bot_owner():
        async def predicate(interaction: discord.Interaction) -> bool:
            return interaction.user.id == 185365893499322368

        return app_commands.check(predicate)

    @staticmethod
    def is_guild_owner():
        async def predicate(interaction: discord.Interaction) -> bool:
            return interaction.user.id == interaction.guild.owner_id

        return app_commands.check(predicate)

    async def chain_autocomplete(self, interaction: discord.Interaction, current: str,) -> list[app_commands.Choice[str]]:
        with open('../networks.yaml', 'r') as f:
            networks = yaml.safe_load(f)

        choices = []
        for name in networks.keys():
            if current.lower() in name.lower():
                display_name = name.title()
                if len(display_name) > 97:
                    display_name = display_name[:97] + "..."
                choices.append(app_commands.Choice(name=display_name, value=name))

        return choices[:25]

    @app_commands.command(name="debug")
    @is_bot_owner()
    @app_commands.describe(lookup="Optional: Guild ID or name to lookup subscriptions")
    async def debug_data(self, interaction: discord.Interaction, lookup: str = None):
        """Debug Redis data for this channel or lookup guild subscriptions"""
        if lookup:
            webhook_keys = self.bot.redis.keys("webhook:*")
            found_subscriptions = []

            for key in webhook_keys:
                data = self.bot.redis.get(key)
                if data:
                    webhook_data = json.loads(data)
                    if (str(lookup) == webhook_data.get('guild_id') or
                            lookup.lower() in webhook_data.get('guild_name', '').lower()):
                        found_subscriptions.append({
                            'chain': webhook_data['chain'],
                            'channel_name': webhook_data['channel_name'],
                            'guild_name': webhook_data['guild_name'],
                            'webhook_id': key.split(':')[1]
                        })

            if found_subscriptions:
                print(found_subscriptions)
                debug_info = [f"Found {len(found_subscriptions)} subscriptions:"]
                for sub in found_subscriptions:
                    debug_info.append(f"\nChain: {sub['chain']}")
                    debug_info.append(f"Channel: #{sub['channel_name']}")
                    debug_info.append(f"Webhook ID: {sub['webhook_id']}")
            else:
                debug_info = [f"No subscriptions found for: {lookup}"]

        else:
            webhooks = await interaction.channel.webhooks()
            webhook = discord.utils.get(webhooks, name='Chain Updates')

            if not webhook:
                await interaction.response.send_message(
                    "No webhook found in this channel.",
                    ephemeral=True
                )
                return

            webhook_key = f"webhook:{webhook.id}"
            webhook_data = self.bot.redis.get(webhook_key)
            chain_keys = self.bot.redis.keys("chain:*:webhooks")

            debug_info = []
            debug_info.append(f"Webhook ID: {webhook.id}")
            debug_info.append(f"Webhook Key: {webhook_key}")

            if webhook_data:
                data = json.loads(webhook_data)
                debug_info.append(f"Stored Data: {json.dumps(data, indent=2)}")
            else:
                debug_info.append("No stored data found for webhook")

            for chain_key in chain_keys:
                chain = chain_key.split(':')[1]
                if self.bot.redis.sismember(chain_key, str(webhook.id)):
                    debug_info.append(f"Found in {chain} webhook set")

        await interaction.response.send_message(
            "Debug Information:\n```json\n" + "\n".join(debug_info) + "\n```",
            ephemeral=True
        )

    @debug_data.error
    async def debug_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.CheckFailure):
            await interaction.response.send_message(
                "⛔ Only the bot owner can use this command.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Debug failed: {str(error)}",
                ephemeral=True
            )

    @app_commands.command(name="subscribe")
    @app_commands.describe(chain="The blockchain to subscribe to", notify_role="Role to notify for updates", channel="The channel to send updates to (defaults to current channel)")
    @app_commands.autocomplete(chain=chain_autocomplete)
    async def subscribe(self, interaction: discord.Interaction, chain: str, notify_role: discord.Role, channel: discord.TextChannel = None):
        try:
            target_channel = channel or interaction.channel
            if not target_channel.permissions_for(interaction.user).manage_webhooks:
                await interaction.response.send_message(
                    "⛔ You need `Manage Webhooks` permission to subscribe to updates.",
                    ephemeral=True
                )
                return

            # Check for any pending subscriptions in progress
            webhooks = await target_channel.webhooks()
            webhook = discord.utils.get(webhooks, name='Chain Updates')

            if webhook:
                webhook_key = f"webhook:{webhook.id}"
                existing_data = self.bot.redis.get(webhook_key)

                if existing_data:
                    existing_sub = json.loads(existing_data)
                    existing_chain = existing_sub.get('chain')

                    # Check if there's already a subscription confirmation pending
                    async for message in target_channel.history(limit=10):
                        if (message.author.id == interaction.client.user.id and
                                "Continuing will replace the existing subscription" in message.content and
                                not message.content.startswith("✅")):
                            await interaction.response.send_message(
                                "⚠️ There's already a pending subscription confirmation in this channel. "
                                "Please handle that first or wait for it to expire.",
                                ephemeral=True
                            )
                            return

                    if existing_chain and existing_chain != chain:
                        async def subscribe_callback():
                            await self.process_subscription(interaction, chain, notify_role, target_channel)

                        view = ConfirmSubscriptionView(
                            interaction,
                            chain,
                            existing_chain,
                            subscribe_callback
                        )

                        await interaction.response.send_message(
                            f"⚠️ This channel is already subscribed to **{existing_chain}** updates.\n"
                            f"Continuing will replace the existing subscription with **{chain}**.",
                            view=view,
                            ephemeral=True
                        )
                        return
                    elif existing_chain == chain:
                        await interaction.response.send_message(
                            f"⚠️ This channel is already subscribed to **{chain}** updates.",
                            ephemeral=True
                        )
                        return

            await self.process_subscription(interaction, chain, notify_role, target_channel)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to subscribe: {str(e)}",
                ephemeral=True
            )

    async def process_subscription(self, interaction: discord.Interaction, chain: str, notify_role: discord.Role, target_channel: discord.TextChannel):
        """Process the actual subscription after confirmation if needed"""
        try:
            webhooks = await target_channel.webhooks()
            webhook = discord.utils.get(webhooks, name='Chain Updates')

            # If webhook exists, clean up old Redis entries before creating new subscription
            if webhook:
                webhook_key = f"webhook:{webhook.id}"
                # Get existing subscription data to find the old chain
                existing_data = self.bot.redis.get(webhook_key)
                if existing_data:
                    existing_sub = json.loads(existing_data)
                    old_chain = existing_sub.get('chain')
                    if old_chain:
                        # Remove webhook ID from old chain's set
                        old_chain_key = f"chain:{old_chain}:webhooks"
                        self.bot.redis.srem(old_chain_key, str(webhook.id))
                    # Delete the old webhook data
                    self.bot.redis.delete(webhook_key)

            # Create new webhook if it doesn't exist
            if not webhook:
                try:
                    avatar_path = next((p for p in Path('..', 'static', 'logos').glob(f'{chain}.*') if p.stem.lower() == chain.lower()), None)

                    with open(avatar_path, 'rb') as image:
                        avatar_bytes = image.read()

                    webhook = await target_channel.create_webhook(name='Chain Updates', avatar=avatar_bytes)
                except Exception as e:
                    print(f"Failed to create webhook with avatar: {e}")
                    webhook = await target_channel.create_webhook(name='Chain Updates')

            # Store new subscription in Redis
            webhook_key = f"webhook:{webhook.id}"
            subscription = {
                'webhook_url': webhook.url,
                'channel_id': str(target_channel.id),
                'channel_name': target_channel.name,
                'guild_id': str(interaction.guild_id),
                'guild_name': interaction.guild.name,
                'chain': chain,
                'notify': str(notify_role.id)
            }

            # Store webhook info
            self.bot.redis.set(webhook_key, json.dumps(subscription))

            # Add to chain's webhook set
            chain_key = f"chain:{chain}:webhooks"
            self.bot.redis.sadd(chain_key, str(webhook.id))

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"✅ Successfully subscribed to {chain} updates in {target_channel.mention} with {notify_role.mention} notifications",
                    ephemeral=True
                )
            else:
                await interaction.edit_original_response(
                    content=f"✅ Successfully subscribed to {chain} updates in {target_channel.mention} with {notify_role.mention} notifications",
                    view=None
                )

        except Exception as e:
            error_message = f"❌ Failed to subscribe: {str(e)}"
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.edit_original_response(content=error_message, view=None)

    @app_commands.command(name="unsubscribe")
    @app_commands.describe(chain="The blockchain to unsubscribe from", channel="The channel to unsubscribe (defaults to current channel)")
    @app_commands.autocomplete(chain=chain_autocomplete)
    async def unsubscribe(self, interaction: discord.Interaction, chain: str, channel: discord.TextChannel = None):
        try:
            target_channel = channel or interaction.channel
            if not target_channel.permissions_for(interaction.user).manage_webhooks:
                await interaction.response.send_message(
                    "⛔ You need `Manage Webhooks` permission to subscribe to updates.",
                    ephemeral=True
                )
                return

            webhooks = await target_channel.webhooks()
            webhook = discord.utils.get(webhooks, name='Chain Updates')

            if webhook:
                webhook_key = f"webhook:{webhook.id}"
                chain_key = f"chain:{chain}:webhooks"

                # Remove from Redis
                self.bot.redis.delete(webhook_key)
                self.bot.redis.srem(chain_key, str(webhook.id))

                # Delete webhook if no more subscriptions
                await webhook.delete()

                await interaction.response.send_message(
                    f"✅ Successfully unsubscribed from {chain} updates in {target_channel.mention}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "No subscription found in this channel.",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to unsubscribe: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="list")
    async def list_subscriptions(self, interaction: discord.Interaction):
        """List all chain subscriptions in this server"""
        try:
            webhook_keys = self.bot.redis.keys("webhook:*")
            server_subscriptions = []

            for key in webhook_keys:
                data = self.bot.redis.get(key)
                if data:
                    webhook_data = json.loads(data)
                    # Check if this webhook belongs to the current server
                    if str(interaction.guild_id) == webhook_data.get('guild_id'):
                        server_subscriptions.append({
                            'chain': webhook_data['chain'],
                            'channel_id': webhook_data['channel_id']
                        })

            if server_subscriptions:
                subscriptions_info = [f"Found {len(server_subscriptions)} active subscriptions in this server:"]
                for sub in server_subscriptions:
                    subscriptions_info.append(f"- {sub['chain']} in <#{sub['channel_id']}> - `{sub['channel_id']}`")

                await interaction.response.send_message(
                    "\n".join(subscriptions_info),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "No active subscriptions found in this server.",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to list subscriptions: {str(e)}",
                ephemeral=True
            )


def setup_bot():
    bot = ChainUpdateBot()
    chain_commands = ChainCommands(bot)
    bot.tree.add_command(chain_commands)
    return bot


if __name__ == "__main__":
    bot = setup_bot()
    bot.run(os.environ.get('DISCORD_API_KEY'))
