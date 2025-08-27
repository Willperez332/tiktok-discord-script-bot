import discord
from discord import app_commands
import os
from dotenv import load_dotenv
import assemblyai as aai

# Import our new function from the other file
from script_formatter import process_tiktok_url, format_script_chunks


# --- Basic Setup ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

# Configure the AssemblyAI SDK with our key
aai.settings.api_key = ASSEMBLYAI_API_KEY

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- Bot Events and Commands ---

@client.event
async def on_ready():
    # This syncs our command with Discord's servers
    await tree.sync()
    print(f'Bot is logged in as {client.user}')
    print('Ready to receive commands!')

@tree.command(name="format", description="Formats a TikTok script from a URL.")
@app_commands.describe(url="The full TikTok video URL.")
async def format_command(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)

    try:
        print(f"Received URL: {url}")
        clean_script = await process_tiktok_url(url)

        if not clean_script or not clean_script.strip():
            await interaction.followup.send("I couldn't find any speech in that video.")
            return

        # Use our new formatter to get the final output string
        formatted_output = format_script_chunks(clean_script)
        
        # Use a Discord Embed for a much cleaner look
        embed = discord.Embed(
            title="Formatted TikTok Script",
            description=formatted_output,
            color=discord.Color.green() # Use a nice color
        )
        embed.add_field(name="Original URL", value=url, inline=False)

        # Send the final, beautiful embed back to the user
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"An error occurred: {e}")
        # Also use an embed for errors
        error_embed = discord.Embed(
            title="An Error Occurred",
            description=f"Sorry, an error occurred while processing the video.\nPlease check the URL and try again.",
            color=discord.color.red()
        )
        error_embed.add_field(name="Error Details", value=f"`{e}`", inline=False)
        await interaction.followup.send(embed=error_embed)

# --- Run the Bot ---
client.run(BOT_TOKEN)