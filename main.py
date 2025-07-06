import io
import os
import sys
import time
import tempfile
import requests
import csv
import re
from pdf2image import convert_from_path
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

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
                "Extract all readable text from this image. Separate the extracted text into two sections with clear headers: 'English_Text:' and 'Khmer_Text:'. Only include text actually found in the image under each section. If a section is empty, just write 'None'.",
                {
                    "data": img_bytes,
                    "mime_type": "image/png"
                }
            ]
            response = self.model.generate_content(prompt)
            print(f"🔍 OCR successful on page {page_number}")
            return response.text
        except Exception as e:
            error_msg = f"[Error processing page {page_number}]: {str(e)}"
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

        # Default to None if not found
        english_text = None
        khmer_text = None

        eng_match = re.search(r"English_Text:(.*?)(Khmer_Text:|$)", cleaned_text, re.DOTALL | re.IGNORECASE)
        khm_match = re.search(r"Khmer_Text:(.*)", cleaned_text, re.DOTALL | re.IGNORECASE)

        if eng_match:
            english_text = eng_match.group(1).strip()
            if english_text.lower() == "none":
                english_text = ""
        if khm_match:
            khmer_text = khm_match.group(1).strip()
            if khmer_text.lower() == "none":
                khmer_text = ""

        return english_text, khmer_text

    def process_multiple_pdfs_to_csv(self, pdf_urls, output_csv="all_results.csv", headers=None):
        all_rows = []
        row_id = 1
        for idx, url in enumerate(pdf_urls, start=1):
            print(f"\n📁 Processing file {idx}/{len(pdf_urls)}: {url}")
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
                    page_text = self.ocr_image(page_img, i)
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
                    time.sleep(1)  # Rate limiting
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
    print("Enter PDF URLs one per line.")
    print("Press Enter on a blank line to start processing.")
    print("Press Enter without typing anything at the start to exit.\n")
    pdf_urls = []
    first_input = input(" > ").strip()
    if first_input == "":
        print("No input received. Exiting application.")
        return []
    if first_input.lower() == "exit":
        print("Exiting application.")
        return []
    if first_input.lower().endswith(".pdf"):
        pdf_urls.append(first_input)
    else:
        print("Invalid URL: must end with .pdf")
    while True:
        line = input("Enter another URL (or press Enter to process): ").strip()
        if line.lower() == "exit":
            print("Exiting application.")
            return []
        if line == "":
            break
        if line.lower().endswith(".pdf"):
            pdf_urls.append(line)
        else:
            print("Invalid URL: must end with .pdf")
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
    while True:
        pdf_urls = collect_pdf_urls()
        if not pdf_urls:
            break
        processor.process_multiple_pdfs_to_csv(
            pdf_urls,
            output_csv="all_results.csv",
            headers=headers
        )
        print("\n✅ Batch processed. Restarting...\n")

# --------------------- Entry Point ---------------------
if __name__ == "__main__":
    main()
