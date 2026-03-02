from fastmcp import FastMCP
from dotenv import load_dotenv
import os

load_dotenv()

mcp = FastMCP(name= os.getenv("PROJECT_NAME"))