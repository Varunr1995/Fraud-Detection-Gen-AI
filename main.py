import discord
from discord.ext import commands
from PIL import Image
import pytesseract
import os
import re
import spacy
import requests
from dotenv import load_dotenv
from transformers import pipeline

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Tesseract configuration
pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"

# NLP models
nlp = spacy.load("en_core_web_sm")
ner = pipeline("ner", model="dslim/bert-base-NER", grouped_entities=True)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def is_valid_city(name):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": name, "format": "json", "limit": 1},
            headers={"User-Agent": "receipt-bot"},
            timeout=5
        )
        data = resp.json()
        if data and data[0].get("type", "") in ("city", "town", "village"):
            return True
    except Exception:
        pass
    return False


def extract_city_name(txt):
    # Hugging Face NER candidates
    for ent in ner(txt):
        if ent.get('entity_group') in ('LOC', 'GPE'):
            candidate = ent.get('word')
            if is_valid_city(candidate):
                return candidate
    # spaCy fallback
    for ent in nlp(txt).ents:
        if ent.label_ == 'GPE' and is_valid_city(ent.text):
            return ent.text
    return None


def extract_fields(txt):
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    # Amount extraction: last 'Total' line
    amount = None
    for line in reversed(lines):
        if re.search(r"\bTotal\b", line, re.I):
            m = re.search(r"([\d,]+(?:\.\d{2})?)", line)
            if m:
                amount = m.group(1).replace(",", "")
            break
    # Fallback: search for rupee or Rs
    if not amount:
        for line in reversed(lines):
            m2 = re.search(r"(?:₹|Rs\.?)+\s*([\d,]+(?:\.\d{2})?)", line)
            if m2:
                amount = m2.group(1).replace(",", "")
                break
    # Fallback: first generic number
    if not amount:
        m3 = re.search(r"([\d,]+(?:\.\d{2})?)", txt)
        if m3:
            amount = m3.group(1).replace(",", "")
    # Date extraction
    date = None
    d = re.search(r"delivered on\s*([A-Za-z]+\s*\d{1,2},\s*\d{1,2}:\d{2}\s*[AP]M)", txt, re.I)
    if d:
        date = d.group(1)
    else:
        d2 = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b", txt)
        if d2:
            date = d2.group(1)
    # City extraction
    city = extract_city_name(txt)
    return {"amount": amount, "date": date, "city": city}


@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")


@bot.command(name="upload")
async def upload_receipt(ctx):
    await ctx.send(
        "📎 Please upload your receipt image(s) (JPG or JPEG format). Up to multiple images allowed."
    )


@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot:
        return
    if bot.user.mentioned_in(message):
        await message.channel.send("👋 Mentioned me? Use `!upload` to process receipts.")
    if message.attachments:
        processed = False
        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".jpg", ".jpeg")):
                await message.channel.send(f"📥 Processing **{attachment.filename}**...")
                path = f"temp_{attachment.filename}"
                await attachment.save(path)
                try:
                    text = pytesseract.image_to_string(Image.open(path))
                    fields = extract_fields(text)
                    if not fields['amount']:
                        await message.channel.send("❌ Could not extract amount. Please upload a valid receipt.")
                        continue
                    if not fields['date']:
                        await message.channel.send("❌ Could not extract date. Please upload a valid receipt.")
                        continue
                    if not fields['city']:
                        await message.channel.send("❌ Could not extract city. Please upload a valid receipt.")
                        continue
                    status = "Genuine"
                    await message.channel.send(
                        f"🧾 **{attachment.filename}** — Status: **{status}**\n"
                        f"\n**Extracted Fields:**\n"
                        f"- Amount: {fields['amount']}\n"
                        f"- Date: {fields['date']}\n"
                        f"- City: {fields['city']}"
                    )
                    processed = True
                except Exception as e:
                    await message.channel.send(f"❌ Error processing **{attachment.filename}**: {e}")
                finally:
                    if os.path.exists(path):
                        os.remove(path)
        if processed:
            # Collect additional details
            prompts = ["Employee ID", "Expense Amount", "Date (e.g. April 18, 4:12 PM)", "City"]
            responses = {}
            for i, label in enumerate(prompts, 1):
                await message.channel.send(f"{i}. {label} (or type 'Cancel' to abort):")
                resp = await bot.wait_for('message', check=lambda m: m.author == message.author)
                if resp.content.strip().lower() == 'cancel':
                    await message.channel.send("🚫 Cancelled. Type `!upload` to restart.")
                    return
                responses[label] = resp.content.strip()
            await message.channel.send("✅ Data saved (mock). You can integrate DB next.")


bot.run(DISCORD_BOT_TOKEN)
