import os
from pymongo import MongoClient

client = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=3000)
db = client.get_default_database()