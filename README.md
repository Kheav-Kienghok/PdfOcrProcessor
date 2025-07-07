# 📄 PDF Downloader and OCR Extractor

## 🔍 Project Overview

This project automates the extraction of **Khmer** and **English** text from online PDF files using Google's Gemini models.

It uses a **two-model pipeline**:

1. **Detection Stage**  
   A lightweight model (`gemini-2.5-flash` or `gemini-pro`) analyzes each PDF page (as an image) to determine whether it contains **Khmer**, **English**, **Both**, or **neither**.  
   This pre-check helps avoid wasting API quota on irrelevant content (e.g., pages in other languages like Hindi or Thai), conserving usage of the more expensive extraction model.

2. **Extraction Stage**  
   If the page contains Khmer or English, it is passed to a high-accuracy OCR model—`gemini-1.5-flash` or `gemini-2.0-flash`—which extracts and organizes readable text into two clearly labeled sections:
   - `English_Text:`
   - `Khmer_Text:`

To ensure your system remains stable, the script uses `psutil` to monitor memory usage. When RAM usage exceeds a defined threshold, the script automatically pauses to prevent crashes or overload.

Additionally:
- PDFs exceeding a configurable page limit (default: 20 pages) are skipped to preserve system resources.
- Each page is processed **individually**, never loading an entire PDF into memory at once.

> ⚠️ **Note:**  
> `gemini-1.5-flash` and `gemini-2.0-flash` is highly accurate for **Khmer OCR**, but it is limited to **50 requests per day** on the free tier.  
> Using a lightweight detection model helps reserve this limited quota for meaningful content only.


---

## ✅ Features

- 🔗 Download PDFs from user-provided URLs
- 📄 Convert PDF pages to images on-the-fly
- 🤖 Use **Gemini OCR** to extract both **English and Khmer** text
- 📦 Save extracted data into structured CSV format
- 💾 Automatically monitor and manage system RAM
- 🚫 Skip large PDFs that exceed your configured page limit
- 🔄 Process one page at a time to reduce memory usage
- 🖥️ Simple and interactive command-line workflow

---

## 📥 Sample Input (PDF)

[Click here to view the sample PDF](https://mfaic.gov.kh/files/uploads/0YS4PAUIQFCD/សេចក្តីជូនដំណឹង_ស្តីពីកាដេញថ្លៃការផ្គត់ផ្គង់ប្រងឥន្ធនៈ.pdf)

---

## 🧠 Gemini OCR Results (Comparison)

<div align="center">

<table>
  <tr>
    <th style="text-align: center;">Gemini 1.5 Flash</th>
    <th style="text-align: center;">Gemini 2.0 Flash</th>
  </tr>
  <tr>
    <td align="center">
      <img src="images/result-1.5-flash.png" alt="Gemini 1.5 Flash OCR Result" width="300">
    </td>
    <td align="center">
      <img src="images/result-2.0-flash.png" alt="Gemini 2.0 Flash OCR Result" width="300">
    </td>
  </tr>
</table>

</div>

---


## Requirements

- Python 3.12.3 
- [Poppler](https://github.com/oschwartz10612/poppler-windows) (for `pdf2image`; install via system package manager or as described in the pdf2image docs)

---

## Setup

1. **Clone the repository:**
    ```bash
    git clone https://github.com/Kheav-Kienghok/PdfOcrProcessor.git
    cd PdfOcrProcessor
    ```

2. **Install required packages:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Install Poppler:**
    - **Windows:** [Download Poppler binaries](https://github.com/oschwartz10612/poppler-windows/releases/), unzip, and add the `bin` directory to your PATH.
    - **macOS (Homebrew):** `brew install poppler`
    - **Linux (Debian/Ubuntu):** `sudo apt-get install poppler-utils`

4. **Set up your API key:**
    - Create a `.env` file in the project root directory.
    - Add your Gemini API key:
      ```
      GENAI_API_KEY=your_api_key_here
      ```

---

## Usage

Run the script from your project directory:

```bash
python main.py
```

- You will be prompted to enter PDF URLs one by one (must end with `.pdf`).
- When you have entered all your URLs, press **Enter** on an empty line to start processing.
- The extracted text will be saved as a CSV file in the `output/` directory.

### 🔧 Optional Arguments

| Argument    | Description                                                  | Example                              |
|-------------|--------------------------------------------------------------|--------------------------------------|
| `--model`   | Specify Gemini OCR model (`gemini-1.5-flash` or `gemini-2.0-flash`) | `--model gemini-2.0-flash`           |

---

### 📌 Examples

```bash
# Use default model (gemini-1.5-flash)
python main.py

# Use Gemini 2.0 Flash model
python main.py --model gemini-2.0-flash
```

---

## Notes

- By default, PDFs with more than 20 pages are skipped to prevent heavy resource usage.
  - You can change this limit in the script if needed.
- Each page is processed individually for efficiency and safety.
- Make sure you have a valid Gemini API key with enough quota for your intended usage.
