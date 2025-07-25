import os
from typing import Union
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import traceback
import sys
import functools
from discord import app_commands
import json

# Import database connection management
from database.connection import initialize_database, get_pool, close_pool
from database.cache import close_redis, set_cache, get_redis_client
from cachetools import TTLCache
from lists import config

prefix_cache = TTLCache(maxsize=1000, ttl=3600)


class DualStream:
    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file

    def write(self, data):
        self.original_stream.write(data)
        self.log_file.write(data)
        self.log_file.flush()

    def flush(self):
        self.original_stream.flush()
        self.log_file.flush()


log_file = open("bot.log", "a")
sys.stdout = DualStream(sys.stdout, log_file)
sys.stderr = DualStream(sys.stderr, log_file)

print("Logging started.")

intents = discord.Intents.all()


class MyBot(commands.AutoShardedBot):
    async def is_owner(self, user: Union[discord.User, discord.Member]) -> bool:
        if user is not None and getattr(user, "id", None) is not None:
            return user.id in config.Owners.__dict__.values()
        raise ValueError("User/User ID was None, or user object had no ID property")


async def get_prefix(bot, message):
    if not message.guild:
        return "o!"

    guild_id = message.guild.id
    if guild_id in prefix_cache:
        return prefix_cache[guild_id]

    pool = await get_pool()
    if not pool:
        return "o!"

    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT value FROM guild_settings WHERE guild_id = $1 AND key = 'prefix'",
            guild_id,
        )
        prefix = "o!"
        if result:
            # The value is stored as a JSON string, so we need to parse it.
            prefix = json.loads(result)

        prefix_cache[guild_id] = prefix
        return prefix


async def prefix_update_listener():
    redis = await get_redis_client()
    if not redis:
        print("Redis not available, prefix update listener will not run.")
        return

    pubsub = redis.pubsub()
    await pubsub.subscribe("prefix_updates")
    print("Subscribed to prefix_updates channel.")

    while True:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                print(f"Received raw prefix update: {message['data']}")
                data = message["data"].decode("utf-8")
                guild_id_str, new_prefix_json = data.split(":", 1)
                guild_id = int(guild_id_str)
                new_prefix = json.loads(new_prefix_json)
                prefix_cache[guild_id] = new_prefix
                print(f"Updated prefix for guild {guild_id} to '{new_prefix}'")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error in prefix_update_listener: {e}")


bot = MyBot(command_prefix=get_prefix, intents=intents, help_command=None)
bot.launch_time = discord.utils.utcnow()

ERROR_NOTIFICATION_USER_ID = config.Owners.ILIKEPANCAKES
ERROR_NOTIFICATION_CHANNEL_ID = getattr(config, "ERROR_NOTIFICATION_CHANNEL_ID", None)


def catch_exceptions(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            tb_string = "".join(traceback.format_exception(type(e), e, e.__traceback__)).strip()

            print(f"Uncaught exception in {func.__name__}:")
            print(tb_string)

            context = f"Function: {func.__name__}, Module: {func.__module__}"
            if args and hasattr(args[0], "__class__"):
                context += f", Class: {args[0].__class__.__name__}"

            bot_instance = None
            if args and hasattr(args[0], "bot"):
                bot_instance = args[0].bot
            elif args and isinstance(args[0], commands.Bot):
                bot_instance = args[0]
            else:
                bot_instance = bot

            if bot_instance:
                await send_error_dm(
                    bot_instance,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    error_traceback=tb_string,
                    context_info=context,
                )

            raise

    return wrapper


async def load_cogs():
    cogs_to_exclude = {
        "aimod",  # Deprecated, functionality split into other cogs
        "ban_appeal_cog",  # Obsolete, functionality replaced by appeal_cog
    }
    if not getattr(config, "LOAD_CONFIG_COG", True):
        cogs_to_exclude.add("config_cog")
    dashboard_cfg = getattr(config, "Dashboard", None)
    if not (dashboard_cfg and getattr(dashboard_cfg, "COMMAND_ENABLED", False)):
        cogs_to_exclude.add("dashboard_link_cog")
    for filename in os.listdir("cogs"):
        if filename.endswith(".py"):
            cog_name = filename[:-3]
            if cog_name in cogs_to_exclude or filename.startswith("_"):
                continue
            try:
                await bot.load_extension(f"cogs.{cog_name}")
                print(f"Loaded cog: {cog_name}")
            except Exception as e:
                print(f"Failed to load cog {cog_name}: {e}")
                tb_string = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                try:
                    await send_error_dm(
                        bot,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        error_traceback=tb_string,
                        context_info=f"Error loading cog: {cog_name}",
                    )
                except Exception as dm_error:
                    print(f"Failed to send error DM for cog loading error: {dm_error}")


async def send_error_dm(bot_instance, error_type, error_message, error_traceback=None, context_info=None):
    try:
        error_content = f"**Error Type:** {error_type}\n"
        error_content += f"**Error Message:** {error_message}\n"

        if context_info:
            error_content += f"**Context:** {context_info}\n"

        if error_traceback:
            if len(error_traceback) > 1500:
                error_traceback = error_traceback[:1500] + "...(truncated)"
            error_content += f"**Traceback:**\n```\n{error_traceback.strip()}\n```"

        if ERROR_NOTIFICATION_CHANNEL_ID:
            channel = bot_instance.get_channel(ERROR_NOTIFICATION_CHANNEL_ID)
            if channel is None:
                try:
                    channel = await bot_instance.fetch_channel(ERROR_NOTIFICATION_CHANNEL_ID)
                except Exception:
                    channel = None
            if not channel:
                print(f"Could not find channel with ID {ERROR_NOTIFICATION_CHANNEL_ID} to send error notification")
                return
            await channel.send(error_content)
            return

        user = await bot_instance.fetch_user(ERROR_NOTIFICATION_USER_ID)
        if not user:
            print(f"Could not find user with ID {ERROR_NOTIFICATION_USER_ID} to send error notification")
            return

        await user.send(error_content)
    except Exception as e:
        print(f"Failed to send error DM: {e}")


@bot.event
async def on_error(event, *args, **kwargs):
    error_type, error_value, error_traceback = sys.exc_info()
    tb_string = "".join(traceback.format_exception(error_type, error_value, error_traceback))

    print(f"Error in event {event}:")
    print(tb_string)

    context = f"Event: {event}"
    if args:
        context += f", Args: {args}"
    if kwargs:
        context += f", Kwargs: {kwargs}"

    await send_error_dm(
        bot,
        error_type=error_type.__name__,
        error_message=str(error_value),
        error_traceback=tb_string,
        context_info=context,
    )


@bot.event
async def on_command_error(ctx, error):
    error = getattr(error, "original", error)

    # Handle specific user-facing errors
    user_message = None
    should_notify_owner = True

    if isinstance(error, commands.CommandNotFound):
        user_message = f"❌ Command `{ctx.invoked_with}` not found. Use `{ctx.prefix}help` to see available commands."
        should_notify_owner = False
    elif isinstance(error, commands.MissingRequiredArgument):
        user_message = f"❌ Missing required argument: `{error.param.name}`. Use `{ctx.prefix}help {ctx.command}` for usage information."
        should_notify_owner = False
    elif isinstance(error, commands.BadArgument):
        user_message = f"❌ Invalid argument provided. Use `{ctx.prefix}help {ctx.command}` for usage_information."
        should_notify_owner = False
    elif isinstance(error, commands.TooManyArguments):
        user_message = f"❌ Too many arguments provided. Use `{ctx.prefix}help {ctx.command}` for usage information."
        should_notify_owner = False
    elif isinstance(error, commands.MissingPermissions):
        missing_perms = ", ".join(error.missing_permissions)
        user_message = f"❌ You don't have permission to use this command. Required permissions: {missing_perms}"
        should_notify_owner = False
    elif isinstance(error, commands.BotMissingPermissions):
        missing_perms = ", ".join(error.missing_permissions)
        user_message = (
            f"❌ I don't have the required permissions to execute this command. Missing permissions: {missing_perms}"
        )
        should_notify_owner = False
    elif isinstance(error, commands.NoPrivateMessage):
        user_message = "❌ This command cannot be used in private messages."
        should_notify_owner = False
    elif isinstance(error, commands.PrivateMessageOnly):
        user_message = "❌ This command can only be used in private messages."
        should_notify_owner = False
    elif isinstance(error, commands.NotOwner):
        user_message = "❌ This command can only be used by the bot owner."
        should_notify_owner = False
    elif isinstance(error, commands.CommandOnCooldown):
        user_message = f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds."
        should_notify_owner = False
    elif isinstance(error, commands.DisabledCommand):
        user_message = "❌ This command is currently disabled."
        should_notify_owner = False
    elif isinstance(error, commands.CheckFailure):
        user_message = "❌ You don't have permission to use this command."
        should_notify_owner = False

    # Send user-friendly message or generic error message
    try:
        if user_message:
            await ctx.send(user_message)
        else:
            await ctx.send("❌ An error occurred while executing the command. The bot owner has been notified.")
    except Exception:
        pass

    # Only notify owner for unexpected errors
    if should_notify_owner:
        tb_string = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        print(f"Command error in {ctx.command.name}:")
        print(tb_string)

        context = f"Command: {ctx.command.name}, Author: {ctx.author} ({ctx.author.id}), Guild: {ctx.guild.name if ctx.guild else 'DM'} ({ctx.guild.id if ctx.guild else 'N/A'}), Channel: {ctx.channel}"

        await send_error_dm(
            ctx.bot,
            error_type=type(error).__name__,
            error_message=str(error),
            error_traceback=tb_string,
            context_info=context,
        )


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error = getattr(error, "original", error)

    # Handle specific user-facing errors
    user_message = None
    should_notify_owner = True

    if isinstance(error, app_commands.CommandNotFound):
        user_message = f"❌ Command `{error.name}` not found."
        should_notify_owner = False
    elif isinstance(error, app_commands.MissingPermissions):
        missing_perms = ", ".join(error.missing_permissions)
        user_message = f"❌ You are missing the following required permissions: {missing_perms}"
        should_notify_owner = False
    elif isinstance(error, app_commands.BotMissingPermissions):
        missing_perms = ", ".join(error.missing_permissions)
        user_message = (
            f"❌ I don't have the required permissions to execute this command. Missing permissions: {missing_perms}"
        )
        should_notify_owner = False
    elif isinstance(error, app_commands.NoPrivateMessage):
        user_message = "❌ This command cannot be used in private messages."
        should_notify_owner = False
    elif isinstance(error, app_commands.CommandOnCooldown):
        user_message = f"❌ This command is on cooldown. Try again in {error.retry_after:.2f} seconds."
        should_notify_owner = False
    elif isinstance(error, app_commands.CheckFailure):
        user_message = "❌ You don't have permission to use this command."
        should_notify_owner = False
    elif isinstance(error, app_commands.TransformerError):
        user_message = f"❌ Invalid input provided: {str(error)}"
        should_notify_owner = False
    elif isinstance(error, commands.MissingRequiredArgument):
        user_message = f"❌ Missing required argument: `{error.param.name}`."
        should_notify_owner = False
    elif isinstance(error, commands.BadArgument):
        user_message = "❌ Invalid argument provided."
        should_notify_owner = False
    elif isinstance(error, commands.NotOwner):
        user_message = "❌ This command can only be used by the bot owner."
        should_notify_owner = False

    # Send user-friendly message or generic error message
    try:
        if user_message:
            if not interaction.response.is_done():
                await interaction.response.send_message(user_message, ephemeral=True)
            else:
                await interaction.followup.send(user_message, ephemeral=True)
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while executing the command. The bot owner has been notified.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while executing the command. The bot owner has been notified.",
                    ephemeral=True,
                )
    except Exception:
        pass

    # Only notify owner for unexpected errors
    if should_notify_owner:
        tb_string = "".join(traceback.format_exception(type(error), error, error.__traceback__)).strip()

        command_name = interaction.command.name if interaction.command else "Unknown"
        print(f"App command error in {command_name}:")
        print(tb_string)

        context = f"Command: {command_name}, Author: {interaction.user} ({interaction.user.id}), Guild: {interaction.guild.name if interaction.guild else 'DM'} ({interaction.guild.id if interaction.guild else 'N/A'}), Channel: {interaction.channel}"

        await send_error_dm(
            interaction.client,
            error_type=type(error).__name__,
            error_message=str(error),
            error_traceback=tb_string,
            context_info=context,
        )


@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        print("Commands synced successfully!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

        tb_string = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        await send_error_dm(
            bot,
            error_type=type(e).__name__,
            error_message=str(e),
            error_traceback=tb_string,
            context_info="Error occurred during command sync in on_ready event",
        )

    print(f"Logged in as {bot.user}")
    print(f"Global error handling is active - errors will be sent to user ID: {ERROR_NOTIFICATION_USER_ID}")
    await update_bot_guilds_cache()
    await update_launch_time_cache()
    await update_all_guild_member_caches()
    bot.loop.create_task(prefix_update_listener())


async def update_bot_guilds_cache():
    """Updates the Redis cache with the list of guild IDs the bot is in."""
    guild_ids = [guild.id for guild in bot.guilds]
    await set_cache("bot_guilds", guild_ids)
    print("Updated bot guilds cache.")


async def update_launch_time_cache():
    """Updates the Redis cache with the bot's launch time."""
    await set_cache("bot_launch_time", bot.launch_time.timestamp())
    print("Updated bot launch time cache.")


@bot.event
async def on_guild_join(guild):
    """Event handler for when the bot joins a guild."""
    print(f"Joined guild: {guild.name} ({guild.id})")
    await update_bot_guilds_cache()
    await update_guild_member_cache(guild)


@bot.event
async def on_guild_remove(guild):
    """Event handler for when the bot is removed from a guild."""
    print(f"Removed from guild: {guild.name} ({guild.id})")
    await update_bot_guilds_cache()
    redis = await get_redis_client()
    if redis:
        await redis.delete(f"guild:{guild.id}:members")
        print(f"Removed member cache for guild {guild.id}")


@bot.event
async def on_member_join(member):
    """Event handler for when a member joins a guild."""
    redis = await get_redis_client()
    if redis:
        await redis.sadd(f"guild:{member.guild.id}:members", member.id)
        print(f"Added member {member.id} to cache for guild {member.guild.id}")


@bot.event
async def on_member_remove(member):
    """Event handler for when a member leaves a guild."""
    redis = await get_redis_client()
    if redis:
        await redis.srem(f"guild:{member.guild.id}:members", member.id)
        print(f"Removed member {member.id} from cache for guild {member.guild.id}")


async def update_guild_member_cache(guild):
    """Caches the member IDs for a specific guild."""
    redis = await get_redis_client()
    if not redis:
        return

    key = f"guild:{guild.id}:members"
    try:
        # Fetch all members and store their IDs
        member_ids = [str(member.id) for member in guild.members]
        # Use a pipeline to clear and re-add members efficiently
        pipe = redis.pipeline()
        pipe.delete(key)
        if member_ids:
            pipe.sadd(key, *member_ids)
        await pipe.execute()
        print(f"Updated member cache for guild {guild.name} ({guild.id}) with {len(member_ids)} members.")
    except discord.Forbidden:
        print(f"Missing permissions to fetch members for guild {guild.name} ({guild.id}).")
    except Exception as e:
        print(f"Error caching members for guild {guild.name} ({guild.id}): {e}")


async def update_all_guild_member_caches():
    """Iterates through all guilds and caches their members."""
    print("Starting to cache all guild members...")
    for guild in bot.guilds:
        await update_guild_member_cache(guild)
    print("Finished caching all guild members.")


@bot.event
async def on_shard_ready(shard_id):
    print(f"Shard {shard_id} is ready.")


@bot.command(name="testerror")
async def test_error(ctx):
    await ctx.send(f"Testing error handling in {ctx.command}...")
    raise ValueError("This is a test error to verify error handling")


@bot.tree.command(name="testerror", description="Test slash command to verify error handling")
async def test_error_slash(interaction: discord.Interaction):
    await interaction.response.send_message("Testing error handling in slash command...")
    raise ValueError("This is a test error to verify slash command error handling")


async def main():
    try:
        load_dotenv(".env")
        discord_token = os.getenv("DISCORD_TOKEN")

        if not discord_token:
            raise ValueError("Missing DISCORD_TOKEN environment variable.")

        # Initialize database before loading cogs
        print("Initializing database connection...")
        db_success = await initialize_database()
        if db_success:
            print("Database initialized successfully!")
        else:
            print("Failed to initialize database. Exiting.")
            return

        async with bot:
            await load_cogs()
            await bot.start(discord_token)
    finally:
        # Clean up database connections
        print("Closing database connections...")
        await close_pool()
        await close_redis()
        print("Database connections closed.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Critical error during bot startup: {e}")
        tb_string = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        print(tb_string)

        print(f"Could not send error notification to user ID {ERROR_NOTIFICATION_USER_ID} - bot not running")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        print(f"Traceback: {tb_string}")
    finally:
        if "log_file" in locals() and not log_file.closed:
            log_file.close()
