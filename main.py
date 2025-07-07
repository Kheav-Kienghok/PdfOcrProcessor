import io
import os
import sys
import time
import tempfile
import requests
import csv
import re
import psutil 
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime
import argparse



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
    def __init__(self, api_key: str, extraction_model: str = "gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self.extraction_model = genai.GenerativeModel(extraction_model)
        self.detection_model = genai.GenerativeModel("models/gemini-2.5-pro")
        print(f"🔧 Initialized Extraction model '{extraction_model}' and Detection model 'gemini-pro'")

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

    def convert_pdf_to_images(self, pdf_path: str, dpi: int = 300, first_page: int = None, last_page: int = None):
        try:
            images = convert_from_path(
                pdf_path,
                dpi=dpi,
                first_page=first_page,
                last_page=last_page
            )
            print(f"✅ Converted PDF '{pdf_path}' to {len(images)} image(s)")
            return images
        except Exception as e:
            print(f"❌ Error converting PDF to images: {e}")
            return []
            
    def detect_languages_in_image(self, image: Image.Image) -> str:
        """Detect if the image contains Khmer, English, both, or none."""
        try:
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()

            prompt = [
                "This image may contain text in English and/or Khmer. Analyze the image and return ONLY one of the following words:\n\n- Khmer\n- English\n- Both\n- None\n\nDo not include anything else in the response.",
                {
                    "data": img_bytes,
                    "mime_type": "image/png"
                }
            ]

            response = self.detection_model.generate_content(prompt)
            detected = response.text.strip().capitalize()
            print(f"🧭 Language detected: {detected}")
            return detected
        except Exception as e:
            print(f"❌ Language detection failed: {e}")
            return "None"


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
            response = self.extraction_model.generate_content(prompt)
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

        # max_lines = max(len(eng_lines), len(khm_lines))
        # for line_num in range(max_lines):
        #     eng = eng_lines[line_num] if line_num < len(eng_lines) else ""
        #     khm = khm_lines[line_num] if line_num < len(khm_lines) else ""
        #     # Skip if both lines are short (≤3 after clean)
        #     if len(eng) <= 3 and len(khm) <= 3:
        #         continue
        #     all_rows.append([row_id, eng, khm])
        #     row_id += 1

        if eng_match:
            raw_eng = eng_match.group(1).strip()
            if raw_eng.lower() != "none":
                english_text = raw_eng

        if khm_match:
            raw_khm = khm_match.group(1).strip()
            if raw_khm.lower() != "none":
                khmer_text = raw_khm

        return english_text, khmer_text

    def save_rows_to_csv(self, rows, output_csv):
        try:
            with open(output_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "English_Text", "Khmer_Text"])
                writer.writerows(rows)
            print(f"\n✅ All results saved to '{output_csv}'")
        except Exception as e:
            print(f"❌ Failed to save OCR output to CSV: {e}")

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

                # Get number of pages in the PDF
                info = pdfinfo_from_path(pdf_path)
                max_pages = info["Pages"]

                if max_pages > 20:
                    print(f"⏩ Skipping '{url}' ({max_pages} pages) — exceeds 20 page limit.")
                    continue  # Skip to next PDF

                for i in range(1, max_pages + 1):

                    # ------------------- RAM CHECK -------------------
                    wait_if_ram_high(threshold=85, wait_time=7) # <--- Add before each page OCR

                    # Convert only the current page to image (not the whole PDF)
                    try:
                        images = self.convert_pdf_to_images(pdf_path, dpi=300, first_page=i, last_page=i)
                        if not images:
                            print(f"❌ Failed to convert page {i} to image.")
                            continue
                        
                        page_img = images[0]

                        try:
                            detected_lang = self.detect_languages_in_image(page_img)

                            if detected_lang not in ["English", "Khmer", "Both"]:
                                print(f"⛔ Skipping page {i} — Detected language: '{detected_lang}'")
                                continue

                            page_text = self.ocr_image(page_img, i)

                        except RuntimeError as quota_error:
                            # Save progress and exit
                            self.save_rows_to_csv(all_rows, output_csv)
                            print("👋 Exiting due to API quota exhaustion. Partial results saved.")
                            return

                    except RuntimeError as quota_error:
                        print(f"⛔ OCR halted: {quota_error}")
                        # Save progress and exit
                        self.save_rows_to_csv(all_rows, output_csv)
                        print("👋 Exiting due to API quota exhaustion. Partial results saved.")
                        return
                    

                    english_text, khmer_text = self.extract_english_khmer(page_text)

                    # Split into lines and clean
                    eng_lines = [clean_line(line) for line in english_text.splitlines() if clean_line(line)]
                    khm_lines = [clean_line(line) for line in khmer_text.splitlines() if clean_line(line)]

                    for eng_line in eng_lines:
                        if len(eng_line) > 3:
                            all_rows.append([row_id, eng_line, ""])
                            row_id += 1

                    for khm_line in khm_lines:
                        if len(khm_line) > 3:
                            all_rows.append([row_id, "", khm_line])
                            row_id += 1

                    # --- Clean up memory ---
                    del page_img
                    import gc; gc.collect()

                    time.sleep(1)  # Still useful for rate limiting

        # Write all to CSV at the end (if not already written due to quota)
        self.save_rows_to_csv(all_rows, output_csv)

# --------------------- Input Handling ---------------------
def collect_pdf_urls():
    pdf_urls = []
    print("Enter PDF URLs (must end with .pdf).")
    print("Press Enter on an empty line to start processing.")
    print("Example: https://mfaic.gov.kh/files/uploads/0YS4PAUIQFCD/សេចក្តីជូនដំណឹង_ស្តីពីកាដេញថ្លៃការផ្គត់ផ្គង់ប្រងឥន្ធនៈ.pdf\n")
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

    parser = argparse.ArgumentParser(
        description="Download PDFs, extract Khmer/English text via Gemini OCR, and save to CSV."
    )

    parser.add_argument(
        "--model",
        type=str,
        default="gemini-1.5-flash",
        choices=["gemini-1.5-flash", "gemini-2.0-flash"],
        help="Specify the Gemini model for OCR extraction."
    )

    args = parser.parse_args()

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

    # Initialize processor with selected model
    processor = PdfOcrProcessor(API_KEY, extraction_model=args.model)

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
