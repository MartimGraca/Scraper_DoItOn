import os
from dotenv import load_dotenv
from database import get_connection

load_dotenv()

def main():
    db_host = os.getenv("DB_HOST", "<desconhecido>")
    db_name = os.getenv("DB_NAME", "<desconhecido>")
    db_user = os.getenv("DB_USER", "<desconhecido>")

    print("Vai APAGAR TODOS os utilizadores da tabela 'users'.")
    print(f"Alvo: DB_HOST={db_host} DB_NAME={db_name} DB_USER={db_user}")
    confirm = input("Escreve exatamente 'APAGAR' para continuar: ").strip()
    if confirm != "APAGAR":
        print("Operação cancelada.")
        return

    conn = get_connection()
    cur = conn.cursor()
    try:
        try:
            cur.execute("SELECT COUNT(*) FROM users")
            before = cur.fetchone()[0]
        except Exception:
            before = None

        try:
            cur.execute("SET SQL_SAFE_UPDATES = 0")
        except Exception:
            pass

        cur.execute("DELETE FROM users")
        try:
            cur.execute("ALTER TABLE users AUTO_INCREMENT = 1")
        except Exception:
            pass

        conn.commit()

        cur.execute("SELECT COUNT(*) FROM users")
        after = cur.fetchone()[0]

        print(f"✅ Concluído. Registos antes: {before if before is not None else '?'} | depois: {after}")
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao apagar utilizadores: {e}")
    finally:
        try: cur.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

if __name__ == "__main__":
    main()