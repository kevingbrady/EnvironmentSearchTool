import re
from subprocess import CalledProcessError

import requests
import os
import spacy
import shutil
import subprocess
import pdfplumber
from pathlib import Path
from bs4 import BeautifulSoup
from jinja2.nodes import Call

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

nlp = spacy.load("en_core_web_sm", disable=["parser"])
nlp.max_length = 3000000

doc_key_pattern = re.compile(
    r'^(?:nistir|sp|ir|fips|nccoe|cswp|etsi|cta|itl|md|rev|r\d+)[-.\s]?\d*'  # Matches document prefixes
    r'|'                                                            # OR
    r'^\d+[-][a-zA-Z0-9-]+$',                                       # Matches compound numbers like 800-53, 140-3
    flags=re.IGNORECASE
)

custom_stop_words = {
    "nist", "publication", "report", "author", "abstract",
    "appendix", "section", "table", "figure", "version", "sp", "ir", "rev",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "mr", "mrs", "ms", "dr", "prof", "sir", "madam", "esq", "jr", "sr", "ar"
}


def tokenizer(text):
    doc = nlp(text)

    tokens = []
    for token in doc:
        token_lowercase = token.lemma_.lower()
        raw_text = token.text.strip().replace(".", "")

        if (
                token.is_alpha
                and len(raw_text) > 1
                and token.ent_type_ != "PERSON"
                and token_lowercase not in custom_stop_words
                and not token.like_email
                and not token.like_url
                and not token.is_stop
                and not token.is_punct
                and not token.is_space
                and not token.like_num
                and not doc_key_pattern.match(raw_text)
        ):
            tokens.append(token_lowercase)

    return tokens


def extract_publication_data(entry):
    try:
        # Mapping to the exact key structure utilized in the dataset schema ("detail_url")
        url = entry.get("detail_url")
        downloaded = False

        if not url:
            print(f"Skipping '{entry['title']}': No 'detail_url' specified.")
            return None, None, None

        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"      Failed to load page. HTTP Status: {response.status_code}")
            return None, None, None

        soup = BeautifulSoup(response.text, "html.parser")

        # pub-header-full-display    doc number                  div
        # pub-title                  doc title                   div
        # pub-authors-container      doc authors list            div
        # pub-detail-abstract-all    doc abstract                div
        # pub-history-container      doc release date block      span

        doc_key = soup.find(id='pub-header-full-display')
        doc_text = ''
        title = soup.find(id='pub-title')
        authors = soup.find(id='pub-authors-container') or soup.find(id='pub-editors-container')
        abstract = soup.find(id='pub-detail-abstract-all') or soup.find(id='pub-detail-abstract-info-full')
        publication_history = soup.find(id='pub-history-container')
        publication_download_link = soup.find(id='pub-local-download-link')  # soup.find(id='pub-doi-link') #or
        doc_key = doc_key.get_text(strip=True)
        title = title.get_text(strip=True) if title else ''
        authors = authors.get_text(strip=True).split(',') if authors else []
        abstract = abstract.get_text(strip=True).replace('Hide full abstract', '') if abstract else ''
        publication_history = publication_history.get_text(strip=True) if publication_history else ''
        publication_download_link = publication_download_link['href'] if hasattr(publication_download_link,
                                                                                 'href') else ''
        actual_local_pdf_path = f'{Path.cwd()}/nist_publications/{doc_key}.pdf' if publication_download_link else ''

        match = re.search(r"(\d{2}/\d{2}/\d{2}):[^(]*\(Final\)", publication_history)
        if match: publication_history = match.group(1)

        if publication_download_link:
            if not os.path.exists(actual_local_pdf_path):
                try:
                    if shutil.which('curl'):
                        cmd = ['curl', '-L', '-s', '-A', headers['User-Agent'], '-o', actual_local_pdf_path,
                               publication_download_link]
                        subprocess.run(cmd, check=True)
                        downloaded = True
                except CalledProcessError as e:
                    pass

            if Path(publication_download_link).suffix.lower() == '.pdf' \
                    and os.path.exists(actual_local_pdf_path):
                with pdfplumber.open(actual_local_pdf_path) as pdf:
                    for page in pdf.pages:
                        if page.extract_text():
                            doc_text += page.extract_text() + '\n'

                    downloaded = True

        # --- STEP 5: Consolidate Existing Index and Scraped Metadata ---
        return doc_key, {
            "title": title,
            "nist_page_url": url,
            "local_pdf_path": actual_local_pdf_path,
            "authors": authors,
            "abstract": abstract,
            "keywords": [],
            "publication_date": publication_history,
            "downloaded": downloaded
        }, doc_text

    except Exception as e:
        print(f"Problem processing url: {url}   {e}")
