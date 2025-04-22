import re
import os
import asyncio
import requests
from typing import Optional
from PIL import Image
from dotenv import load_dotenv
import pytesseract
import torch
import spacy
from transformers import (
    TrOCRProcessor, VisionEncoderDecoderModel,
    AutoTokenizer, AutoModelForCausalLM, pipeline
)

# Load .env
load_dotenv()
HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN")

# OCR model
processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-printed")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-printed")

# spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import spacy.cli
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# Transformers NER
ner = pipeline("ner", model="dslim/bert-base-NER", aggregation_strategy="simple")

# LLaMA 3.2 1B model
_llama_tokenizer = None
_llama_model = None

def get_llama_model():
    global _llama_tokenizer, _llama_model
    if _llama_tokenizer is None or _llama_model is None:
        model_id = "meta-llama/Llama-3.2-1B"
        _llama_tokenizer = AutoTokenizer.from_pretrained(model_id, use_auth_token=HF_TOKEN)
        _llama_model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=torch.float32, use_auth_token=HF_TOKEN
        ).to("cpu")
    return _llama_tokenizer, _llama_model

# OCR function
def extract_text_from_image(image_path: str) -> str:
    try:
        image = Image.open(image_path).convert("RGB")
        pixel_values = processor(images=image, return_tensors="pt").pixel_values
        generated_ids = model.generate(pixel_values)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return text if len(text.strip()) > 10 else pytesseract.image_to_string(image)
    except Exception as e:
        print(f"[Fallback OCR] TrOCR failed: {e}")
        return pytesseract.image_to_string(Image.open(image_path))

# Field extractors
def extract_amount(text: str) -> Optional[str]:
    match = re.search(r"Bill\s*Total[^\d₹$]*[₹$]?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(",", "").strip()
    candidates = re.findall(r"(?:rs\.?|₹|\$)?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?", text)
    if candidates:
        try:
            return max(candidates, key=lambda x: float(x.replace(",", "").replace("₹", "").strip()))
        except ValueError:
            return None
    return None

def extract_date(text: str) -> Optional[str]:
    date_patterns = [
        r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b",
        r"\b(\d{2}\s*[A-Za-z]{3,9}\s*\d{4})\b",
        r"\b([A-Za-z]{3,9}\s*\d{1,2},?\s*\d{4})\b"
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None

def get_city_from_pincode(pincode: str) -> Optional[str]:
    try:
        res = requests.get(f"https://api.postalpincode.in/pincode/{pincode}", timeout=5)
        data = res.json()
        if data and data[0]["Status"] == "Success":
            return data[0]["PostOffice"][0]["District"]
    except Exception:
        return None
    return None

def extract_city(text: str) -> Optional[str]:
    match = re.search(r"\b\d{6}\b", text)
    if match:
        city = get_city_from_pincode(match.group(0))
        if city:
            return city
    for ent in ner(text):
        if ent['entity_group'] in ("LOC", "GPE"):
            return ent["word"]
    for ent in nlp(text).ents:
        if ent.label_ == "GPE":
            return ent.text
    return None

# === Async-safe LLM ===
def _sync_llm_generate(prompt: str, max_tokens: int = 200) -> str:
    tokenizer, model = get_llama_model()
    inputs = tokenizer(prompt, return_tensors="pt").to("cpu")
    outputs = model.generate(**inputs, max_new_tokens=max_tokens)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

async def generate_summary_with_qwen(receipt_text: str) -> str:
    loop = asyncio.get_event_loop()
    prompt = f"Summarize this receipt:\n{receipt_text}"
    return await loop.run_in_executor(None, _sync_llm_generate, prompt, 150)

async def generate_json_from_receipt(receipt_text: str) -> str:
    loop = asyncio.get_event_loop()
    prompt = f"""Extract structured JSON from this receipt:\n{receipt_text}\nFormat:
{{
  "amount": "",
  "date": "",
  "city": ""
}}"""
    return await loop.run_in_executor(None, _sync_llm_generate, prompt, 200)

async def generate_llm_answer(question: str, receipt_text: str) -> str:
    loop = asyncio.get_event_loop()
    prompt = f"Receipt:\n{receipt_text}\n\nQuestion:\n{question}"
    return await loop.run_in_executor(None, _sync_llm_generate, prompt, 200)
