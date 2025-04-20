# App ID: 1363217653938000053
# Public Key: 445a53fb368e3a11b5eda2627472d39af7922572a5af0608124c523a4b77451c
 
import os
import re
import sqlite3
import discord
from discord.ext import commands
from PIL import Image
import pytesseract
from pytesseract import TesseractNotFoundError
import spacy
from transformers import pipeline
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Configure Tesseract
pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"

# Initialize spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import spacy.cli
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# Initialize NER pipeline
ner = pipeline("ner", model="dslim/bert-base-NER", grouped_entities=True)

# Initialize SQLite database
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

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")

@bot.command(name="upload")
async def upload_receipt(ctx):
    await ctx.send("📎 Please upload your receipt image(s) (JPG/JPEG). You can upload multiple.")

@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot:
        return
    if bot.user.mentioned_in(message):
        await message.channel.send("👋 Need to verify a receipt? Use `!upload`.")
    if message.attachments:
        for att in message.attachments:
            if not att.filename.lower().endswith((".jpg", ".jpeg")):
                continue
            await message.channel.send(f"📥 Processing **{att.filename}**...")
            path = f"temp_{att.filename}"
            await att.save(path)
            try:
                # OCR extraction
                try:
                    text = pytesseract.image_to_string(Image.open(path))
                except TesseractNotFoundError:
                    await message.channel.send(
                        "❌ Tesseract OCR not found. Install via `brew install tesseract`."
                    )
                    continue

                # Extract amount: digits immediately following 'Bill Total'
                amount = None
                for line in text.splitlines():
                    if re.search(r"Bill\s*Total", line, re.IGNORECASE):
                        # take substring after 'Bill Total'
                        snippet = line.split('Bill Total', 1)[1]
                        # remove non-digit except dot
                        amt = re.sub(r"[^0-9.]", "", snippet)
                        if amt:
                            amount = amt
                        break
                if not amount:
                    await message.channel.send(
                        "❌ Could not extract amount. Upload a valid receipt."
                    )
                    continue

                # Extract date
                date = None
                d = re.search(
                    r"delivered on\s*([A-Za-z]+\s*\d{1,2},\s*\d{1,2}:\d{2}\s*[AP]M)",
                    text,
                    re.IGNORECASE
                )
                if d:
                    date = d.group(1)
                else:
                    d2 = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b", text)
                    if d2:
                        date = d2.group(1)
                if not date:
                    await message.channel.send(
                        "❌ Could not extract date. Upload a valid receipt."
                    )
                    continue

                # Extract city via NER
                city = None
                for ent in ner(text):
                    if ent['entity_group'] in ('LOC', 'GPE'):
                        city = ent['word']
                        break
                if not city:
                    for ent in nlp(text).ents:
                        if ent.label_ == 'GPE':
                            city = ent.text
                            break
                if not city:
                    await message.channel.send(
                        "❌ Could not extract city. Upload a valid receipt."
                    )
                    continue

                # Show extracted values
                await message.channel.send(
                    f"🧾 **{att.filename}** — Genuine\n"
                    f"- Amount: {amount}\n"
                    f"- Date: {date}\n"
                    f"- City: {city}"
                )

                # Save to SQLite
                cursor.execute(
                    "INSERT INTO receipts (user_id, amount, date, city, image_path) VALUES (?,?,?,?,?)",
                    (str(message.author.id), amount, date, city, path)
                )
                conn.commit()
                await message.channel.send("✅ Saved to local database!")

            except Exception as e:
                await message.channel.send(f"❌ Error: {e}")
            finally:
                if os.path.exists(path):
                    os.remove(path)

bot.run(DISCORD_BOT_TOKEN)
