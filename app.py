
import math 
import pandas as pd
import plotly.express as px
import streamlit as st
import sqlite3
from PIL import Image
import io
import hashlib
from datetime import datetime
import nest_asyncio
from dotenv import load_dotenv
import bcrypt
import mysql.connector

from scraper import executar_scraper
from scraper import get_site_name
import matplotlib.pyplot as plt
from scraper_google import executar_scraper_google
from scraper_google import rodar_scraper_sequencial
from streamlit_option_menu import option_menu
import multiprocessing
multiprocessing.set_start_method("spawn", force=True)
import asyncio
import sys
from st_aggrid import AgGrid
from auth import get_user, check_password, register_user, log_action, login_tentativas_check, login_falhou, get_role_name
import os

load_dotenv()
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ----------- Configuração da BD -----------
from database import get_connection

conn = get_connection()
cursor = conn.cursor()

# ----------- Funções de BD com verificação de tabelas -----------

def verificar_e_criar_tabela_se_necessario(nome_tabela, sql_criacao):

    try:
        cursor.execute(f"SHOW TABLES LIKE '{nome_tabela}'")
        if not cursor.fetchone():
            print(f"⚠️ Tabela '{nome_tabela}' não encontrada. A criar...")
            cursor.execute(sql_criacao)
            conn.commit()
            print(f"✅ Tabela '{nome_tabela}' criada.")
    except Exception as e:
        print(f"❌ Erro ao verificar/criar tabela '{nome_tabela}': {e}")

def get_role_id_by_name(name):
    cursor.execute("SELECT id FROM roles WHERE name = %s", (name,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_all_users():
    cursor.execute("SELECT users.id, username, email, roles.name FROM users JOIN roles ON users.role_id = roles.id")
    return cursor.fetchall()

def update_user_role(user_id, new_role_id):
    cursor.execute("UPDATE users SET role_id = %s WHERE id = %s", (new_role_id, user_id))
    conn.commit()

def get_roles():
    cursor.execute("SELECT id, name FROM roles")
    return cursor.fetchall()

def get_clientes(email, role):
    # Verificar se a tabela clientes existe
    verificar_e_criar_tabela_se_necessario("clientes", """
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
    
    if role in ("admin", "account") or email is None:
        cursor.execute("SELECT id, nome, perfil, tier, keywords, logo, email FROM clientes")
    else:
        cursor.execute("SELECT id, nome, perfil, tier, keywords, logo, email FROM clientes WHERE email = %s", (email,))
    return cursor.fetchall()

def get_media_by_cliente(cliente_id):
    # Verificar se a tabela media existe
    verificar_e_criar_tabela_se_necessario("media", """
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
    
    cursor.execute("SELECT id, nome, url, tipologia, segmento FROM media WHERE cliente_id = %s", (cliente_id,))
    return cursor.fetchall()

def insert_media(nome, url, cliente_id, tipologia, segmento, tier):
    cursor.execute(
        "INSERT INTO media (nome, url, cliente_id, tipologia, segmento, tier) VALUES (%s, %s, %s, %s, %s, %s)",
        (nome, url, cliente_id, tipologia, segmento, tier)
    )
    conn.commit()

def media_existe(nome, cliente_id):
    # Devolve na ordem que o UI espera:
    # (id, nome, url, tipologia, segmento, tier)
    cursor.execute(
        "SELECT id, nome, url, tipologia, segmento, tier FROM media WHERE nome = %s AND cliente_id = %s LIMIT 1",
        (nome, cliente_id)
    )
    return cursor.fetchone()


def media_por_url(url):
    # Devolve dict com cliente_id para podermos decidir o que fazer
    cursor.execute(
        "SELECT id, nome, url, cliente_id, tipologia, segmento, tier FROM media WHERE url = %s LIMIT 1",
        (url,)
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "nome": row[1],
        "url": row[2],
        "cliente_id": row[3],
        "tipologia": row[4],
        "segmento": row[5],
        "tier": row[6],
    }

def obter_tier_por_nome(nome):
    cursor.execute("SELECT tier FROM media WHERE LOWER(nome) = LOWER(%s) LIMIT 1", (nome,))
    resultado = cursor.fetchone()
    if resultado:
        return resultado[0]
    return None

def update_media(media_id, nome, url, tipologia, segmento, tier):
    cursor.execute(
        "UPDATE media SET nome = %s, url = %s, tipologia = %s, segmento = %s, tier = %s WHERE id = %s",
        (nome, url, tipologia, segmento, tier, media_id)
    )
    conn.commit()

def extrair_nome_midia(site_name, titulo):
    if "|" in titulo:
        candidato = titulo.split("|")[-1].strip()
        if 2 <= len(candidato) <= 40 and not candidato.lower().startswith("www."):
            return candidato
    site_name = site_name.lower().replace("www.", "")
    dominio = site_name.split(".")[0]
    return dominio.capitalize()

def delete_cliente(cliente_id):
    cursor.execute("DELETE FROM media WHERE cliente_id = %s", (cliente_id,))
    cursor.execute("DELETE FROM clientes WHERE id = %s", (cliente_id,))
    conn.commit()

def delete_users(user_id):
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()

def eliminar_midia(midia_id):
    cursor.execute("DELETE FROM media WHERE id = %s", (midia_id,))
    conn.commit()


# ----------- Autenticação -----------

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    login, register = st.tabs(["Login", "Registo"])

    with login:
        st.header("Login")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        ok, msg = login_tentativas_check(st)
        if not ok:
            st.warning(msg)
            st.stop()

        if st.button("Entrar"):
            user = get_user(email)
            if user and check_password(password, user[3]):
                # CORREÇÃO: Usar a role real da base de dados
                role_name = get_role_name(user[4])  # user[4] é role_id
                
                st.session_state.user = {
                    "id": user[0],
                    "username": user[1],
                    "email": user[2],
                    "role_id": user[4],
                    "role_name": role_name,  # Usar role real da BD
                    "is_admin": role_name == "admin"
                }
                log_action(email, "login de utilizador", "sistema")
                st.session_state["tentativas_login"] = 0
                st.rerun()
            else:
                login_falhou(st)
                st.error("❌ Credenciais inválidas.")

    with register:
        st.header("Registo")
        username = st.text_input("Novo utilizador", key="reg_username")
        reg_email = st.text_input("Email de registo", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        if st.button("Criar Conta"):
            try:
                register_user(username, reg_email, reg_password)
                log_action(reg_email, "registo de novo utilizador", "utilizador")
                st.success("Conta criada com sucesso! Faça login.")
            except mysql.connector.IntegrityError:
                st.error("Email já registado.")
            except ValueError as e:
                st.error(str(e))

    st.stop()


# ----------- Layout Base -----------
st.set_page_config(page_title="ScraperApp", layout="wide")

col1, col2 = st.columns([9, 1])
with col1:
    st.image("https://doiton.agency/wp-content/uploads/2022/10/logo_doiton.jpg")
with col2:
    st.image("https://www.w3schools.com/w3images/avatar2.png", width=40)
    st.write(f"👤 {st.session_state.user['username']}")
    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()


# ----------- Sidebar -----------
with st.sidebar:
    st.markdown("---")

    if "user" in st.session_state and st.session_state.user:
        user = st.session_state.user
        role_name = user["role_name"]
        username = user["username"]

        # Cabeçalho com utilizador
        st.markdown(f"👤 **{username}**")
        st.markdown(f"🔐 *{role_name.title()}*")
        st.markdown("---")



role_name = st.session_state.user["role_name"]
if role_name == "admin":
    menu = st.sidebar.radio("Navegação", ["Scraper","Resultados Automáticos","Clientes", "Dashboard", "Gestão Utilizadores", "Admin DB","Logs","Media"])
elif role_name == "account":
    menu = st.sidebar.radio("Navegação", ["Scraper" ,"Resultados Automáticos","Clientes", "Dashboard","Media"])
else:
    menu = st.sidebar.radio("Navegação", ["Clientes", "Dashboard"])



# ----------- Página Scraper -----------

import nest_asyncio
nest_asyncio.apply()

if menu == "Scraper" and role_name in ["admin", "account"]:
    st.title("Web Scraper")

    if "resultados_direto" not in st.session_state:
        st.session_state["resultados_direto"] = []
    if "resultados_scraper" not in st.session_state:
        st.session_state["resultados_scraper"] = []

    clientes = get_clientes(email=st.session_state.user["email"], role=role_name)
    nomes_clientes = [c[1] for c in clientes]
    
    if not nomes_clientes:
        st.warning("⚠️ Nenhum cliente encontrado. Contacte o administrador para criar clientes.")
        st.stop()
    
    empresa = st.selectbox("Empresa", nomes_clientes)
    cliente_id = next((c[0] for c in clientes if c[1] == empresa), None)

    keywords_atuais = ""
    for c in clientes:
        if c[1] == empresa:
            keywords_atuais = c[4] or ""

    modo_scraper = st.radio("Escolha o modo de scraping:", ["Website Direto", "Google Notícias"])

    # ---------- WEBSITE DIRETO ----------
    if modo_scraper == "Website Direto":
        url = st.text_input("🌐 URL do site")
        keyword = st.text_input("🔍 Palavra-chave", value=keywords_atuais.split(",")[0] if keywords_atuais else "")
        max_results = st.slider("Nº máximo de resultados", 1, 20, 5)

        if st.button("🚀 Iniciar Scraper (Direto)"):
            if url and keyword:
                with st.spinner("A recolher dados...Vai beber um cafézinho ☕"):
                    resultados = asyncio.run(executar_scraper(url, keyword, max_results))
                    st.session_state["resultados_direto"] = resultados
            else:
                st.warning("Preencha todos os campos.")

        if st.session_state["resultados_direto"]:
            st.subheader("📑 Resultados")
            for i, resultado in enumerate(st.session_state["resultados_direto"]):
                titulo = resultado[0]
                link = resultado[1]
                site_name = resultado[2]

                with st.expander(f"Resultado {i + 1}"):
                    st.markdown(f"**Título:** {titulo}")
                    st.markdown(f"**Nome do Site:** {site_name}")
                    st.markdown(f"[🌐 Abrir Link]({link})", unsafe_allow_html=True)

                    nome_sugerido = extrair_nome_midia(site_name, titulo)
                    nome = st.text_input("📝 Nome da Media", nome_sugerido, key=f"{keyword}_nome_{i}")
                    tipologia = st.selectbox("📺 Tipologia", ["Online", "TV", "Rádio", "Imprensa"], key=f"dir_tipo_{i}")
                    segmento = st.selectbox("🏷️ Segmento", ["Tecnologia", "Político", "Saúde", "Outro"], key=f"dir_seg_{i}")
                    tier_automatico = obter_tier_por_nome(nome)
                    tier_default = tier_automatico if tier_automatico else 4

                    tier = st.selectbox("⭐ Tier", [1, 2, 3, 4], index=tier_default - 1, key=f"dir_tier_{i}")

                    if st.button("💾 Guardar", key=f"dir_guardar_{i}"):
                        existente = media_existe(nome, cliente_id)  # (id, nome, url, tipologia, segmento, tier)

                        # Se não existir por nome, verificar se a URL já existe (para evitar erro de UNIQUE)
                        if not existente:
                            ex_url = media_por_url(link)  # dict com cliente_id
                            if ex_url:
                                if ex_url["cliente_id"] == cliente_id:
                                    # Tratar como existente para este cliente
                                    existente = (
                                        ex_url["id"], ex_url["nome"], ex_url["url"],
                                        ex_url["tipologia"], ex_url["segmento"], ex_url["tier"]
                                    )
                                else:
                                    # URL pertence a outro cliente -> informar e não inserir
                                    dono = next((c[1] for c in clientes if c[0] == ex_url["cliente_id"]), "Outro cliente")
                                    st.warning(f"⚠️ Esta URL já está associada à empresa: {dono}. Não é possível reutilizar.")
                                    st.stop()

                        if existente:
                            st.warning("⚠️ Já existe uma media com este nome/URL para esta empresa.")
                            col1, col2 = st.columns(2)

                            with col1:
                                st.markdown("#### 📄 Media Existente")
                                st.write(f"**Nome:** {existente[1]}")
                                st.write(f"**URL:** {existente[2]}")
                                st.write(f"**Tipologia:** {existente[3]}")
                                st.write(f"**Segmento:** {existente[4]}")
                                st.write(f"**Tier:** {existente[5]}")

                            with col2:
                                st.markdown("#### ✍️ Nova Media")
                                st.write(f"**Nome:** {nome}")
                                st.write(f"**URL:** {link}")
                                st.write(f"**Tipologia:** {tipologia}")
                                st.write(f"**Segmento:** {segmento}")
                                st.write(f"**Tier:** {tier}")

                            if st.button("✅ Confirmar e Substituir", key=f"dir_confirma_{i}_{existente[0]}"):
                                update_media(
                                    media_id=existente[0],
                                    nome=nome,
                                    url=link,
                                    tipologia=tipologia,
                                    segmento=segmento,
                                    tier=tier
                                )
                                st.success("Media atualizada com sucesso!")
                                st.rerun()
                            elif st.button("❌ Cancelar", key=f"dir_cancel_{i}"):
                                st.info("Operação cancelada.")
                        else:
                            insert_media(nome, link, cliente_id, tipologia, segmento, tier)
                            st.success("Guardado com sucesso!")
                            st.rerun()

    # ---------- GOOGLE NEWS ----------
    elif modo_scraper == "Google Notícias":
     st.subheader("🔍 Pesquisa no Google Notícias")
    keyword = st.text_input("Insira palavras-chave separadas por vírgula:", value=keywords_atuais)
    filtro_tempo = st.selectbox("Filtrar por período de tempo:", ["Na última hora", "Últimas 24 horas", "Última semana", "Último mês", "Último ano"])

    if st.button("🔎 Pesquisar"):
        if not cliente_id:
            st.warning("Por favor, selecione ou crie um cliente antes de continuar.")
        else:
            keywords = [kw.strip() for kw in keyword.split(",") if kw.strip()]
            st.session_state["resultados_scraper"] = []

            for kw in keywords:
                with st.spinner(f"A recolher dados para {kw} ☕"):
                    try:
                        resultados_kw = executar_scraper_google(kw, filtro_tempo)
                        st.session_state["resultados_scraper"].append({
                            "keyword": kw,
                            "resultados": resultados_kw
                        })
                        st.success(f"✅ {len(resultados_kw)} resultados encontrados para: '{kw}'")
                    except Exception as e:
                        st.error(f"❌ Erro ao processar keyword '{kw}': {e}")

    # Mostra resultados, mesmo após o clique no botão
    for grupo in st.session_state.get("resultados_scraper", []):
        kw = grupo["keyword"]
        resultados_kw = grupo["resultados"]

        st.subheader(f"📑 Resultados do Google para : {kw}")
        if not isinstance(resultados_kw, list):
            st.error("❌ O scraper não devolveu resultados válidos para esta keyword.")
            resultados_kw = []

        for i, resultado in enumerate(resultados_kw):
            link = resultado.get("link", "")
            site_name = resultado.get("site", "Desconhecido")
            titulo = resultado.get("titulo", "Sem título")
            data_pub = resultado.get("data", "N/D")

            with st.expander(f"Notícia {i + 1}"):
                st.markdown(f"**Título:** {titulo}")
                st.markdown(f"**Nome do Site:** {site_name}")
                st.markdown(f"**🕒 Data de Publicação:** {data_pub}")
                st.markdown(f"[🌐 Abrir Link]({link})", unsafe_allow_html=True)

                nome_sugerido = extrair_nome_midia(site_name, titulo)
                nome = st.text_input("📝 Nome da Media", nome_sugerido, key=f"{kw}_nome_{i}")
                tipologia = st.selectbox("📺 Tipologia", ["Online", "TV", "Rádio", "Imprensa"], key=f"{kw}_tipo_{i}")
                segmento = st.selectbox("🏷️ Segmento", ["Tecnologia", "Político", "Saúde", "Outro"], key=f"{kw}_seg_{i}")
                tier_automatico = obter_tier_por_nome(nome)
                tier_default = tier_automatico if tier_automatico else 4

                tier = st.selectbox("⭐ Tier", [1, 2, 3, 4], index=tier_default - 1, key=f"dir_tier_{i}")

                if st.button("💾 Guardar", key=f"dir_guardar_{i}"):
                        existente = media_existe(nome, cliente_id)  # (id, nome, url, tipologia, segmento, tier)

                        # Também verificar por URL antes de tentar inserir
                        if not existente:
                            ex_url = media_por_url(link)
                            if ex_url:
                                if ex_url["cliente_id"] == cliente_id:
                                    existente = (
                                        ex_url["id"], ex_url["nome"], ex_url["url"],
                                        ex_url["tipologia"], ex_url["segmento"], ex_url["tier"]
                                    )
                                else:
                                    dono = next((c[1] for c in clientes if c[0] == ex_url["cliente_id"]), "Outro cliente")
                                    st.warning(f"⚠️ Esta URL já está associada à empresa: {dono}. Não é possível reutilizar.")
                                    st.stop()

                        # Guarda valores no session_state para o confirmar
                        st.session_state[f"dir_pending_nome_{i}"] = nome
                        st.session_state[f"dir_pending_tipologia_{i}"] = tipologia
                        st.session_state[f"dir_pending_segmento_{i}"] = segmento
                        st.session_state[f"dir_pending_tier_{i}"] = tier
                        st.session_state[f"dir_pending_link_{i}"] = link
                        st.session_state[f"dir_pending_id_{i}"] = existente[0] if existente else None

                        if existente:
                            st.warning("⚠️ Já existe uma media com este nome/URL para esta empresa.")
                            col1, col2 = st.columns(2)

                            with col1:
                                st.markdown("#### 📄 Media Existente")
                                st.write(f"**Nome:** {existente[1]}")
                                st.write(f"**URL:** {existente[2]}")
                                st.write(f"**Tipologia:** {existente[3]}")
                                st.write(f"**Segmento:** {existente[4]}")
                                st.write(f"**Tier:** {existente[5]}")

                            with col2:
                                st.markdown("#### ✍️ Nova Media")
                                st.write(f"**Nome:** {nome}")
                                st.write(f"**URL:** {link}")
                                st.write(f"**Tipologia:** {tipologia}")
                                st.write(f"**Segmento:** {segmento}")
                                st.write(f"**Tier:** {tier}")

                            if st.button("✅ Confirmar e Substituir", key=f"dir_confirma_{i}"):
                                update_media(
                                    media_id=st.session_state[f"dir_pending_id_{i}"],
                                    nome=st.session_state[f"dir_pending_nome_{i}"],
                                    url=st.session_state[f"dir_pending_link_{i}"],
                                    tipologia=st.session_state[f"dir_pending_tipologia_{i}"],
                                    segmento=st.session_state[f"dir_pending_segmento_{i}"],
                                    tier=st.session_state[f"dir_pending_tier_{i}"]
                                )
                                st.success("Media atualizada com sucesso!")
                                st.rerun()
                            elif st.button("❌ Cancelar", key=f"dir_cancelar_{i}"):
                                st.info("Cancelado.")
                        else:
                            insert_media(nome, link, cliente_id, tipologia, segmento, tier)
                            st.success("Guardado com sucesso!")
                            st.rerun()




# ----------- Página Dashboard (Placeholder) -----------
elif menu == "Dashboard":
    st.title("\U0001F4CA Dashboard de Clientes")







# ----------- Página Clientes -----------
elif menu == "Clientes":
    st.markdown("### 📁 Gestão de Clientes")

    role =st.session_state.user["role_name"]
    email = st.session_state.user["email"]

    clientes = get_clientes(email=email, role=role)

    # Botão adicionar empresa (só admin/account)
    col_add, _, _ = st.columns([1, 8, 1])
    with col_add:
        if role in ("admin", "account"):
            if st.button("➕ Nova Empresa", use_container_width=True):
                st.session_state["adicionar_empresa"] = True

    if st.session_state.get("adicionar_empresa", False):
        with st.expander("➕ Adicionar Nova Empresa", expanded=True):
            nome_empresa = st.text_input("Nome da Empresa", key="new_nome")
            perfil = st.text_input("Perfil", key="new_perfil")
            tier = st.selectbox("Tier", [1, 2, 3, 4], key="new_tier")
            email_cliente = st.text_input("Email associado ao cliente", key="new_email_cliente")
            logo_file = st.file_uploader("Logo", type=["png", "jpg", "jpeg"], key="new_logo")

            if st.button("💾 Salvar Empresa", use_container_width=True):
                if nome_empresa and perfil and email_cliente:
                    logo_bytes = logo_file.read() if logo_file else None
                    tier_value = int(tier)
                    cursor.execute("""
                        INSERT INTO clientes (nome, perfil, tier, keywords, logo, email)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (nome_empresa, perfil, tier_value, "", logo_bytes, email_cliente))
                    conn.commit()
                    st.success("✅ Empresa adicionada com sucesso!")
                    log_action(email, "criação de cliente", f"empresa: {nome_empresa}")
                    st.session_state["adicionar_empresa"] = False
                    st.rerun()
                else:
                    st.warning("⚠️ Preencha todos os campos obrigatórios.")

    # Filtrar cliente por email se for user
    if role == "user":
        clientes = [c for c in clientes if c[6] == email]

    nomes_clientes = [c[1] for c in clientes]
    if not nomes_clientes:
        st.warning("⚠️ Nenhum cliente associado.")
        st.stop()

    cliente_nome = st.selectbox("🔍 Selecione um Cliente", nomes_clientes)
    cliente = next((c for c in clientes if c[1] == cliente_nome), None)

    if cliente:
        cliente_id, nome, perfil, tier, keywords, logo_blob, email_assoc = cliente

        st.markdown("---")
        col_logo, col_info = st.columns([1, 3])
        with col_logo:
            if logo_blob:
                image = Image.open(io.BytesIO(logo_blob))
                st.image(image, width=120)
        with col_info:
            st.markdown(f"###  **{nome}**")
            st.markdown(f"**Perfil:** {perfil}")
            st.markdown(f"**Tier:** {tier}")
            st.markdown(f"**Email:** [{email_assoc}](mailto:{email_assoc})")
            st.markdown(f"**Keywords:** {keywords if keywords else '—'}")

        if role in ("admin", "account"):
            with st.expander("✏️ Editar Cliente"):
                novo_nome = st.text_input("Nome", nome, key="novo_nome")
                novo_perfil = st.text_input("Perfil", perfil, key="novo_perfil")
                novo_tier = st.selectbox(
                    "Tier do cliente",
                    options=[1, 2, 3, 4],
                    index=[1, 2, 3, 4].index(tier) if tier in [1, 2, 3, 4] else 4,
                    key="novo_tier"
                )
                novas_keywords = st.text_input("Keywords", keywords or "", key="novas_keywords")

                if st.button("💾 Guardar Alterações", key="update_cliente_btn"):
                    cursor.execute("""
                        UPDATE clientes SET nome=%s, perfil=%s, tier=%s, keywords=%s WHERE id=%s
                    """, (novo_nome, novo_perfil, novo_tier, novas_keywords, cliente_id))
                    conn.commit()
                    st.success("✅ Cliente atualizado!")
                    log_action(email, "edição de cliente", f"cliente: {novo_nome}")
                    st.rerun()

        # Botão eliminar cliente só para admin
        if role == "admin":
            if "confirm_delete_cliente" not in st.session_state:
                st.session_state["confirm_delete_cliente"] = False

            if not st.session_state["confirm_delete_cliente"]:
                if st.button("🗑️ Eliminar Cliente", key="btn_delete_cliente"):
                    st.session_state["confirm_delete_cliente"] = True
                    st.rerun()
            else:
                st.error(f"⚠️ Tem certeza que deseja eliminar o cliente: **{nome}**?")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Sim, eliminar", key="btn_confirm_delete"):
                        delete_cliente(cliente_id)
                        st.success("✅ Cliente eliminado com sucesso.")
                        log_action(email, "eliminação de cliente", f"cliente: {nome}")
                        st.session_state["confirm_delete_cliente"] = False
                        st.rerun()
                with col2:
                    if st.button("❌ Cancelar", key="btn_cancel_delete"):
                        st.session_state["confirm_delete_cliente"] = False
                        st.rerun()


        if "edit_media_active" not in st.session_state:
            st.session_state["edit_media_active"] = False

        # Medias associadas
        col_title, col_btn = st.columns([4, 1])
        with col_title:
            st.markdown("### Media Associada")
        with col_btn:
            if role in ("admin", "account"):
                if st.session_state["edit_media_active"]:
                    if st.button("❌ Fechar", key="btn_fechar_edicao_media", use_container_width=True):
                        st.session_state["edit_media_active"] = False
                        st.rerun()
                else:
                    if st.button("✏️ Editar Medias", key="btn_editar_media", use_container_width=True):
                        st.session_state["edit_media_active"] = True
                        st.rerun()

        midias = get_media_by_cliente(cliente_id)
        midias_por_pagina = 10
        total_paginas = (len(midias) - 1) // midias_por_pagina + 1

        pagina = st.number_input("📄 Página", min_value=1, max_value=total_paginas, value=1, step=1)
        inicio = (pagina - 1) * midias_por_pagina
        fim = inicio + midias_por_pagina
        midias_pagina = midias[inicio:fim]

        for m_id, m_nome, m_url, m_tipologia, m_segmento in midias_pagina:
            st.markdown(f"""
                <div style='border: 1px solid #DDD; border-radius: 10px; padding: 10px; margin-bottom: 10px;'>
                    <b>📌 Nome:</b> {m_nome}<br>
                    <b>🔗 URL:</b> <a href="{m_url}" target="_blank">{m_url}</a><br>
                    <b>🏷️ Tipologia:</b> {m_tipologia} &nbsp;&nbsp; 
                    <b>📂 Segmento:</b> {m_segmento}
                </div>
            """, unsafe_allow_html=True)

        if role in ("admin", "account") and st.session_state["edit_media_active"]:
            st.markdown("### ✏️ Editar Todas as Medias")
            for m_id, m_nome, m_url, m_tipologia, m_segmento in midias:
                st.markdown(f"####Mídia ID {m_id}")
                novo_nome = st.text_input("Nome", value=m_nome, key=f"nome_{m_id}")
                novo_tipologia = st.selectbox(
                    "Tipologia",
                    ["Print", "Online", "TV", "Rádio"],
                    index=["Print", "Online", "TV", "Rádio"].index(m_tipologia),
                    key=f"tipo_{m_id}"
                )
                novo_segmento = st.selectbox(
                    "Segmento",
                    ["Tecnologia", "Rural", "Saúde"],
                    index=["Tecnologia", "Rural", "Saúde"].index(m_segmento),
                    key=f"seg_{m_id}"
                )
                col_save, col_cancel = st.columns([1, 1])
                with col_save:
                    if st.button("💾 Atualizar", key=f"save_{m_id}"):
                        cursor.execute("""
                            UPDATE media
                            SET nome=%s, tipologia=%s, segmento=%s
                            WHERE id=%s
                        """, (novo_nome, novo_tipologia, novo_segmento, m_id))
                        conn.commit()
                        st.success(f"✅ Media ID {m_id} atualizada com sucesso.")
                        log_action(email, "edição de mídia", f"mídia ID: {m_id}")
                with col_cancel:
                    if st.button("❌ Cancelar edição", key=f"cancel_{m_id}"):
                        st.session_state["edit_media_active"] = False

                        st.rerun()



# ----------- Página Admin DB -----------
elif menu == "Admin DB" and st.session_state.user["is_admin"]:
    st.title("📂 Acesso Base de Dados")

    # Diagnóstico: ver tabelas disponíveis (MySQL)
    cursor.execute("SHOW TABLES;")
    tabelas = cursor.fetchall()
    tabelas_nomes = [t[0] for t in tabelas]
    if not tabelas_nomes:
        st.warning("🚫 Nenhuma tabela encontrada na base de dados.")
        st.stop()

    selected_table = st.selectbox("Selecionar Tabela", tabelas_nomes, key="admin_select_table")

    try:
        query = f"SELECT * FROM {selected_table}"
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        if rows:
            df = pd.DataFrame(rows, columns=columns)
            st.dataframe(df)
        else:
            st.info("📭 A tabela está vazia.")
    except Exception as e:
        st.error(f"❌ Erro ao aceder à tabela '{selected_table}': {e}")




# ----------- Página Gestão Utilizadores -----------

if menu == "Gestão Utilizadores" and st.session_state.user["role_name"] == "admin":
    st.title("Gestão de Utilizadores")
    users = get_all_users()
    roles = get_roles()
    role_dict = {r[1]: r[0] for r in roles}

    for user in users:
        uid, uname, uemail, urole = user
        col1, col2 = st.columns([3, 2])
        with col1:
            st.text(f"{uname} ({uemail})")
        with col2:
            new_role = st.selectbox("", options=role_dict.keys(), index=list(role_dict).index(urole), key=f"role_{uid}")
            if st.button("Atualizar", key=f"update_{uid}"):
                update_user_role(uid, role_dict[new_role])
                st.success("Função atualizada!")
                log_action(st.session_state.user["email"], "alteração função", f"utilizador ID: {uid}")
                st.rerun()





# ----------- Página de Logs ----------

elif menu == "Logs":
    if get_role_name(st.session_state.user["role_id"]) != "admin":
        st.warning(" Apenas administradores podem aceder aos logs.")
        st.stop()

    st.markdown(" Registo de Ações")
    logs_df = pd.read_sql_query("SELECT * FROM logs ORDER BY timestamp DESC", conn)

    from st_aggrid import AgGrid, GridOptionsBuilder

    gb = GridOptionsBuilder.from_dataframe(logs_df)
    gb.configure_pagination()
    gb.configure_columns(["timestamp", "user_email", "action", "target"])
    gb.configure_default_column(groupable=True)
    grid_options = gb.build()

    AgGrid(logs_df, gridOptions=grid_options, height=500, theme="streamlit")



# ----------- Lista de Mídia ----------
elif menu == "Media" and role_name in ["admin", "account"]:
    st.markdown("<h2 style='color:#4A90E2;'>📺 Gestão e Visualização de Media</h2>", unsafe_allow_html=True)

    clientes = get_clientes(None, role_name)
    clientes_dict = {c[1]: c[0] for c in clientes}
    cliente_selecionado_nome = st.selectbox("📁 Selecione a Empresa", list(clientes_dict.keys()))
    cliente_id = clientes_dict[cliente_selecionado_nome]

    with st.expander("➕ Adicionar Nova Media"):
        with st.form("form_adicionar_midia"):
            nome_midia = st.text_input("Nome da Mídia")
            url_midia = st.text_input("URL da Mídia")
            tipologia = st.selectbox("Tipologia", ["Print", "Online", "TV", "Rádio"])
            segmento = st.selectbox("Segmento", ["Tecnologia", "Político", "Saúde", "Outro"])
            tier = st.selectbox("Tier", [1, 2, 3, 4], index=3)
            submit = st.form_submit_button("Salvar")
            if submit:
                if nome_midia and url_midia and cliente_id:
                 insert_media(nome_midia, url_midia, cliente_id, tipologia, segmento, tier)
                 st.success("✅ Media adicionada com sucesso!")
                 st.rerun()
            else:
                 st.error("❌ Preencha todos os campos obrigatórios.")

    # Filtros
    st.markdown("<hr><h3 style='color:#4A90E2;'>🔍 Filtros de Pesquisa</h3>", unsafe_allow_html=True)
    query = """
        SELECT media.id AS ID, media.nome AS Nome, media.url AS URL, media.tipologia, 
               media.segmento, media.tier, clientes.nome AS Empresa, media.cliente_id
        FROM media
        JOIN clientes ON media.cliente_id = clientes.id
    """
    df_media = pd.read_sql_query(query, conn)

    with st.expander("🎛️ Filtros", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            filtro_nome = st.text_input("🔎 Nome da Mídia")
        with col2:
            filtro_tipologia = st.multiselect("📺 Tipologia", df_media["tipologia"].unique())
        with col3:
            filtro_segmento = st.multiselect("🏷️ Segmento", df_media["segmento"].unique())
        with col4:
            filtro_tier = st.multiselect("⭐ Tier", sorted(df_media["tier"].unique()))

    if filtro_nome:
        df_media = df_media[df_media["Nome"].str.contains(filtro_nome, case=False, na=False)]

    for filtro, coluna in zip([filtro_tipologia, filtro_segmento, filtro_tier],
                              ["tipologia", "segmento", "tier"]):
        if filtro:
            df_media = df_media[df_media[coluna].isin(filtro)]

    # Paginação
    MIDIAS_POR_PAGINA = 10
    pag_total = max(1, math.ceil(len(df_media) / MIDIAS_POR_PAGINA))

    if "pagina" not in st.session_state:
        st.session_state["pagina"] = 1

    pag_atual = st.session_state["pagina"]
    start_idx = (pag_atual - 1) * MIDIAS_POR_PAGINA
    end_idx = start_idx + MIDIAS_POR_PAGINA
    midias_pagina = df_media.iloc[start_idx:end_idx]

    st.markdown("<hr><h3 style='color:#4A90E2;'>📄 Lista de Medias</h3>", unsafe_allow_html=True)

    for _, row in midias_pagina.iterrows():
        midia_id = row['ID']
        nome, url, tipologia, segmento, tier = row['Nome'], row['URL'], row['tipologia'], row['segmento'], row['tier']
        with st.container():
            st.markdown(
                f"""
                <div style='
                    background-color: #ffffff;
                    border: 1px solid #e0e0e0;
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 15px;
                    box-shadow: 0px 4px 8px rgba(0,0,0,0.05);
                '>
                    <h4 style='color: #2c3e50; margin-bottom: 10px;'>{nome}</h4>
                    <p style='margin: 0; font-size: 18px;'><strong>🌐 URL:</strong> <a href='{url}' target='_blank' style='color: #3498db;'>{url}</a></p>
                    <p style='margin: 0; font-size: 18px;'><strong>📺 Tipologia:</strong> {tipologia}</p>
                    <p style='margin: 0; font-size: 18px;'><strong>🏷️ Segmento:</strong> {segmento}</p>
                    <p style='margin: 0; font-size: 18px;'><strong>⭐ Tier:</strong> {tier}</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✏️ Editar", key=f"editar_{midia_id}"):
                    st.session_state[f"editando_{midia_id}"] = True
            with col2:
                if st.button("❌ Eliminar", key=f"eliminar_{midia_id}"):
                    eliminar_midia(midia_id)
                    st.success(f"Media '{nome}' eliminada com sucesso!")
                    st.rerun()

        if st.session_state.get(f"editando_{midia_id}"):
            with st.form(f"form_edit_{midia_id}"):
                novo_nome = st.text_input("📝 Nome da Mídia", value=nome)
                novo_url = st.text_input("🔗 URL", value=url)
                nova_tipologia = st.selectbox("📺 Tipologia", ["Print", "Online", "TV", "Rádio"],
                                              index=["Print", "Online", "TV", "Rádio"].index(tipologia))
                novo_segmento = st.selectbox("🏷️ Segmento", ["Tecnologia", "Político", "Saúde", "Outro"],
                                             index=["Tecnologia", "Político", "Saúde", "Outro"].index(segmento))
                novo_tier = st.selectbox("Tier", [1, 2, 3, 4], index=tier-1)

                colx, coly = st.columns(2)
                with colx:
                    if st.form_submit_button("💾 Guardar"):
                        update_media(midia_id, novo_nome, novo_url, nova_tipologia, novo_segmento, novo_tier)
                        st.success("✅ Media atualizada com sucesso!")
                        st.session_state[f"editando_{midia_id}"] = False
                        st.rerun()
                with coly:
                    if st.form_submit_button("❌ Cancelar"):
                        st.session_state[f"editando_{midia_id}"] = False
                        st.rerun()

    # Paginação visual estilo Google
    MAX_BOTOES = 5
    metade = MAX_BOTOES // 2
    inicio = max(1, pag_atual - metade)
    fim = min(pag_total, pag_atual + metade)

    if fim - inicio + 1 < MAX_BOTOES:
        if inicio == 1:
            fim = min(pag_total, inicio + MAX_BOTOES - 1)
        elif fim == pag_total:
            inicio = max(1, fim - MAX_BOTOES + 1)

    with st.container():
        cols = st.columns(MAX_BOTOES + 4)

        if cols[0].button("⏮", disabled=(pag_atual == 1)):
            st.session_state["pagina"] = 1
            st.rerun()

        if cols[1].button("⬅", disabled=(pag_atual == 1)):
            st.session_state["pagina"] = pag_atual - 1
            st.rerun()

        idx = 2
        for i in range(inicio, fim + 1):
            label = f"**{i}**" if i == pag_atual else str(i)
            if cols[idx].button(label, key=f"pag_{i}"):
                st.session_state["pagina"] = i
                st.rerun()
            idx += 1

        if cols[idx].button("➡", disabled=(pag_atual == pag_total)):
            st.session_state["pagina"] = pag_atual + 1
            st.rerun()
        idx += 1

        if cols[idx].button("⏭", disabled=(pag_atual == pag_total)):
            st.session_state["pagina"] = pag_total
            st.rerun()



# ----------- SCRAPER OFFLINE AUTOMATICO ----------
if menu == "Resultados Automáticos":
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, titulo, url, data, keyword, cliente_id, site FROM noticias_sugeridas ORDER BY data DESC")
    resultados = cursor.fetchall()

    st.title("📰 Resultados Automáticos")

    for id_, titulo, url, data, keyword, cliente_id, site in resultados:
        with st.expander(f"🔗 {titulo}"):
            st.write(f"**URL:** [{url}]({url})")
            st.write(f"📅 Data: {data}")
            st.write(f"🔑 Palavra-chave: {keyword}")
            st.write(f"🌐 Site: {site}")

            col1, col2 = st.columns(2)

            with col1:
                if st.button(f"✅ Guardar como mídia", key=f"guardar_{id_}"):
                    # Guardar na tabela mídia
                    cursor.execute("""
                        INSERT OR IGNORE INTO media (nome, url, cliente_id, tipologia, segmento, tier)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (titulo, url, cliente_id or 1, "Sugerida", keyword, 4))
                    cursor.execute("DELETE FROM noticias_sugeridas WHERE id = %s", (id_,))
                    conn.commit()
                    st.success("Guardado com sucesso!")
                    st.experimental_rerun()

            with col2:
                if st.button(f"❌ Ignorar", key=f"ignorar_{id_}"):
                    cursor.execute("DELETE FROM noticias_sugeridas WHERE id = %s", (id_,))
                    conn.commit()
                    st.warning("Notícia ignorada.")
                    st.rerun()

    conn.close()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

