import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import time

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

# Função para verificar se uma tabela existe
def tabela_existe(cursor, nome_tabela):
    """
    Verifica se uma tabela existe na base de dados.
    """
    cursor.execute("SHOW TABLES LIKE %s", (nome_tabela,))
    return cursor.fetchone() is not None

# Criar estrutura das tabelas
def criar_tabelas():
    conn = None
    cursor = None
    max_tentativas = 3
    tentativa = 0
    
    while tentativa < max_tentativas:
        try:
            print(f"🔄 Tentativa {tentativa + 1} de {max_tentativas} para criar tabelas...")
            conn = get_connection()
            cursor = conn.cursor()

            # Lista de tabelas e suas definições SQL
            tabelas = {
                "roles": """
                CREATE TABLE IF NOT EXISTS roles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(50) UNIQUE NOT NULL
                );
                """,
                "allowed_emails": """
                CREATE TABLE IF NOT EXISTS allowed_emails (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    role_id INT NOT NULL,
                    FOREIGN KEY (role_id) REFERENCES roles(id)
                );
                """,
                "users": """
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (role_id) REFERENCES roles(id)
                );
                """,
                "clientes": """
                CREATE TABLE IF NOT EXISTS clientes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nome VARCHAR(255) NOT NULL,
                    perfil TEXT,
                    tier INT CHECK(tier BETWEEN 1 AND 4) DEFAULT 4,
                    keywords TEXT,
                    logo LONGBLOB,
                    email VARCHAR(255)
                );
                """,
                "media": """
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
                """,
                "results": """
                CREATE TABLE IF NOT EXISTS results (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    cliente_id INT NOT NULL,
                    media_id INT NOT NULL,
                    keyword VARCHAR(255),
                    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                    FOREIGN KEY (media_id) REFERENCES media(id)
                );
                """,
                "logs": """
                CREATE TABLE IF NOT EXISTS logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp TEXT,
                    user_email TEXT,
                    action TEXT,
                    target TEXT
                );
                """,
                "noticias_sugeridas": """
                CREATE TABLE IF NOT EXISTS noticias_sugeridas (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    titulo TEXT,
                    url TEXT UNIQUE,
                    data TEXT,
                    keyword TEXT,
                    cliente_id INT,
                    site TEXT
                );
                """
            }

            # Criar cada tabela individualmente
            for nome_tabela, sql in tabelas.items():
                try:
                    cursor.execute(sql)
                    print(f"✅ Tabela '{nome_tabela}' criada/verificada.")
                except Error as e:
                    print(f"❌ Erro ao criar tabela '{nome_tabela}': {e}")
                    raise e

            conn.commit()
            print("✅ Todas as tabelas criadas/verificadas com sucesso.")

            # Verificar se todas as tabelas foram realmente criadas
            tabelas_criadas = []
            for nome_tabela in tabelas.keys():
                if tabela_existe(cursor, nome_tabela):
                    tabelas_criadas.append(nome_tabela)
                else:
                    print(f"⚠️ Tabela '{nome_tabela}' não foi encontrada após criação.")

            print(f"📋 Tabelas confirmadas na base de dados: {', '.join(tabelas_criadas)}")

            # Garantir que as roles existem após criar as tabelas
            if "roles" in tabelas_criadas:
                garantir_roles_existem()
            
            # Se chegou até aqui, sucesso!
            break

        except Error as e:
            tentativa += 1
            print(f"❌ Erro na tentativa {tentativa}: {e}")
            if tentativa < max_tentativas:
                print(f"⏳ Aguardando 2 segundos antes da próxima tentativa...")
                time.sleep(2)
            else:
                print(f"💥 Falha após {max_tentativas} tentativas. Erro final: {e}")
                
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                if hasattr(conn, "is_connected"):
                    if conn.is_connected():
                        conn.close()
                else:
                    conn.close()

# Função para verificar integridade da base de dados
def verificar_integridade_bd():
    """
    Verifica se todas as tabelas necessárias existem na base de dados.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        tabelas_necessarias = ["roles", "users", "clientes", "media", "results", "logs", "noticias_sugeridas"]
        tabelas_existentes = []
        tabelas_em_falta = []
        
        for tabela in tabelas_necessarias:
            if tabela_existe(cursor, tabela):
                tabelas_existentes.append(tabela)
            else:
                tabelas_em_falta.append(tabela)
        
        print(f"📊 Verificação de integridade da BD:")
        print(f"✅ Tabelas existentes: {', '.join(tabelas_existentes)}")
        if tabelas_em_falta:
            print(f"❌ Tabelas em falta: {', '.join(tabelas_em_falta)}")
            return False
        else:
            print("🎉 Todas as tabelas necessárias estão presentes!")
            return True
            
    except Error as e:
        print(f"❌ Erro ao verificar integridade: {e}")
        return False
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
print("🚀 Inicializando base de dados...")
criar_tabelas()
verificar_integridade_bd()