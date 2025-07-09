import sqlite3
from datetime import datetime
from scraper_google import executar_scraper_google
import time

DB_PATH = "database.db"

def get_clientes_keywords():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, keywords FROM clientes WHERE keywords IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return rows

def guardar_noticia(noticia, cliente_id, keyword):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO noticias_sugeridas (titulo, url, data, keyword, cliente_id, site)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (noticia["titulo"], noticia["link"], noticia["data"], keyword, cliente_id, noticia["site"]))
        conn.commit()
    except Exception as e:
        print("Erro a guardar:", e)
    finally:
        conn.close()

def correr_para_todos():
    clientes = get_clientes_keywords()
    for cliente_id, keywords_str in clientes:
        if not keywords_str:
            continue
        keywords = [kw.strip() for kw in keywords_str.split(",") if kw.strip()]
        for keyword in keywords:
            print(f"[{datetime.now()}] A correr para Cliente {cliente_id} - Keyword: {keyword}")
            try:
                resultados = executar_scraper_google(keyword, "Últimas 24 horas")
                for r in resultados:
                    if r["status"] == "ENCONTRADA":
                        guardar_noticia(r, cliente_id, keyword)
                time.sleep(5)
            except Exception as e:
                print(f"Erro: {e}")

if __name__ == "__main__":
    correr_para_todos()
