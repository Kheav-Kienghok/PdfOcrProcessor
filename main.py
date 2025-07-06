import io
import os
import sys
import time
import tempfile
import requests
import csv
import re
import psutil 
from pdf2image import convert_from_path
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime


# -------------- Add RAM Checking Helper ---------------
def wait_if_ram_high(threshold=85, wait_time=5):
    """Pause if RAM usage goes above threshold percentage."""
    while True:
        mem = psutil.virtual_memory()
        if mem.percent >= threshold:
            print(f"⚠️  High RAM usage detected: {mem.percent}%. Pausing for {wait_time}s...")
            time.sleep(wait_time)
        else:
            break

# --------------------- Load API Key ---------------------
load_dotenv()
API_KEY = os.getenv("GENAI_API_KEY")

# --------------------- Cleaning Helper ---------------------
def clean_line(line):
    # Remove leading numbers, bullets, punctuation, and spaces
    return re.sub(r'^[\d\W_]+', '', line).strip()

# --------------------- Processor Class ---------------------
class PdfOcrProcessor:
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        print(f"🔧 Initialized Gemini model '{model_name}'")

    def download_pdf(self, url: str, filename: str, headers: dict = None) -> bool:
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                with open(filename, "wb") as f:
                    f.write(response.content)
                print(f"✅ Downloaded PDF to '{filename}'")
                return True
            else:
                print(f"❌ Failed to download PDF, status code: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Exception during PDF download: {e}")
            return False

    def convert_pdf_to_images(self, pdf_path: str, dpi: int = 300):
        try:
            images = convert_from_path(pdf_path, dpi=dpi)
            print(f"✅ Converted PDF '{pdf_path}' to {len(images)} image(s)")
            return images
        except Exception as e:
            print(f"❌ Error converting PDF to images: {e}")
            return []

    def ocr_image(self, image: Image.Image, page_number: int) -> str:
        try:
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            prompt = [
                "Extract all readable text from this image. Separate the extracted text into two sections with clear headers: 'English_Text:' and 'Khmer_Text:'. Only include text actually found in the image under each section. If a section is empty, just write ' '.",
                {
                    "data": img_bytes,
                    "mime_type": "image/png"
                }
            ]
            response = self.model.generate_content(prompt)
            print(f"🔍 OCR successful on page {page_number}")
            return response.text
        except Exception as e:
            error_text = str(e)
            if "429" in error_text or "quota" in error_text.lower():
                print("❌ Rate limit exceeded — Gemini daily quota reached.")
                print("🔁 Stopping further OCR processing. Try again tomorrow or upgrade your API tier.\n")
                # Raise custom signal or return sentinel value to abort further processing
                raise RuntimeError("Rate limit exceeded. Aborting OCR processing.")
            
            error_msg = f"[Error processing page {page_number}]: {error_text}"
            print(f"❌ {error_msg}")
            return error_msg


    def extract_english_khmer(self, text):
        # Remove boilerplate lines Gemini sometimes returns
        lines = text.splitlines()
        filtered_lines = []
        for line in lines:
            if line.strip().startswith("--- Page"):
                continue
            if "Here's a transcription of the text" in line:
                continue
            filtered_lines.append(line)
        cleaned_text = "\n".join(filtered_lines)

        # Default to empty if not found
        english_text = ""
        khmer_text = ""

        eng_match = re.search(r"English_Text:(.*?)(Khmer_Text:|$)", cleaned_text, re.DOTALL | re.IGNORECASE)
        khm_match = re.search(r"Khmer_Text:(.*)", cleaned_text, re.DOTALL | re.IGNORECASE)

        if eng_match:
            raw_eng = eng_match.group(1).strip()
            if raw_eng.lower() != "none":
                english_text = raw_eng

        if khm_match:
            raw_khm = khm_match.group(1).strip()
            if raw_khm.lower() != "none":
                khmer_text = raw_khm

        return english_text, khmer_text

    def process_multiple_pdfs_to_csv(self, pdf_urls, output_csv=None, headers=None):
        all_rows = []
        row_id = 1

        # Generate output filename if not provided
        if output_csv is None:
            timestamp = datetime.now().strftime("%d_%m_%H%M%S")
            output_dir = "output"
            os.makedirs(output_dir, exist_ok=True)
            output_csv = os.path.join(output_dir, f"scrape_content_{timestamp}.csv")

        for idx, url in enumerate(pdf_urls, start=1):
            print(f"📁 Processing file {idx}/{len(pdf_urls)}: {url}")

            with tempfile.TemporaryDirectory() as temp_dir:
                pdf_path = os.path.join(temp_dir, f"file_{idx}.pdf")
                if not self.download_pdf(url, pdf_path, headers=headers):
                    print(f"Skipping file {idx} due to download failure.")
                    continue

                images = self.convert_pdf_to_images(pdf_path)
                if not images:
                    print("Aborting due to PDF conversion failure.")
                    continue

                for i, page_img in enumerate(images, start=1):

                    # ------------------- RAM CHECK -------------------
                    wait_if_ram_high(threshold=85, wait_time=7) # <--- Add before each page OCR

                    try:
                        page_text = self.ocr_image(page_img, i)
                    except RuntimeError as quota_error:
                        print(f"⛔ OCR halted: {quota_error}")
                        # Immediately write what has been processed so far
                        break  # exits the inner loop, continues to saving
                    

                    english_text, khmer_text = self.extract_english_khmer(page_text)

                    # Split into lines and clean
                    eng_lines = [clean_line(line) for line in english_text.splitlines() if clean_line(line)]
                    khm_lines = [clean_line(line) for line in khmer_text.splitlines() if clean_line(line)]

                    max_lines = max(len(eng_lines), len(khm_lines))
                    for line_num in range(max_lines):
                        eng = eng_lines[line_num] if line_num < len(eng_lines) else ""
                        khm = khm_lines[line_num] if line_num < len(khm_lines) else ""
                        # Skip if both lines are short (≤3 after clean)
                        if len(eng) <= 3 and len(khm) <= 3:
                            continue
                        all_rows.append([row_id, eng, khm])
                        row_id += 1

                    # --- Clean up memory ---
                    del page_img
                    import gc; gc.collect()

                    time.sleep(1)  # Still useful for rate limiting

        # Write all to CSV at the end
        try:
            with open(output_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "English_Text", "Khmer_Text"])
                writer.writerows(all_rows)
            print(f"\n✅ All results saved to '{output_csv}'")
        except Exception as e:
            print(f"❌ Failed to save OCR output to CSV: {e}")

# --------------------- Input Handling ---------------------
def collect_pdf_urls():
    pdf_urls = []
    print("Enter PDF URLs (must end with .pdf).")
    print("Press Enter on an empty line to start processing:\n")

    while True:
        url_input = input("  > ").strip()
        if not url_input:
            print("\nStarting PDF processing...\n")
            break

        if not url_input.lower().endswith(".pdf"):
            print("❌ Invalid URL: must end with .pdf")
            continue

        pdf_urls.append(url_input)

    if not pdf_urls:
        print("No valid PDF URLs provided. Exiting.")
        return []

    return pdf_urls

# --------------------- Main Application ---------------------
def main():
    if not API_KEY:
        print("❌ API key not found. Please set GENAI_API_KEY in your .env file.")
        sys.exit(1)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
    }
    processor = PdfOcrProcessor(API_KEY)

    pdf_urls = collect_pdf_urls()
    if not pdf_urls:
        print("No PDFs to process. Exiting.")
        return
    
    start_time = datetime.now()
    print(f"\n🕒 Started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔗 {len(pdf_urls)} PDF link(s) to process...\n")
        
    processor.process_multiple_pdfs_to_csv(
        pdf_urls,
        headers=headers
    )

    end_time = datetime.now()
    duration_seconds = (end_time - start_time).total_seconds()

    print(f"\n✅ PDF processing complete.")
    print(f"🕓 Finished at {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️ Total processing time: {duration_seconds:.2f} seconds")

# --------------------- Entry Point ---------------------
if __name__ == "__main__":
    main()
