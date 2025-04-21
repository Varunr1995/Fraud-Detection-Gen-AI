import re
from typing import Optional
import requests
from PIL import Image
from transformers import TrOCRProcessor, VisionEncoderDecoderModel, pipeline
import pytesseract
import torch
import spacy

# === Load OCR Models ===
processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-printed")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-printed")

# === Load spaCy NER ===
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import spacy.cli
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# === Load Transformers-based NER model ===
ner = pipeline("ner", model="dslim/bert-base-NER", grouped_entities=True)

def extract_text_from_image(image_path: str) -> str:
    try:
        image = Image.open(image_path).convert("RGB")
        pixel_values = processor(images=image, return_tensors="pt").pixel_values
        generated_ids = model.generate(pixel_values)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        if len(text.strip()) > 10:
            print("[TrOCR Output]\n", text)
            return text
        else:
            raise ValueError("Empty or insufficient TrOCR output")
    except Exception as e:
        print(f"[⚠️] TrOCR failed, falling back to Tesseract: {e}")
        fallback_text = pytesseract.image_to_string(Image.open(image_path))
        print("[Tesseract Output]\n", fallback_text)
        return fallback_text

def extract_amount(text: str) -> Optional[str]:
    print("[Amount Extraction]\nRaw Text:", text)
    match = re.search(r"Bill\s*Total[^\u20B9\d]*\u20B9?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", text, re.IGNORECASE)
    if match:
        print("Regex Match (Bill Total):", match.group(0))
        return match.group(1).replace(",", "").strip()

    pattern = r"(?:rs\.?|\u20B9|\$)?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"
    candidates = re.findall(pattern, text)
    print("Amount Candidates:", candidates)
    if candidates:
        try:
            return max(candidates, key=lambda x: float(x.replace(",", "").replace("\u20B9", "").strip()))
        except ValueError:
            return None
    return None

def extract_date(text: str) -> Optional[str]:
    print("[Date Extraction]\nRaw Text:", text)
    match = re.search(r"Order delivered on\s+([A-Za-z]+\s+\d{1,2}(?:,\s*\d{1,2}:\d{2}\s*[APMapm]+)?)", text)
    if match:
        print("Regex Match (Delivery Date):", match.group(0))
        return match.group(1).strip()

    date_patterns = [
        r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b",
        r"\b(\d{2}\s*[A-Za-z]{3,9}\s*\d{4})\b",
        r"\b([A-Za-z]{3,9}\s*\d{1,2},?\s*\d{4})\b"
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            print("Regex Match (Alt Date):", match.group(0))
            return match.group(1)
    return None

def get_city_from_pincode(pincode: str) -> Optional[str]:
    try:
        url = f"https://api.postalpincode.in/pincode/{pincode}"
        response = requests.get(url, timeout=5)
        data = response.json()
        if data and data[0]["Status"] == "Success":
            return data[0]["PostOffice"][0]["District"]
    except Exception as e:
        print(f"[❌] Error fetching city from pincode {pincode}: {e}")
    return None

def extract_city(text: str) -> Optional[str]:
    print("[City Extraction]\nRaw Text:", text)
    pincode_match = re.search(r"\b\d{6}\b", text)
    if pincode_match:
        print("Pincode Match:", pincode_match.group(0))
        city = get_city_from_pincode(pincode_match.group(0))
        if city:
            print("City from pincode:", city)
            return city

    for ent in ner(text):
        if ent['entity_group'] in ('LOC', 'GPE'):
            print("NER Match (transformers):", ent['word'])
            return ent['word']
    for ent in nlp(text).ents:
        if ent.label_ == 'GPE':
            print("NER Match (spaCy):", ent.text)
            return ent.text

    return None
