#!/usr/bin/env python3
"""
Script para corrigir as roles dos utilizadores existentes na base de dados.
"""

import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import re

load_dotenv()

def conectar_bd():
    """Conecta à base de dados"""
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        return conn
    except Error as e:
        print(f"❌ Erro de conexão: {e}")
        return None

def processar_admin_emails():
    """Processa os emails de admin do .env"""
    ADMIN_EMAILS_RAW = os.getenv("ADMIN_EMAIL")
    ADMIN_EMAILS = []
    if ADMIN_EMAILS_RAW:
        # Remover aspas duplas e simples, depois dividir por vírgula
        cleaned_emails = re.sub(r'["\\]', '', ADMIN_EMAILS_RAW)
        ADMIN_EMAILS = [e.strip().lower() for e in cleaned_emails.split(',') if e.strip()]
    
    print(f"📧 Emails de admin processados: {ADMIN_EMAILS}")
    return ADMIN_EMAILS

def corrigir_roles_utilizadores():
    """Corrige as roles dos utilizadores existentes"""
    conn = conectar_bd()
    if not conn:
        return
    
    cursor = conn.cursor()
    admin_emails = processar_admin_emails()
    
    try:
        # Obter ID da role admin
        cursor.execute("SELECT id FROM roles WHERE name = 'admin'")
        admin_role_result = cursor.fetchone()
        
        if not admin_role_result:
            print("❌ Role 'admin' não encontrada na base de dados!")
            return
        
        admin_role_id = admin_role_result[0]
        print(f"✅ Role 'admin' encontrada com ID: {admin_role_id}")
        
        # Obter todos os utilizadores
        cursor.execute("SELECT id, email, role_id FROM users")
        users = cursor.fetchall()
        
        print(f"👤 Encontrados {len(users)} utilizadores na base de dados")
        
        for user_id, email, current_role_id in users:
            if email.lower() in admin_emails:
                if current_role_id != admin_role_id:
                    # Atualizar para admin
                    cursor.execute("UPDATE users SET role_id = %s WHERE id = %s", (admin_role_id, user_id))
                    print(f"✅ Utilizador '{email}' atualizado para role admin")
                else:
                    print(f"ℹ️ Utilizador '{email}' já tem role admin")
            else:
                print(f"ℹ️ Utilizador '{email}' mantém role atual (não é admin)")
        
        conn.commit()
        print("✅ Correção de roles concluída!")
        
    except Error as e:
        print(f"❌ Erro ao corrigir roles: {e}")
    finally:
        cursor.close()
        conn.close()

def verificar_estado_final():
    """Verifica o estado final dos utilizadores"""
    conn = conectar_bd()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        SELECT u.id, u.email, r.name as role_name 
        FROM users u 
        LEFT JOIN roles r ON u.role_id = r.id
        ORDER BY r.name, u.email
        """)
        users = cursor.fetchall()
        
        print("\n📊 Estado final dos utilizadores:")
        print("-" * 50)
        for user_id, email, role_name in users:
            print(f"ID: {user_id:2} | Email: {email:30} | Role: {role_name}")
        
    except Error as e:
        print(f"❌ Erro ao verificar estado final: {e}")
    finally:
        cursor.close()
        conn.close()

def main():
    print("🔧 Script de Correção de Roles")
    print("=" * 50)
    
    # Processar emails de admin
    admin_emails = processar_admin_emails()
    
    if not admin_emails:
        print("❌ Nenhum email de admin encontrado no .env!")
        return
    
    # Corrigir roles
    corrigir_roles_utilizadores()
    
    # Verificar estado final
    verificar_estado_final()
    
    print("\n✅ Script concluído!")

if __name__ == "__main__":
    main()

