import sqlite3
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

# Conexão com SQLite
sqlite_conn = sqlite3.connect("database.db")
sqlite_cursor = sqlite_conn.cursor()

# Conexão com MySQL
mysql_conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=int(os.getenv("DB_PORT", 3306))
)
mysql_cursor = mysql_conn.cursor()

def migrar_tabela(nome_tabela, colunas):
    sqlite_cursor.execute(f"SELECT {', '.join(colunas)} FROM {nome_tabela}")
    dados = sqlite_cursor.fetchall()
    if not dados:
        print(f"⚠️ Sem dados para {nome_tabela}")
        return
    print(f"🔄 A migrar {len(dados)} registos para {nome_tabela}...")

    placeholders = ", ".join(["%s"] * len(colunas))
    colunas_mysql = ", ".join(colunas)
    insert_sql = f"INSERT IGNORE INTO {nome_tabela} ({colunas_mysql}) VALUES ({placeholders})"
    mysql_cursor.executemany(insert_sql, dados)
    mysql_conn.commit()
    print(f"✅ Tabela {nome_tabela} migrada com sucesso.")

# Listar tabelas e colunas manualmente
tabelas = {
    "roles": ["id", "name"],
    "allowed_emails": ["id", "email", "role_id"],
    "users": ["id", "username", "email", "password_hash", "role_id", "created_at"],
    "clientes": ["id", "nome", "perfil", "tier", "keywords", "logo", "email"],
    "media": ["id", "nome", "url", "cliente_id", "tipologia", "segmento", "tier"],
    "results": ["id", "cliente_id", "media_id", "keyword"],
    "logs": ["id", "timestamp", "user_email", "action", "target"],
    "noticias_sugeridas": ["id", "titulo", "url", "data", "keyword", "cliente_id", "site"]
}

for tabela, colunas in tabelas.items():
    try:
        migrar_tabela(tabela, colunas)
    except Exception as e:
        print(f"❌ Erro ao migrar {tabela}: {e}")

sqlite_conn.close()
mysql_conn.close()
print(" Migração finalizada.")
