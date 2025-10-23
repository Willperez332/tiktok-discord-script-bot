import os
import asyncio
import discord
from discord import app_commands
from dotenv import load_dotenv

from deepgram import DeepgramClient
from script_formatter import process_tiktok_url, format_script_chunks

load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# single shared client (works with v3 and v4 SDKs)
deepgram_client = DeepgramClient(DEEPGRAM_API_KEY)


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

        # 1) Nice embed
        embed = discord.Embed(
            title="Formatted TikTok Script",
            description="A copyable version follows below as code blocks.",
            color=discord.Color.green()
        )
        embed.add_field(name="Original URL", value=url, inline=False)
        await interaction.followup.send(embed=embed)

        # 2) Mobile-copyable code blocks (split under 2000 char per msg)
        def split_chunks(s: str, limit: int = 1900):
            for i in range(0, len(s), limit):
                yield s[i:i+limit]

        if not formatted.strip():
            await interaction.followup.send("No formatted text produced.")
            return

        for piece in split_chunks(formatted):
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


if __name__ == "__main__":
    if not BOT_TOKEN or not DEEPGRAM_API_KEY:
        raise SystemExit("Missing DISCORD_BOT_TOKEN or DEEPGRAM_API_KEY")
    client.run(BOT_TOKEN)