import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection() :
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USERNAME", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_DATABASE", "tarot_db"),
        port=int(os.getenv("DB_PORT", "3306")),  
    )