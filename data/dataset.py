import os
import json
import warnings
import logging
from pathlib import Path
from huggingface_hub import hf_hub_download, login
from concurrent.futures import ProcessPoolExecutor, as_completed
from sklearn.feature_extraction.text import TfidfVectorizer
from utils import extract_publication_data, tokenizer

warnings.filterwarnings("ignore", category=UserWarning, module="pypdf")
logging.getLogger("pypdf").setLevel(logging.ERROR)

if __name__ == '__main__':

    hugging_face_api_token = Path.home() / "huggingface_api_token.txt"
    login(token=hugging_face_api_token.read_text().strip())

    # 1. Download ONLY the metadata.json index from Hugging Face
    print("Downloading index file metadata.json from Hugging Face...")
    metadata_path = hf_hub_download(
        repo_id="ethanolivertroy/nist-publications-raw",
        filename="metadata.json",
        repo_type="dataset"
    )

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    os.makedirs('nist_publications', exist_ok=True)

    nist_publications = {}
    futures = []
    ordered_keys = []
    pdf_texts = []

    with ProcessPoolExecutor() as pool:

        for entry in metadata:
            futures.append(pool.submit(extract_publication_data, entry))

        for future in as_completed(futures):
            pub_key, pub_data, pub_text = future.result()

            if pub_key and pub_data:
                nist_publications[pub_key] = pub_data
                ordered_keys.append(pub_key)
                pdf_texts.append(pub_text)


    vectorizer = TfidfVectorizer(
        max_df=0.85,
        min_df=0.03,
        tokenizer=tokenizer,
        token_pattern=None
    )
    tfidf_matrix = vectorizer.fit_transform(pdf_texts)
    feature_names = vectorizer.get_feature_names_out()
    num_keywords = 40

    for idx, key in enumerate(ordered_keys):
        row = tfidf_matrix[idx]
        keywords = []

        if len(row.data) > 0:
            top_local_indices = row.data.argsort()[-num_keywords:][::-1]
            global_feature_ids = row.indices[top_local_indices]
            keywords = [feature_names[i] for i in global_feature_ids]

        nist_publications[key]['keywords'] = keywords
        print(f"[{idx + 1}/{len(metadata)}] Completed: {key}")


    # --- STEP 6: Write to Output ---
    output_filename = "nist_publications.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(nist_publications, f, indent=4, ensure_ascii=False)
