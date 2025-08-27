import discord
import os
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Set up the bot
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# This function runs when the bot is online and ready
@client.event
async def on_ready():
    print(f'Bot is logged in as {client.user}')
    print('Ready to format some scripts!')

# Run the bot
client.run(BOT_TOKEN)