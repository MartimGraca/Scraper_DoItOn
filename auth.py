import mysql.connector
import bcrypt
from datetime import datetime
import os
from database import get_connection

conn = get_connection()
cursor = conn.cursor()

from dotenv import load_dotenv

load_dotenv()

# Processar ADMIN_EMAIL como uma lista de emails
import os
import json
import re

ADMIN_EMAILS_RAW = os.getenv("ADMIN_EMAIL", "")
ADMIN_EMAILS = []

if ADMIN_EMAILS_RAW:
    try:
        # Tenta ler como JSON (Render ou .env como lista)
        parsed = json.loads(ADMIN_EMAILS_RAW)
        if isinstance(parsed, list):
            ADMIN_EMAILS = [e.strip().lower() for e in parsed if isinstance(e, str) and e.strip()]
        elif isinstance(parsed, str):
            ADMIN_EMAILS = [parsed.strip().lower()]
    except Exception:
        # Se não for JSON, trata como CSV
        cleaned = re.sub(r'["\'\[\]]', '', ADMIN_EMAILS_RAW)
        ADMIN_EMAILS = [e.strip().lower() for e in cleaned.split(',') if e.strip()]

print(f"ADMIN_EMAILS carregados: {ADMIN_EMAILS}")

def is_admin_email(email):
    return email.strip().lower() in ADMIN_EMAILS


def is_admin_email(email):
    """
    Verifica se um email está na lista de emails de administrador.
    """
    return email.strip().lower() in ADMIN_EMAILS

def register_user(username: str, email: str, password: str):
    if is_admin_email(email):
        role_name = "admin"
    else:
        role_name = "user"
    if not username or not email or not password:
        raise ValueError("Todos os campos são obrigatórios.")

    
    
    role_id = get_role_id_by_name(role_name)
    if role_id is None:
        # CORREÇÃO: Se a role não existir, criar automaticamente
        print(f"⚠️ Role \'{role_name}\' não encontrada. A criar automaticamente...")
        role_id = criar_role_se_nao_existir(role_name)
        if role_id is None:
            raise ValueError(f"Não foi possível criar a role \'{role_name}\'.")

    hashed = hash_password(password)
    
    # Verificar se o email já existe
    existing_user = get_user(email)
    if existing_user:
        # Se é admin e já existe, permitir atualização de username/password
        if is_admin_email(email):
            cursor.execute(
                "UPDATE users SET username = %s, password_hash = %s WHERE email = %s",
                (username, hashed, email)
            )
            conn.commit()
            print(f"✅ Utilizador admin \'{email}\' atualizado com sucesso.")
        else:
            raise mysql.connector.IntegrityError("Email já registado.")
    else:
        # Criar novo utilizador
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, %s)",
            (username, email, hashed, role_id)
        )
        conn.commit()
        print(f"✅ Novo utilizador \'{email}\' criado com role \'{role_name}\'.")

def criar_role_se_nao_existir(role_name: str):
    """
    Cria uma role se ela não existir e retorna o seu ID.
    """
    try:
        cursor.execute("INSERT INTO roles (name) VALUES (%s)", (role_name,))
        conn.commit()
        print(f"✅ Role \'{role_name}\' criada com sucesso.")
        return cursor.lastrowid
    except mysql.connector.IntegrityError:
        # Role já existe, buscar o ID
        cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Erro ao criar role \'{role_name}\': {e}")
        return None

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# FUNÇÕES DE UTILIZADORES
# ---------------------------

def get_user(email: str):
    cursor.execute("SELECT id, username, email, password_hash, role_id FROM users WHERE email = %s", (email,))
    return cursor.fetchone()

def get_role_id_by_name(name: str):
    cursor.execute("SELECT id FROM roles WHERE name = %s", (name,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_role_name(role_id: int) -> str:
    cursor.execute("SELECT name FROM roles WHERE id = %s", (role_id,))
    result = cursor.fetchone()
    return result[0] if result else "user"

# ---------------------------
# LOGGING COM VERIFICAÇÃO DE TABELA
# ---------------------------

def log_action(user_email: str, action: str, target: str):
    """
    Regista uma ação no log, com verificação se a tabela logs existe.
    """
    try:
        # Verificar se a tabela logs existe antes de tentar inserir
        cursor.execute("SHOW TABLES LIKE \'logs\'")
        if not cursor.fetchone():
            print("⚠️ Tabela \'logs\' não encontrada. A criar...")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp TEXT,
                user_email TEXT,
                action TEXT,
                target TEXT
            );
            """)
            conn.commit()
            print("✅ Tabela \'logs\' criada.")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO logs (timestamp, user_email, action, target) VALUES (%s, %s, %s, %s)",
            (timestamp, user_email, action, target)
        )
        conn.commit()
        print(f"📝 Log registado: {user_email} - {action}")
        
    except Exception as e:
        print(f"❌ Erro ao registar log: {e}")
        # Não falhar a aplicação por causa de um erro de log
        pass

# ---------------------------
# PROTEÇÃO CONTRA TENTATIVAS
# ---------------------------

def login_tentativas_check(st):
    if "tentativas_login" not in st.session_state:
        st.session_state["tentativas_login"] = 0

    if st.session_state["tentativas_login"] >= 5:
        return False, "⚠️ Múltiplas tentativas falhadas. Por favor, tente mais tarde."
    return True, ""

def login_falhou(st):
    if "tentativas_login" not in st.session_state:
        st.session_state["tentativas_login"] = 0
    st.session_state["tentativas_login"] += 1

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )



