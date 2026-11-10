from pydantic_settings import BaseSettings
from pymongo import AsyncMongoClient
from pathlib import Path
from typing import List, Any
import os
import json

class Settings(BaseSettings):
    mongodb_uri: str = os.getenv('MONGODB_URI', "mongodb://localhost:27017")
    db_name: str = "StandardsSearchDB"
    collection_name: str = "Standards"

    def __init__(self, **values: Any):
        super().__init__(**values)

    async def load_database_from_json(self):
        client = AsyncMongoClient(self.mongodb_uri)
        db = client[self.db_name]
        collection = db[self.collection_name]

        count = await collection.count_documents({})
        if count == 0:
            json_data_filepath = Path.cwd() / "data" / "nist_publications.json"
            if os.path.exists(json_data_filepath):
                with open(json_data_filepath, "r", encoding="utf-8") as json_file:
                    raw_data = json.load(json_file)

                    documents = []
                    for key, data in raw_data.items():
                        data["doc_key"] = key
                        documents.append(data)

                    if documents:
                        await collection.insert_many(documents)

        await client.close()


