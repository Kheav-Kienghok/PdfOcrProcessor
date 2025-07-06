# PDF Downloader and OCR Extractor

## Project Description

This project automates the extraction of text from online PDF files.  
It collects URLs ending with `.pdf`, downloads the PDFs to your local machine, and converts each page to images. The images are then sent to the Gemini API for OCR (Optical Character Recognition) using a specific prompt to receive the extracted data in a structured format. The final results are saved into a CSV file for easy access and analysis.

To ensure your computer remains stable during large processing jobs, the project uses `psutil` to monitor memory usage. If RAM usage becomes too high, the process will automatically pause, clear up memory, and then continue, helping to prevent your machine from being killed due to excessive resource usage.

## Setup

1. **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

2. **Install required packages:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Set up your API key:**
    - Create a `.env` file in the project root directory.
    - Add your Gemini API key:
      ```
      GENAI_API_KEY=your_api_key_here
      ```

4. **Run the script:**

    ```bash
    python main.py
    ```

You will be prompted to enter PDF URLs one by one. When done, press Enter on an empty line.
