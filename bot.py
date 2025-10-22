import discord
from discord import app_commands
import os
from dotenv import load_dotenv

from script_formatter import process_tiktok_url, format_script_chunks
# --- START OF CHANGE ---
# We now import the ASYNCHRONOUS version of the client
from deepgram import AsyncDeepgramClient
# --- END OF CHANGE ---

# --- Load all our secret keys ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# --- START OF CHANGE ---
# --- Initialize the AsyncDeepgram Client ---
deepgram_client = AsyncDeepgramClient(DEEPGRAM_API_KEY)
# --- END OF CHANGE ---

# --- Standard Bot Setup ---
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync()
    print(f'Bot is logged in as {client.user}')
    print('Ready to receive commands with Async Deepgram engine!')

@tree.command(name="format", description="Formats a TikTok script from a URL using the Deepgram engine.")
@app_commands.describe(url="The full TikTok video URL.")
async def format_command(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)

    try:
        print(f"Received URL: {url}")
        # --- Pass the initialized Async Deepgram client to our processing function ---
        clean_script = await process_tiktok_url(url, deepgram_client)

        if not clean_script or not clean_script.strip():
            await interaction.followup.send("I couldn't find any speech in that video.")
            return

        formatted_output = format_script_chunks(clean_script)
        
        embed = discord.Embed(
            title="Formatted TikTok Script",
            description="The full script is in the code block below for easy copying on mobile.",
            color=discord.Color.green()
        )
        embed.add_field(name="Original URL", value=url, inline=False)
        
        if len(formatted_output) > 1990:
            copyable_script = f"```{formatted_output[:1990]}...```"
        else:
            copyable_script = f"```{formatted_output}```"

        await interaction.followup.send(content=copyable_script, embed=embed)

    except Exception as e:
        print(f"An error occurred: {e}")
        error_embed = discord.Embed(
            title="An Error Occurred",
            description=f"Sorry, an error occurred while processing the video.\nPlease check the URL and try again.",
            color=discord.Color.red()
        )
        error_embed.add_field(name="Error Details", value=f"`{e}`", inline=False)
        await interaction.followup.send(embed=error_embed)

client.run(BOT_TOKEN)