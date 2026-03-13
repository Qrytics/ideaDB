"""
bot.py
======
IdeaDB — Discord bot entry point.

Listens to every message in every channel, runs MetadataParser on it
(text, attachments, GIFs, links), stores the results, and responds to
slash-style prefix commands for idea generation and analytics.

Commands
--------
  !ideas  [count]   — Ask the LLM to generate <count> ideas (default 5)
  !keywords          — Show the top keywords collected so far
  !stats             — Show collection statistics
  !clear             — (Admin) Wipe all data for this server
  !help ideadb       — Show this help
"""

import os
from typing import Dict

import discord
from discord.ext import commands

from database import Database
from idea_generator import IdeaGenerator
from metadata_parser import MetadataParser

# ---------------------------------------------------------------------------
# Load configuration
# ---------------------------------------------------------------------------
load_dotenv()

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
DB_PATH: str = os.getenv("DB_PATH", "ideadb.sqlite")
IDEA_CHANNEL: str = os.getenv("IDEA_CHANNEL", "")

# Number of new entries that trigger an automatic idea summary.
# Set to 0 (or leave blank) to disable auto-generation.
try:
    AUTO_IDEA_THRESHOLD: int = int(os.getenv("AUTO_IDEA_THRESHOLD", "0"))
except ValueError:
    AUTO_IDEA_THRESHOLD = 0

# ---------------------------------------------------------------------------
# Validate required env vars up front
# ---------------------------------------------------------------------------
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in the environment / .env file.")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set in the environment / .env file.")

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True          # required to read message text

bot = commands.Bot(command_prefix="!", intents=intents)

db = Database(db_path=DB_PATH)
parser = MetadataParser()
generator = IdeaGenerator(api_key=GROQ_API_KEY)

# Track entries-since-last-auto-idea per guild (in memory; resets on restart)
_new_since_last_idea: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    print(f"✅  IdeaDB is online — logged in as {bot.user} (id={bot.user.id})")
    print(f"    Prefix: !   |   DB: {DB_PATH}")
    print(f"    Auto-idea threshold: {AUTO_IDEA_THRESHOLD or 'disabled'}")


@bot.event
async def on_message(message: discord.Message) -> None:
    # Ignore messages from bots (including ourselves)
    if message.author.bot:
        return

    # Let the command framework handle prefix commands first
    await bot.process_commands(message)

    # Skip if the message was a bot command
    if message.content.startswith(bot.command_prefix):
        return

    # ── Collect & store metadata ─────────────────────────────────────
    parsed = parser.parse_message(message)
    if parsed:
        guild_id = str(message.guild.id) if message.guild else "DM"
        db.store_entry(
            guild_id=guild_id,
            channel_id=str(message.channel.id),
            author=str(message.author),
            content_type=parsed["type"],
            keywords=parsed["keywords"],
            metadata=parsed["metadata"],
            raw_content=parsed["raw_content"],
        )

        # ── Auto-idea trigger ─────────────────────────────────────────
        if AUTO_IDEA_THRESHOLD > 0 and message.guild:
            _new_since_last_idea[guild_id] = (
                _new_since_last_idea.get(guild_id, 0) + 1
            )
            if _new_since_last_idea[guild_id] >= AUTO_IDEA_THRESHOLD:
                _new_since_last_idea[guild_id] = 0
                await _post_auto_ideas(message.guild)


async def _post_auto_ideas(guild: discord.Guild) -> None:
    """Post auto-generated ideas to the designated idea channel (if configured)."""
    channel = None
    if IDEA_CHANNEL:
        # Try to find by name or by ID
        channel = discord.utils.get(guild.text_channels, name=IDEA_CHANNEL)
        if not channel and IDEA_CHANNEL.isdigit():
            channel = guild.get_channel(int(IDEA_CHANNEL))
    if not channel:
        return

    entries = db.get_recent_entries(str(guild.id), limit=200)
    if not entries:
        return

    try:
        ideas = await generator.generate_ideas(entries, count=3)
        embed = discord.Embed(
            title="💡 Auto-Generated Ideas",
            description=ideas,
            color=discord.Color.purple(),
        )
        embed.set_footer(
            text=f"Generated from {len(entries)} collected entries · IdeaDB"
        )
        await channel.send(embed=embed)
    except Exception as exc:
        print(f"[auto-ideas] Failed to generate ideas: {exc}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@bot.command(name="ideas")
async def cmd_ideas(ctx: commands.Context, count: int = 5) -> None:
    """Generate startup / project ideas from collected server data.

    Usage:  !ideas [count]
    Example: !ideas 3
    """
    if count < 1 or count > 10:
        await ctx.send("⚠️  Please specify a count between 1 and 10.")
        return

    guild_id = str(ctx.guild.id) if ctx.guild else "DM"
    entries = db.get_recent_entries(guild_id, limit=200)

    if not entries:
        await ctx.send(
            "❌  No data collected yet. "
            "Start chatting and sharing links / files!"
        )
        return

    thinking = await ctx.send(
        f"🧠  Analyzing **{len(entries)}** collected entries and generating "
        f"**{count}** idea(s) — this may take a few seconds…"
    )

    try:
        ideas = await generator.generate_ideas(entries, count=count)
    except Exception as exc:
        await thinking.edit(content=f"❌  Idea generation failed: {exc}")
        return

    embed = discord.Embed(
        title=f"💡 {count} Project & Startup Idea(s)",
        description=ideas,
        color=discord.Color.blue(),
    )
    embed.set_footer(
        text=f"Based on {len(entries)} entries · model: llama-3.1-8b-instant · IdeaDB"
    )
    await thinking.delete()
    await ctx.send(embed=embed)


@bot.command(name="keywords")
async def cmd_keywords(ctx: commands.Context) -> None:
    """Show the top keywords and topics collected for this server.

    Usage:  !keywords
    """
    guild_id = str(ctx.guild.id) if ctx.guild else "DM"
    top = db.get_top_keywords(guild_id, limit=25)

    if not top:
        await ctx.send("❌  No keywords collected yet.")
        return

    lines = [f"`{kw}` — {cnt}" for kw, cnt in top]
    embed = discord.Embed(
        title="🔑  Top Keywords & Topics",
        description="\n".join(lines),
        color=discord.Color.green(),
    )
    embed.set_footer(text="IdeaDB · keyword frequency across all collected entries")
    await ctx.send(embed=embed)


@bot.command(name="stats")
async def cmd_stats(ctx: commands.Context) -> None:
    """Display collection statistics for this server.

    Usage:  !stats
    """
    guild_id = str(ctx.guild.id) if ctx.guild else "DM"
    stats = db.get_stats(guild_id)

    embed = discord.Embed(
        title="📊  IdeaDB Collection Statistics",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Total Entries",  value=str(stats["total"]),    inline=True)
    embed.add_field(name="💬 Messages",    value=str(stats["messages"]), inline=True)
    embed.add_field(name="📎 Files",       value=str(stats["files"]),    inline=True)
    embed.add_field(name="🔗 Links",       value=str(stats["links"]),    inline=True)
    embed.set_footer(text="IdeaDB")
    await ctx.send(embed=embed)


@bot.command(name="clear")
@commands.has_permissions(administrator=True)
async def cmd_clear(ctx: commands.Context) -> None:
    """(Admin) Clear all collected data for this server.

    Usage:  !clear
    """
    guild_id = str(ctx.guild.id) if ctx.guild else "DM"
    db.clear_guild(guild_id)
    await ctx.send("🗑️  All collected data for this server has been cleared.")


@cmd_clear.error
async def cmd_clear_error(
    ctx: commands.Context, error: commands.CommandError
) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⛔  You need the **Administrator** permission to use this command.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
