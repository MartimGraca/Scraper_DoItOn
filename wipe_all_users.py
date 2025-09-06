import os
import time
from dotenv import load_dotenv

# Assumimos que tens database.get_connection() já implementado
from database import get_connection

load_dotenv()

TRUTHY = {"1", "true", "yes", "y", "on"}

def wipe_users_once(
    flag_file: str = ".wipe_users_once",
    use_env_flag: bool = True,
    retries: int = 5,
    delay_seconds: int = 5,
    auto_remove_flag: bool = True,
) -> None:
    """
    Se existir o ficheiro `flag_file` na raiz do projeto ou a env WIPE_USERS_ON_STARTUP for true,
    tenta apagar TODOS os registos da tabela `users` (com retries).
    Após sucesso, remove o ficheiro de flag se auto_remove_flag=True.
    """
    root = os.getcwd()
    flag_path = os.path.join(root, flag_file)

    env_flag = os.getenv("WIPE_USERS_ON_STARTUP", "").strip().lower() in TRUTHY if use_env_flag else False
    should_wipe = env_flag or os.path.exists(flag_path)

    if not should_wipe:
        return

    print("🧹 Wipe de utilizadores (on startup) ativado...")
    last_err = None

    for attempt in range(1, retries + 1):
        try:
            conn = get_connection()
            cur = conn.cursor()

            try:
                # Opcional: desativar FKs durante o wipe (só MySQL)
                try:
                    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
                except Exception:
                    pass

                # Apagar todos os utilizadores
                cur.execute("DELETE FROM users")

                # Reset do AUTO_INCREMENT (ignora erros)
                try:
                    cur.execute("ALTER TABLE users AUTO_INCREMENT = 1")
                except Exception:
                    pass

                # Reativar FKs
                try:
                    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
                except Exception:
                    pass

                conn.commit()
                print("✅ Wipe concluído com sucesso.")

                # Remover sinal após sucesso
                if os.path.exists(flag_path) and auto_remove_flag:
                    try:
                        os.remove(flag_path)
                        print(f"🗑️ Ficheiro de flag removido: {flag_path}")
                    except Exception as e_rm:
                        print(f"⚠️ Não foi possível remover o ficheiro de flag: {e_rm}")

                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

                return

            except Exception as e:
                conn.rollback()
                last_err = e
                print(f"❌ Erro ao executar wipe: {e}")

            finally:
                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

        except Exception as e_conn:
            last_err = e_conn
            print(f"🔄 Tentativa {attempt}/{retries} de ligar à BD falhou: {e_conn}")

        if attempt < retries:
            print(f"⏳ A aguardar {delay_seconds}s antes de nova tentativa...")
            time.sleep(delay_seconds)

    print("🚫 Desisti do wipe após múltiplas tentativas.")
    if last_err:
        print(f"Último erro: {last_err}")