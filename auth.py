import mysql.connector
import bcrypt
from datetime import datetime
import os
from database import get_connection

conn = get_connection()
cursor = conn.cursor()

from dotenv import load_dotenv

load_dotenv()
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

def register_user(username: str, email: str, password: str):
    if not username or not email or not password:
        raise ValueError("Todos os campos são obrigatórios.")

    if ADMIN_EMAIL and email.strip().lower() == ADMIN_EMAIL.strip().lower():
        role_name = "admin"
    else:
        role_name = "user"
    
    role_id = get_role_id_by_name(role_name)
    if role_id is None:
        # CORREÇÃO: Se a role não existir, criar automaticamente
        print(f"⚠️ Role '{role_name}' não encontrada. A criar automaticamente...")
        role_id = criar_role_se_nao_existir(role_name)
        if role_id is None:
            raise ValueError(f"Não foi possível criar a role '{role_name}'.")

    hashed = hash_password(password)
    cursor.execute(
        "INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, %s)",
        (username, email, hashed, role_id)
    )
    conn.commit()

def criar_role_se_nao_existir(role_name: str):
    """
    Cria uma role se ela não existir e retorna o seu ID.
    """
    try:
        cursor.execute("INSERT INTO roles (name) VALUES (%s)", (role_name,))
        conn.commit()
        print(f"✅ Role '{role_name}' criada com sucesso.")
        return cursor.lastrowid
    except mysql.connector.IntegrityError:
        # Role já existe, buscar o ID
        cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Erro ao criar role '{role_name}': {e}")
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
    return result[0] if result else "Desconhecido"

# ---------------------------
# LOGGING
# ---------------------------

def log_action(user_email: str, action: str, target: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO logs (timestamp, user_email, action, target) VALUES (%s, %s, %s, %s)",
        (timestamp, user_email, action, target)
    )
    conn.commit()

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