import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

# Função para obter ligação à base de dados
def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

# Função para garantir que as roles existem
def garantir_roles_existem():
    """
    Garante que as roles necessárias existem na base de dados.
    Esta função deve ser chamada sempre que a aplicação inicia.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Verificar se cada role existe individualmente e inserir se necessário
        roles_necessarias = ["user", "account", "admin"]
        
        for role_name in roles_necessarias:
            cursor.execute("SELECT COUNT(*) FROM roles WHERE name = %s", (role_name,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO roles (name) VALUES (%s)", (role_name,))
                print(f"✅ Role '{role_name}' inserida na base de dados.")
        
        conn.commit()
        print("✅ Verificação de roles concluída.")
        
    except Error as e:
        print(f"❌ Erro ao garantir roles: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            if hasattr(conn, "is_connected"):
                if conn.is_connected():
                    conn.close()
            else:
                conn.close()

# Criar estrutura das tabelas
def criar_tabelas():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS allowed_emails (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            role_id INT NOT NULL,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            perfil TEXT,
            tier INT CHECK(tier BETWEEN 1 AND 4) DEFAULT 4,
            keywords TEXT,
            logo LONGBLOB,
            email VARCHAR(255)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS media (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(255),
            url TEXT UNIQUE,
            cliente_id INT NOT NULL,
            tipologia VARCHAR(100),
            segmento VARCHAR(100),
            tier INT CHECK(tier BETWEEN 1 AND 4) DEFAULT 4,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INT AUTO_INCREMENT PRIMARY KEY,
            cliente_id INT NOT NULL,
            media_id INT NOT NULL,
            keyword VARCHAR(255),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (media_id) REFERENCES media(id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp TEXT,
            user_email TEXT,
            action TEXT,
            target TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS noticias_sugeridas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            titulo TEXT,
            url TEXT UNIQUE,
            data TEXT,
            keyword TEXT,
            cliente_id INT,
            site TEXT
        );
        """)

        conn.commit()
        print("✅ Tabelas criadas/verificadas com sucesso.")

        # Garantir que as roles existem após criar as tabelas
        garantir_roles_existem()

    except Error as e:
        print(f"❌ Erro ao criar tabelas: {e}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            if hasattr(conn, "is_connected"):
                if conn.is_connected():
                    conn.close()
            else:
                conn.close()

# Executar criação ao importar
criar_tabelas()
