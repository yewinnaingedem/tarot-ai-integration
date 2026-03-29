import mysql.connector.pooling
import os
from dotenv import load_dotenv

load_dotenv()

_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="tarot_pool",
    pool_size=5,
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USERNAME", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_DATABASE", "tarot_db"),
    port=int(os.getenv("DB_PORT", "3306")),
)

def get_connection():
    return _pool.get_connection()