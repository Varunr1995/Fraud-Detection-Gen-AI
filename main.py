import os
import sqlite3
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils import extract_text_from_image, extract_amount, extract_date, extract_city

# === Load environment variables ===
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# === SQLite DB Setup ===
conn = sqlite3.connect('receipts.db')
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    date TEXT NOT NULL,
    city TEXT NOT NULL,
    image_path TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# === Discord Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"\U0001F916 Bot is ready. Logged in as {bot.user}")


@bot.command(name="upload")
async def upload_receipt(ctx):
    await ctx.send("\ud83d\udcce Please upload your receipt image(s) (JPG/JPEG). You can upload multiple.")


@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot:
        return

    if bot.user.mentioned_in(message):
        await message.channel.send("\ud83d\udc4b Need to verify a receipt? Use `!upload`.")

    if message.attachments:
        for att in message.attachments:
            if not att.filename.lower().endswith((".jpg", ".jpeg")):
                continue

            await message.channel.send(f"\ud83d\udcc5 Processing **{att.filename}**...")
            path = f"temp_{att.filename}"
            await att.save(path)

            try:
                text = extract_text_from_image(path)
                print("\n===== OCR TEXT =====\n", text, "\n===================\n")

                amount = extract_amount(text)
                date = extract_date(text)
                city = extract_city(text)

                if not all([amount, date, city]):
                    missing = []
                    if not amount: missing.append("amount")
                    if not date: missing.append("date")
                    if not city: missing.append("city")
                    await message.channel.send(f"\u274c Could not extract: {', '.join(missing)}")
                    continue

                await message.channel.send(
                    f"\ud83d\udcc4 **{att.filename}** — Verified \u2705\n"
                    f"- Amount: {amount}\n"
                    f"- Date: {date}\n"
                    f"- City: {city}"
                )

                cursor.execute(
                    "INSERT INTO receipts (user_id, amount, date, city, image_path) VALUES (?,?,?,?,?)",
                    (str(message.author.id), amount, date, city, path)
                )
                conn.commit()
                await message.channel.send("\u2705 Receipt saved to local database!")

            except Exception as e:
                await message.channel.send(f"\u274c Error: {e}")

            finally:
                if os.path.exists(path):
                    os.remove(path)


bot.run(DISCORD_BOT_TOKEN)