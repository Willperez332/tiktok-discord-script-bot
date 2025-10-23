import discord
from discord import app_commands
import os
from dotenv import load_dotenv

from script_formatter import process_tiktok_url, format_script_chunks
from deepgram import AsyncDeepgramClient

load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Initialize async Deepgram client once
deepgram_client = AsyncDeepgramClient(DEEPGRAM_API_KEY)

@tree.command(name="format", description="Transcribe a TikTok and format it for Veo 3.")
@app_commands.describe(url="TikTok URL")
async def format_command(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)

    try:
        clean_script = await process_tiktok_url(url, deepgram_client)
        if not clean_script:
            await interaction.followup.send("I couldn't find any speech in that video.")
            return

        formatted = format_script_chunks(clean_script)

        # --- Embed for presentation ---
        embed = discord.Embed(
            title="Formatted TikTok Script",
            description="Below is a copyable version (as code blocks).",
            color=discord.Color.green()
        )
        embed.add_field(name="Original URL", value=url, inline=False)
        await interaction.followup.send(embed=embed)

        # --- Copyable code blocks for mobile ---
        # Discord message hard limit is 2000 chars.
        # We split into ~1900 to leave room for code fences.
        def chunks(s: str, size: int = 1900):
            for i in range(0, len(s), size):
                yield s[i:i+size]

        if not formatted.strip():
            await interaction.followup.send("No formatted text produced.")
            return

        for piece in chunks(formatted):
            # Wrap each chunk in a code block for easy long-press/copy on mobile
            await interaction.followup.send(f"```text\n{piece}\n```")

    except Exception as e:
        error_embed = discord.Embed(
            title="An Error Occurred",
            description="Sorry, something went wrong while processing the video.",
            color=discord.Color.red()
        )
        error_embed.add_field(name="Details", value=f"`{e}`", inline=False)
        await interaction.followup.send(embed=error_embed)

@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")

client.run(BOT_TOKEN)