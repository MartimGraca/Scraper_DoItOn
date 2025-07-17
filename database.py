import os
import mysql.connector
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# Conexão unificada: SQLite ou MySQL
def init_connection():
    db_type = os.getenv("DB_TYPE", "sqlite")

    if db_type == "mysql":
        return mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", 3306))
        )
    else:
        return sqlite3.connect(os.getenv("DATABASE_NAME", "database.db"), check_same_thread=False)

conn = init_connection()
cursor = conn.cursor()

# ======== CRIAÇÃO DAS TABELAS (MySQL compatível) ========

# Roles
cursor.execute("""
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) UNIQUE NOT NULL
)
""")

cursor.execute("SELECT COUNT(*) FROM roles")
if cursor.fetchone()[0] == 0:
    cursor.executemany("INSERT INTO roles (name) VALUES (%s)", [
        ("user",),
        ("account",),
        ("admin",)
    ])
    conn.commit()

# Allowed emails
cursor.execute("""
CREATE TABLE IF NOT EXISTS allowed_emails (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    role_id INTEGER NOT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id)
)
""")

# Users
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id)
)
""")

# Clientes
cursor.execute("""
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(255) NOT NULL,
    perfil TEXT,
    tier INTEGER DEFAULT 4,
    keywords TEXT,
    logo LONGBLOB,
    email VARCHAR(255)
)
""")

# Media
cursor.execute("""
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(255),
    url VARCHAR(500) UNIQUE,
    cliente_id INTEGER NOT NULL,
    tipologia VARCHAR(100),
    segmento VARCHAR(100),
    tier INTEGER DEFAULT 4,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
)
""")

# Results
cursor.execute("""
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    cliente_id INTEGER NOT NULL,
    media_id INTEGER NOT NULL,
    keyword VARCHAR(255),
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    FOREIGN KEY (media_id) REFERENCES media(id)
)
""")

# Logs
cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    timestamp TEXT,
    user_email TEXT,
    action TEXT,
    target TEXT
)
""")

# Noticias sugeridas
cursor.execute("""
CREATE TABLE IF NOT EXISTS noticias_sugeridas (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    titulo TEXT,
    url TEXT UNIQUE,
    data TEXT,
    keyword TEXT,
    cliente_id INTEGER,
    site TEXT
)
""")

conn.commit()
print("✅ Base de dados criada com sucesso.")
