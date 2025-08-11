#!/usr/bin/env python3
"""
Script de debug para verificar o estado da base de dados e corrigir problemas.
"""

import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

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

def verificar_tabelas():
    """Verifica quais tabelas existem na base de dados"""
    conn = conectar_bd()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("SHOW TABLES")
        tabelas = cursor.fetchall()
        
        print("📋 Tabelas existentes na base de dados:")
        if tabelas:
            for tabela in tabelas:
                print(f"  - {tabela[0]}")
        else:
            print("  Nenhuma tabela encontrada!")
            
    except Error as e:
        print(f"❌ Erro ao verificar tabelas: {e}")
    finally:
        cursor.close()
        conn.close()

def verificar_roles():
    """Verifica as roles existentes na base de dados"""
    conn = conectar_bd()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, name FROM roles")
        roles = cursor.fetchall()
        
        print("🔐 Roles existentes na base de dados:")
        if roles:
            for role_id, role_name in roles:
                print(f"  - ID: {role_id}, Nome: {role_name}")
        else:
            print("  Nenhuma role encontrada!")
            
    except Error as e:
        print(f"❌ Erro ao verificar roles: {e}")
        if "doesn't exist" in str(e):
            print("  A tabela 'roles' não existe!")
    finally:
        cursor.close()
        conn.close()

def verificar_utilizadores():
    """Verifica os utilizadores existentes na base de dados"""
    conn = conectar_bd()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        SELECT u.id, u.username, u.email, r.name as role_name 
        FROM users u 
        LEFT JOIN roles r ON u.role_id = r.id
        """)
        users = cursor.fetchall()
        
        print("👤 Utilizadores existentes na base de dados:")
        if users:
            for user_id, username, email, role_name in users:
                print(f"  - ID: {user_id}, Username: {username}, Email: {email}, Role: {role_name}")
        else:
            print("  Nenhum utilizador encontrado!")
            
    except Error as e:
        print(f"❌ Erro ao verificar utilizadores: {e}")
        if "doesn't exist" in str(e):
            print("  A tabela 'users' ou 'roles' não existe!")
    finally:
        cursor.close()
        conn.close()

def criar_roles_se_necessario():
    """Cria as roles necessárias se não existirem"""
    conn = conectar_bd()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        # Primeiro, verificar se a tabela roles existe
        cursor.execute("SHOW TABLES LIKE 'roles'")
        if not cursor.fetchone():
            print("⚠️ Tabela 'roles' não existe. A criar...")
            cursor.execute("""
            CREATE TABLE roles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL
            );
            """)
            conn.commit()
            print("✅ Tabela 'roles' criada.")
        
        # Inserir roles necessárias
        roles_necessarias = ["user", "account", "admin"]
        
        for role_name in roles_necessarias:
            try:
                cursor.execute("INSERT IGNORE INTO roles (name) VALUES (%s)", (role_name,))
                if cursor.rowcount > 0:
                    print(f"✅ Role '{role_name}' inserida.")
                else:
                    print(f"ℹ️ Role '{role_name}' já existe.")
            except Error as e:
                print(f"❌ Erro ao inserir role '{role_name}': {e}")
        
        conn.commit()
        
    except Error as e:
        print(f"❌ Erro ao criar roles: {e}")
    finally:
        cursor.close()
        conn.close()

def atualizar_role_utilizador(email, nova_role):
    """Atualiza a role de um utilizador específico"""
    conn = conectar_bd()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        # Obter ID da nova role
        cursor.execute("SELECT id FROM roles WHERE name = %s", (nova_role,))
        role_result = cursor.fetchone()
        
        if not role_result:
            print(f"❌ Role '{nova_role}' não encontrada!")
            return
        
        role_id = role_result[0]
        
        # Atualizar utilizador
        cursor.execute("UPDATE users SET role_id = %s WHERE email = %s", (role_id, email))
        
        if cursor.rowcount > 0:
            conn.commit()
            print(f"✅ Role do utilizador '{email}' atualizada para '{nova_role}'.")
        else:
            print(f"❌ Utilizador '{email}' não encontrado!")
            
    except Error as e:
        print(f"❌ Erro ao atualizar role: {e}")
    finally:
        cursor.close()
        conn.close()

def main():
    print("🔍 Script de Debug da Base de Dados")
    print("=" * 50)
    
    # Verificar estado atual
    verificar_tabelas()
    print()
    verificar_roles()
    print()
    verificar_utilizadores()
    print()
    
    # Criar roles se necessário
    print("🔧 A criar roles necessárias...")
    criar_roles_se_necessario()
    print()
    
    # Verificar novamente após correções
    print("🔍 Estado após correções:")
    verificar_roles()
    print()
    verificar_utilizadores()
    print()
    
    # Atualizar role do admin se necessário
    admin_emails = ["fernando.batista@doiton.agency", "martimgraca5@gmail.com"]
    
    for email in admin_emails:
        print(f"🔧 A atualizar role para admin: {email}")
        atualizar_role_utilizador(email, "admin")
    
    print()
    print("✅ Script de debug concluído!")

if __name__ == "__main__":
    main()

