import sqlite3
import os

# Caminho do ficheiro
db_path = "database.db"





# Criar nova base de dados
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Tabela de roles
cursor.execute("""
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
)
""")

# Inicialização de roles se não existirem
cursor.execute("SELECT COUNT(*) FROM roles")
if cursor.fetchone()[0] == 0:
    cursor.executemany("INSERT INTO roles (name) VALUES (?)", [
        ("user",),
        ("account",),
        ("admin",)
    ])
    conn.commit()


# Emails permitidos para registo
cursor.execute("""
CREATE TABLE IF NOT EXISTS allowed_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    role_id INTEGER NOT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id)
)
""")

# Tabela de utilizadores
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id)
)
""")
#cursor.execute("DELETE FROM users")
#print("❌ Todos os utilizadores foram apagados.")

# Tabela de clientes
cursor.execute("""
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    perfil TEXT,
    tier INTEGER CHECK(tier BETWEEN 1 AND 4) DEFAULT 4,
    keywords TEXT,
    logo BLOB,
    email TEXT
)
""")

# Tabela de media
cursor.execute("""
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    url TEXT UNIQUE,
    cliente_id INTEGER NOT NULL,
    tipologia TEXT,
    segmento TEXT,
    tier INTENGER CHECK(tier BETWEEN 1 AND 4) DEFAULT 4,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
)
""")

# Tabela de resultados
cursor.execute("""
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    media_id INTEGER NOT NULL,
    keyword TEXT,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    FOREIGN KEY (media_id) REFERENCES media(id)
)
""")

cursor.execute(""" CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    user_email TEXT,
    action TEXT,
    target TEXT
);
""")


cursor.execute("""CREATE TABLE IF NOT EXISTS noticias_sugeridas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT,
    url TEXT UNIQUE,
    data TEXT,
    keyword TEXT,
    cliente_id INTEGER,
    site TEXT
);
""")


conn.commit()
conn.close()
print("✅ Base de dados criada com sucesso.")
