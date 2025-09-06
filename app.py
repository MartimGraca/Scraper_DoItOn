
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
# … outros imports …
from mediaDB_scraper import search_media, enrich_previews, healthcheck  # novo import para o modo Minha Base de Media
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
from auth import get_user, check_password, register_user, log_action, login_tentativas_check, login_falhou, get_role_name, is_admin_email
import os
from wipe_all_users import wipe_users_once

wipe_users_once()


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
    
def update_user_role(user_id, new_role_id):
    # Garantia de segurança: não permitir alterar admins definidos no .env
    cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Utilizador não encontrado.")

    email = row[0]
    if is_admin_email(email):
        # Opcional: registar tentativa
        log_action(
            st.session_state.user["email"] if "user" in st.session_state else "",
            "tentativa alteração função bloqueada",
            f"utilizador ID: {user_id}"
        )
        raise PermissionError("Não é permitido alterar a role de emails admin definidos no .env.")

    cursor.execute("UPDATE users SET role_id = %s WHERE id = %s", (new_role_id, user_id))
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

# CSS leve para não quebrar texto de botões
st.markdown("""
    <style>
    .stButton>button { white-space: nowrap; }
    .small-caption { font-size: 0.85rem; color: #666; }
    </style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([9, 1])
with col1:
    st.image("https://doiton.agency/wp-content/uploads/2022/10/logo_doiton.jpg")
with col2:
    st.image("https://www.w3schools.com/w3images/avatar2.png", width=40)
    st.write(f"👤 {st.session_state.user['username']}")
    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()

    # -------- Alterar password (sem pedir password atual) --------
    def _password_score(pw: str) -> tuple[int, list[str]]:
        tips = []
        score = 0
        if not pw:
            return 0, ["Digite uma password."]
        length = len(pw)
        has_lower = any(c.islower() for c in pw)
        has_upper = any(c.isupper() for c in pw)
        has_digit = any(c.isdigit() for c in pw)
        has_special = any(not c.isalnum() for c in pw)

        if length >= 8: score += 1
        if length >= 12: score += 1
        if has_lower and has_upper: score += 1
        if has_digit: score += 1
        if has_special: score += 1

        if length < 8: tips.append("Use pelo menos 8 caracteres.")
        if not (has_lower and has_upper): tips.append("Misture maiúsculas e minúsculas.")
        if not has_digit: tips.append("Inclua números.")
        if not has_special: tips.append("Inclua símbolos (ex.: !@#).")
        return score, tips

    def _gen_password(n: int = 14) -> str:
        import secrets, string
        pool = [
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^&*()-_=+[]{};:,.?/")
        ]
        restante = n - len(pool)
        all_chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{};:,.?/"
        pool.extend(secrets.choice(all_chars) for _ in range(max(0, restante)))
        secrets.SystemRandom().shuffle(pool)
        return "".join(pool)

    with st.expander("Alterar password", expanded=False):
        # Aviso de segurança
        st.caption("Atenção: esta ação não pede a password atual. Use com cuidado.")

        show = st.checkbox("Mostrar passwords", value=False, key="pw_show_toggle_no_current")

        gen_col1, gen_col2 = st.columns([1, 1])
        with gen_col1:
            if st.button("Gerar password segura", key="btn_gen_pw_no_current"):
                generated = _gen_password()
                st.session_state["pw_nova"] = generated
                st.session_state["pw_confirma"] = generated
                st.info("Password gerada e preenchida nos campos.")
        with gen_col2:
            pass

        # Formulário sem pedir password atual
        with st.form("form_change_password_no_current"):
            t = "text" if show else "password"
            new_pw = st.text_input("Nova password", type=t, key="pw_nova", placeholder="Mín. 8 caracteres")
            confirm_pw = st.text_input("Confirmar nova password", type=t, key="pw_confirma", placeholder="Repita a nova password")

            score, tips = _password_score(st.session_state.get("pw_nova", ""))
            st.progress(score / 5.0 if score else 0.0)
            st.caption(f"Força: {score}/5")
            if tips and st.session_state.get("pw_nova", ""):
                st.caption("Sugestões para melhorar:")
                for tip in tips:
                    st.caption(f"- {tip}")

            matches = st.session_state.get("pw_nova", "") == st.session_state.get("pw_confirma", "")
            long_enough = len(st.session_state.get("pw_nova", "")) >= 8
            can_submit = matches and long_enough

            submit_change = st.form_submit_button("Atualizar password", use_container_width=True, disabled=not can_submit)

            if submit_change:
                from auth import hash_password, log_action
                try:
                    new_hash = hash_password(st.session_state["pw_nova"])
                    cursor.execute(
                        "UPDATE users SET password_hash = %s WHERE id = %s",
                        (new_hash, st.session_state.user["id"])
                    )
                    conn.commit()
                    st.success("✅ Password atualizada com sucesso.")
                    log_action(st.session_state.user["email"], "alteração de password (sem verificação)", "utilizador")
                    # Limpar campos
                    st.session_state["pw_nova"] = ""
                    st.session_state["pw_confirma"] = ""
                except Exception as e:
                    st.error(f"Erro ao atualizar password:{e}")


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
import asyncio
nest_asyncio.apply()

if menu == "Scraper" and role_name in ["admin", "account"]:
    st.title("Web Scraper")

    # Estados iniciais
    st.session_state.setdefault("resultados_direto", [])
    st.session_state.setdefault("resultados_scraper", [])
    st.session_state.setdefault("mdb_resultados", [])
    st.session_state.setdefault("mdb_busca", [])

    # Escolha do modo primeiro (assim podemos esconder "Empresa" no modo interno)
    modo_scraper = st.radio(
        "Escolha o modo de scraping:",
        ["Website Direto", "Google Notícias", "Minha Base de Media"],
        horizontal=True,
        key="scraper_mode_radio"
    )

    # Carregar clientes apenas se forem necessários (para WD / GN)
    clientes = get_clientes(email=st.session_state.user["email"], role=role_name)
    if not clientes:
        st.warning("⚠️ Nenhum cliente encontrado. Contacte o administrador para criar clientes.")
        st.stop()

    # Mostrar 'Empresa' apenas para Website Direto e Google Notícias
    cliente_id = None
    keywords_atuais = ""
    if modo_scraper in ("Website Direto", "Google Notícias"):
        nomes_clientes = [c[1] for c in clientes]
        empresa = st.selectbox("Empresa", nomes_clientes, key="scraper_empresa_select")
        cliente_id = next((c[0] for c in clientes if c[1] == empresa), None)
        for c in clientes:
            if c[1] == empresa:
                keywords_atuais = c[4] or ""
                break

    # ---------- WEBSITE DIRETO ----------
    if modo_scraper == "Website Direto":
        # Mantém a tua lógica atual tal como está abaixo (não alterado)
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
                    nome = st.text_input("📝 Nome da Media", nome_sugerido, key=f"wd_nome_{i}")
                    tipologia = st.selectbox("📺 Tipologia", ["Online", "TV", "Rádio", "Imprensa"], key=f"wd_tipo_{i}")
                    segmento = st.selectbox("🏷️ Segmento", ["Tecnologia", "Político", "Saúde", "Outro"], key=f"wd_seg_{i}")
                    tier_automatico = obter_tier_por_nome(nome)
                    tier_default = tier_automatico if tier_automatico else 4
                    tier = st.selectbox("⭐ Tier", [1, 2, 3, 4], index=tier_default - 1, key=f"wd_tier_{i}")

                    state_base = f"wd_{i}"

                    if st.button("💾 Guardar", key=f"wd_guardar_{i}"):
                        existente = media_existe(nome, cliente_id)

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

                        if existente:
                            st.session_state[f"{state_base}_pending_nome"] = nome
                            st.session_state[f"{state_base}_pending_tipologia"] = tipologia
                            st.session_state[f"{state_base}_pending_segmento"] = segmento
                            st.session_state[f"{state_base}_pending_tier"] = tier
                            st.session_state[f"{state_base}_pending_link"] = link
                            st.session_state[f"{state_base}_pending_id"] = existente[0]

                            st.session_state[f"{state_base}_existente_nome"] = existente[1]
                            st.session_state[f"{state_base}_existente_url"] = existente[2]
                            st.session_state[f"{state_base}_existente_tipologia"] = existente[3]
                            st.session_state[f"{state_base}_existente_segmento"] = existente[4]
                            st.session_state[f"{state_base}_existente_tier"] = existente[5]

                            st.session_state[f"{state_base}_show_confirm"] = True
                            st.rerun()
                        else:
                            insert_media(nome, link, cliente_id, tipologia, segmento, tier)
                            st.success("Guardado com sucesso!")
                            st.rerun()

                    if st.session_state.get(f"{state_base}_show_confirm", False):
                        pend_id = st.session_state.get(f"{state_base}_pending_id")
                        pend_nome = st.session_state.get(f"{state_base}_pending_nome")
                        pend_url = st.session_state.get(f"{state_base}_pending_link")
                        pend_tipologia = st.session_state.get(f"{state_base}_pending_tipologia")
                        pend_segmento = st.session_state.get(f"{state_base}_pending_segmento")
                        pend_tier = st.session_state.get(f"{state_base}_pending_tier")

                        exist_nome = st.session_state.get(f"{state_base}_existente_nome")
                        exist_url = st.session_state.get(f"{state_base}_existente_url")
                        exist_tipologia = st.session_state.get(f"{state_base}_existente_tipologia")
                        exist_segmento = st.session_state.get(f"{state_base}_existente_segmento")
                        exist_tier = st.session_state.get(f"{state_base}_existente_tier")

                        def clear_pending(prefix: str):
                            for suf in [
                                "pending_nome", "pending_link", "pending_tipologia",
                                "pending_segmento", "pending_tier", "pending_id",
                                "existente_nome", "existente_url", "existente_tipologia",
                                "existente_segmento", "existente_tier", "show_confirm"
                            ]:
                                st.session_state.pop(f"{prefix}_{suf}", None)

                        st.warning("⚠️ Já existe uma media com este nome/URL para esta empresa.")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("#### 📄 Media Existente")
                            st.write(f"**Nome:** {exist_nome}")
                            st.write(f"**URL:** {exist_url}")
                            st.write(f"**Tipologia:** {exist_tipologia}")
                            st.write(f"**Segmento:** {exist_segmento}")
                            st.write(f"**Tier:** {exist_tier}")
                        with col2:
                            st.markdown("#### ✍️ Nova Media")
                            st.write(f"**Nome:** {pend_nome}")
                            st.write(f"**URL:** {pend_url}")
                            st.write(f"**Tipologia:** {pend_tipologia}")
                            st.write(f"**Segmento:** {pend_segmento}")
                            st.write(f"**Tier:** {pend_tier}")

                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✅ Confirmar e Substituir", key=f"wd_confirma_{i}"):
                                update_media(
                                    media_id=pend_id,
                                    nome=pend_nome,
                                    url=pend_url,
                                    tipologia=pend_tipologia,
                                    segmento=pend_segmento,
                                    tier=pend_tier
                                )
                                st.success("Media atualizada com sucesso!")
                                clear_pending(state_base)
                                st.rerun()
                        with c2:
                            if st.button("❌ Cancelar", key=f"wd_cancelar_{i}"):
                                st.info("Operação cancelada.")
                                clear_pending(state_base)
                                st.rerun()

    # ---------- GOOGLE NEWS ----------
    elif modo_scraper == "Google Notícias":
        # Mantém a tua lógica atual tal como está (não alterado)
        st.subheader("🔍 Pesquisa no Google Notícias")

        keyword = st.text_input("Insira palavras-chave separadas por vírgula:", value=keywords_atuais)
        filtro_tempo = st.selectbox(
            "Filtrar por período de tempo:",
            ["Na última hora", "Últimas 24 horas", "Última semana", "Último mês", "Último ano"]
        )

        if st.button("🔎 Pesquisar"):
            if not cliente_id:
                st.warning("Por favor, selecione ou crie um cliente antes de continuar.")
            else:
                st.session_state["resultados_scraper"] = []
                for kw in [k.strip() for k in keyword.split(",") if k.strip()]:
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
                    nome = st.text_input("📝 Nome da Media", nome_sugerido, key=f"gn_nome_{i}")
                    tipologia = st.selectbox("📺 Tipologia", ["Online", "TV", "Rádio", "Imprensa"], key=f"gn_tipo_{i}")
                    segmento = st.selectbox("🏷️ Segmento", ["Tecnologia", "Político", "Saúde", "Outro"], key=f"gn_seg_{i}")
                    tier_automatico = obter_tier_por_nome(nome)
                    tier_default = tier_automatico if tier_automatico else 4
                    tier = st.selectbox("⭐ Tier", [1, 2, 3, 4], index=tier_default - 1, key=f"gn_tier_{i}")

                    state_base = f"gn_{kw}_{i}"

                    if st.button("💾 Guardar", key=f"gn_guardar_{i}"):
                        existente = media_existe(nome, cliente_id)
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

                        if existente:
                            st.session_state[f"{state_base}_pending_nome"] = nome
                            st.session_state[f"{state_base}_pending_tipologia"] = tipologia
                            st.session_state[f"{state_base}_pending_segmento"] = segmento
                            st.session_state[f"{state_base}_pending_tier"] = tier
                            st.session_state[f"{state_base}_pending_link"] = link
                            st.session_state[f"{state_base}_pending_id"] = existente[0]

                            st.session_state[f"{state_base}_existente_nome"] = existente[1]
                            st.session_state[f"{state_base}_existente_url"] = existente[2]
                            st.session_state[f"{state_base}_existente_tipologia"] = existente[3]
                            st.session_state[f"{state_base}_existente_segmento"] = existente[4]
                            st.session_state[f"{state_base}_existente_tier"] = existente[5]

                            st.session_state[f"{state_base}_show_confirm"] = True
                            st.rerun()
                        else:
                            insert_media(nome, link, cliente_id, tipologia, segmento, tier)
                            st.success("Guardado com sucesso!")
                            st.rerun()

                    if st.session_state.get(f"{state_base}_show_confirm", False):
                        pend_id = st.session_state.get(f"{state_base}_pending_id")
                        pend_nome = st.session_state.get(f"{state_base}_pending_nome")
                        pend_url = st.session_state.get(f"{state_base}_pending_link")
                        pend_tipologia = st.session_state.get(f"{state_base}_pending_tipologia")
                        pend_segmento = st.session_state.get(f"{state_base}_pending_segmento")
                        pend_tier = st.session_state.get(f"{state_base}_pending_tier")

                        exist_nome = st.session_state.get(f"{state_base}_existente_nome")
                        exist_url = st.session_state.get(f"{state_base}_existente_url")
                        exist_tipologia = st.session_state.get(f"{state_base}_existente_tipologia")
                        exist_segmento = st.session_state.get(f"{state_base}_existente_segmento")
                        exist_tier = st.session_state.get(f"{state_base}_existente_tier")

                        def clear_pending(prefix: str):
                            for suf in [
                                "pending_nome", "pending_link", "pending_tipologia",
                                "pending_segmento", "pending_tier", "pending_id",
                                "existente_nome", "existente_url", "existente_tipologia",
                                "existente_segmento", "existente_tier", "show_confirm"
                            ]:
                                st.session_state.pop(f"{prefix}_{suf}", None)

                        st.warning("⚠️ Já existe uma media com este nome/URL para esta empresa.")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("#### 📄 Media Existente")
                            st.write(f"**Nome:** {exist_nome}")
                            st.write(f"**URL:** {exist_url}")
                            st.write(f"**Tipologia:** {exist_tipologia}")
                            st.write(f"**Segmento:** {exist_segmento}")
                            st.write(f"**Tier:** {exist_tier}")
                        with col2:
                            st.markdown("#### ✍️ Nova Media")
                            st.write(f"**Nome:** {pend_nome}")
                            st.write(f"**URL:** {pend_url}")
                            st.write(f"**Tipologia:** {pend_tipologia}")
                            st.write(f"**Segmento:** {pend_segmento}")
                            st.write(f"**Tier:** {pend_tier}")

                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✅ Confirmar e Substituir", key=f"gn_confirma_{i}"):
                                update_media(
                                    media_id=pend_id,
                                    nome=pend_nome,
                                    url=pend_url,
                                    tipologia=pend_tipologia,
                                    segmento=pend_segmento,
                                    tier=pend_tier
                                )
                                st.success("Media atualizada com sucesso!")
                                clear_pending(state_base)
                                st.rerun()
                        with c2:
                            if st.button("❌ Cancelar", key=f"gn_cancelar_{i}"):
                                st.info("Operação cancelada.")
                                clear_pending(state_base)
                                st.rerun()

    # ---------- MINHA BASE DE MEDIA (pesquisa direta na BD, visual "scraper") ----------
    elif modo_scraper == "Minha Base de Media":
        st.subheader("🗂️ Web Scraper da Minha BD")
        

        # UI de pesquisa (sem Empresa)
        keywords_raw = st.text_input("Palavras‑chave (separa por vírgulas)", key="mdb_kw")
        match_mode = st.radio("Corresponder", ["Qualquer palavra", "Todas as palavras"], horizontal=True, key="mdb_match")

        col_campos1, col_campos2, col_filtros = st.columns([1.2, 1.2, 1])
        with col_campos1:
            campo_nome = st.checkbox("Procurar em Nome", value=True, key="mdb_campo_nome")
            campo_url = st.checkbox("Procurar em URL", value=True, key="mdb_campo_url")
        with col_campos2:
            campo_tipologia = st.checkbox("Procurar em Tipologia", value=False, key="mdb_campo_tipologia")
            campo_segmento = st.checkbox("Procurar em Segmento", value=False, key="mdb_campo_segmento")
        with col_filtros:
            tipologia_filtro = st.selectbox("Filtrar Tipologia (opcional)", ["Qualquer", "Online", "TV", "Rádio", "Imprensa"], key="mdb_filtro_tipologia")
            segmento_filtro = st.selectbox("Filtrar Segmento (opcional)", ["Qualquer", "Tecnologia", "Político", "Saúde", "Outro"], key="mdb_filtro_segmento")
            tier_filtro = st.selectbox("Filtrar Tier (opcional)", ["Qualquer", 1, 2, 3, 4], key="mdb_filtro_tier")

        limite_resultados = st.number_input("Máx. resultados", min_value=1, max_value=1000, value=200, step=10, key="mdb_limit")

        # Botão de pesquisa
        if st.button("🔎 Pesquisar na BD", key="mdb_btn_search"):
            campos = []
            if campo_nome: campos.append("nome")
            if campo_url: campos.append("url")
            if campo_tipologia: campos.append("tipologia")
            if campo_segmento: campos.append("segmento")
            if not campos:
                campos = ["nome", "url"]

            try:
                rows = search_media(
                    cursor=cursor,  # usa o cursor já aberto na app
                    keywords_raw=keywords_raw or "",
                    fields=campos,
                    match_all=(match_mode == "Todas as palavras"),
                    tipologia_filter=tipologia_filtro,
                    segmento_filter=segmento_filtro,
                    tier_filter=(None if tier_filtro == "Qualquer" else int(tier_filtro)),
                    limit_results=int(limite_resultados),
                )
            except Exception as e:
                st.exception(e)
                rows = []

            # Enriquecer com favicon/og image para parecer “scraped”
            try:
                rows = enrich_previews(rows)
            except Exception:
                pass

            st.session_state["mdb_busca"] = rows
            st.success(f"Encontrados {len(rows)} registos.")

        # Render dos resultados com edição e confirmação
        for i, row in enumerate(st.session_state.get("mdb_busca", [])):
            rid = row["id"]
            titulo_card = row["nome"] or f"ID {rid}"
            favicon = row.get("favicon")
            og_image = row.get("og_image")

            with st.expander(f"{i+1}. {titulo_card} (ID {rid})"):
                cols = st.columns([0.1, 0.8, 0.1])
                with cols[0]:
                    if favicon:
                        st.image(favicon, width=24)
                with cols[1]:
                    st.markdown(f"[{row['url'] or 'sem URL'}]({row['url'] or '#'})", unsafe_allow_html=True)
                    st.caption(f"Tipologia: {row['tipologia'] or '—'} • Segmento: {row['segmento'] or '—'} • Tier: {row['tier'] or '—'}")
                with cols[2]:
                    if og_image:
                        st.image(og_image, width=48)

                # Inputs de edição
                nome = st.text_input("📝 Nome da Media", value=row["nome"] or "", key=f"mdb_edit_nome_{rid}")
                url = st.text_input("🌐 URL", value=row["url"] or "", key=f"mdb_edit_url_{rid}")
                tipologia = st.selectbox(
                    "📺 Tipologia", ["Online", "TV", "Rádio", "Imprensa"],
                    index=(["Online","TV","Rádio","Imprensa"].index(row["tipologia"]) if row["tipologia"] in ["Online","TV","Rádio","Imprensa"] else 0),
                    key=f"mdb_edit_tip_{rid}"
                )
                segmento = st.selectbox(
                    "🏷️ Segmento", ["Tecnologia", "Político", "Saúde", "Outro"],
                    index=(["Tecnologia","Político","Saúde","Outro"].index(row["segmento"]) if row["segmento"] in ["Tecnologia","Político","Saúde","Outro"] else 0),
                    key=f"mdb_edit_seg_{rid}"
                )
                tier = st.selectbox(
                    "⭐ Tier", [1, 2, 3, 4],
                    index=([1,2,3,4].index(int(row["tier"])) if row["tier"] in [1,2,3,4] else 3),
                    key=f"mdb_edit_tier_{rid}"
                )

                state_base = f"mdb_edit_{rid}"

                if st.button("💾 Guardar alterações", key=f"mdb_save_{rid}"):
                    st.session_state[f"{state_base}_pending"] = {
                        "id": rid,
                        "nome": nome,
                        "url": url,
                        "tipologia": tipologia,
                        "segmento": segmento,
                        "tier": int(tier),
                        "cliente_id": row["cliente_id"],
                    }
                    st.session_state[f"{state_base}_existente"] = row
                    st.session_state[f"{state_base}_show_confirm"] = True
                    st.rerun()

                if st.session_state.get(f"{state_base}_show_confirm", False):
                    pend = st.session_state.get(f"{state_base}_pending")
                    ex = st.session_state.get(f"{state_base}_existente")

                    def clear_state():
                        for k in [f"{state_base}_pending", f"{state_base}_existente", f"{state_base}_show_confirm"]:
                            st.session_state.pop(k, None)

                    st.warning("⚠️ Confirmar substituição deste registo:")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("#### 📄 Atual")
                        st.write(f"Nome: {ex['nome']}")
                        st.write(f"URL: {ex['url']}")
                        st.write(f"Tipologia: {ex['tipologia']}")
                        st.write(f"Segmento: {ex['segmento']}")
                        st.write(f"Tier: {ex['tier']}")
                    with col2:
                        st.markdown("#### ✍️ Novo")
                        st.write(f"Nome: {pend['nome']}")
                        st.write(f"URL: {pend['url']}")
                        st.write(f"Tipologia: {pend['tipologia']}")
                        st.write(f"Segmento: {pend['segmento']}")
                        st.write(f"Tier: {pend['tier']}")

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Confirmar e Substituir", key=f"mdb_confirm_{rid}"):
                            # Anti-duplicação básica
                            try:
                                dup = media_existe(pend["nome"], pend["cliente_id"])
                            except Exception:
                                dup = None
                            if dup and dup[0] != ex["id"]:
                                st.warning("Já existe uma media com este nome para este cliente.")
                                st.stop()

                            if pend["url"] and pend["url"] != ex["url"]:
                                ex_url = media_por_url(pend["url"])
                                if ex_url and ex_url["id"] != ex["id"]:
                                    st.warning("Esta URL já está associada a outra media.")
                                    st.stop()

                            update_media(
                                media_id=ex["id"],
                                nome=pend["nome"],
                                url=pend["url"],
                                tipologia=pend["tipologia"],
                                segmento=pend["segmento"],
                                tier=pend["tier"]
                            )
                            st.success("Media atualizada com sucesso!")
                            clear_state()
                            st.rerun()
                    with c2:
                        if st.button("❌ Cancelar", key=f"mdb_cancel_{rid}"):
                            st.info("Operação cancelada.")
                            clear_state()
                            st.rerun()
# ----------- Página Dashboard (Placeholder) -----------
                elif menu == "Dashboard":
                   st.title("\U0001F4CA Dashboard de Clientes")







# ----------- Página Clientes -----------
elif menu == "Clientes":
    st.markdown("### 📁 Gestão de Clientes")

    role = st.session_state.user["role_name"]
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
            # Removido: seleção de Tier para clientes
            email_cliente = st.text_input("Email associado ao cliente", key="new_email_cliente")
            logo_file = st.file_uploader("Logo", type=["png", "jpg", "jpeg"], key="new_logo")

            if st.button("💾 Salvar Empresa", use_container_width=True):
                if nome_empresa and perfil and email_cliente:
                    logo_bytes = logo_file.read() if logo_file else None
                    # Inserir sem a coluna 'tier' -> usa o DEFAULT da BD
                    cursor.execute("""
                        INSERT INTO clientes (nome, perfil, keywords, logo, email)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (nome_empresa, perfil, "", logo_bytes, email_cliente))
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
        # Mantemos o fetch com 'tier' mas não o mostramos nem editamos
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
            # Removido: linha de Tier do cliente
            st.markdown(f"**Email:** [{email_assoc}](mailto:{email_assoc})")
            st.markdown(f"**Keywords:** {keywords if keywords else '—'}")

        if role in ("admin", "account"):
            with st.expander("✏️ Editar Cliente"):
                novo_nome = st.text_input("Nome", nome, key="novo_nome")
                novo_perfil = st.text_input("Perfil", perfil, key="novo_perfil")
                # Removido: edição de Tier do cliente
                novas_keywords = st.text_input("Keywords", keywords or "", key="novas_keywords")

                if st.button("💾 Guardar Alterações", key="update_cliente_btn"):
                    # Atualizar sem tocar na coluna 'tier'
                    cursor.execute("""
                        UPDATE clientes SET nome=%s, perfil=%s, keywords=%s WHERE id=%s
                    """, (novo_nome, novo_perfil, novas_keywords, cliente_id))
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

    # Seleção de Cliente
    clientes = get_clientes(None, role_name)
    clientes_dict = {c[1]: c[0] for c in clientes}
    if not clientes_dict:
        st.warning("⚠️ Não existem empresas. Cria primeiro um cliente.")
        st.stop()
    cliente_selecionado_nome = st.selectbox("📁 Selecione a Empresa", list(clientes_dict.keys()))
    cliente_id = clientes_dict[cliente_selecionado_nome]

    # Importar/Exportar via Excel
    with st.expander("📥 Importar/Exportar via Excel", expanded=False):
        col_dl, col_up = st.columns([1, 2])

        with col_dl:
            st.caption("Modelos de ficheiro para facilitar o preenchimento.")
            # Template vazio
            template_cols = ["Nome", "URL", "Tipologia", "Segmento", "Tier"]
            template_df = pd.DataFrame(columns=template_cols)
            buf_template = io.BytesIO()
            with pd.ExcelWriter(buf_template, engine="xlsxwriter") as writer:
                template_df.to_excel(writer, index=False, sheet_name="Medias")
            st.download_button(
                "⬇️ Descarregar Template Excel",
                data=buf_template.getvalue(),
                file_name=f"template_medias_{cliente_selecionado_nome}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

            # Export das medias atuais do cliente selecionado
            query_export = """
                SELECT media.nome AS Nome, media.url AS URL, media.tipologia AS Tipologia,
                       media.segmento AS Segmento, media.tier AS Tier
                FROM media
                WHERE media.cliente_id = %s
            """
            try:
                df_export = pd.read_sql_query(query_export, conn, params=[cliente_id])
            except Exception:
                df_export = pd.DataFrame(columns=template_cols)
            buf_export = io.BytesIO()
            with pd.ExcelWriter(buf_export, engine="xlsxwriter") as writer:
                (df_export[template_cols] if not df_export.empty else template_df).to_excel(writer, index=False, sheet_name="Medias")
            st.download_button(
                "⬇️ Exportar Medias deste Cliente",
                data=buf_export.getvalue(),
                file_name=f"medias_{cliente_selecionado_nome}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        with col_up:
            st.caption("Carrega um .xlsx com colunas: Nome, URL, Tipologia, Segmento, Tier. O cliente será o selecionado acima.")
            arquivo = st.file_uploader("Carregar Excel (.xlsx)", type=["xlsx"])
            atualizar_existentes = st.checkbox("Atualizar registos existentes (mesma URL no mesmo cliente)", value=True)
            btn_importar = st.button("📤 Importar para Media", use_container_width=True, disabled=arquivo is None)

            if btn_importar and arquivo is not None:
                try:
                    df_in = pd.read_excel(arquivo)
                except Exception as e:
                    st.error(f"❌ Erro a ler Excel: {e}")
                    st.stop()

                # Normalizar nomes de colunas (case-insensitive)
                expected = {"nome": "Nome", "url": "URL", "tipologia": "Tipologia", "segmento": "Segmento", "tier": "Tier"}
                colmap = {}
                for c in df_in.columns:
                    key = str(c).strip().lower()
                    if key in expected:
                        colmap[c] = expected[key]
                df_in = df_in.rename(columns=colmap)

                missing = [v for v in expected.values() if v not in df_in.columns and v != "Nome"]  # 'Nome' podemos derivar
                if "URL" not in df_in.columns:
                    st.error("❌ A coluna 'URL' é obrigatória.")
                    st.stop()
                if missing:
                    st.warning(f"⚠️ Colunas em falta (serão assumidos defaults se aplicável): {', '.join(missing)}")

                # Funções auxiliares
                def clamp_tier(x):
                    try:
                        v = int(x)
                    except Exception:
                        v = 4
                    return min(4, max(1, v))

                def norm_tipologia(x):
                    allowed = ["Print", "Online", "TV", "Rádio"]
                    s = str(x).strip() if pd.notna(x) else ""
                    return s if s in allowed else "Online"

                def norm_segmento(x):
                    allowed = ["Tecnologia", "Político", "Saúde", "Outro"]
                    s = str(x).strip() if pd.notna(x) else ""
                    return s if s in allowed else "Outro"

                def fallback_nome_por_url(u):
                    try:
                        from urllib.parse import urlparse
                        host = urlparse(u).netloc or ""
                        host = host.replace("www.", "")
                        base = host.split(".")[0] if host else "Site"
                        return base.capitalize()
                    except Exception:
                        return "Site"

                # Importação
                total = len(df_in)
                inseridos = atualizados = ignorados = conflitos_outro_cliente = erros = 0
                vistos = set()

                for idx, row in df_in.iterrows():
                    url = str(row.get("URL", "")).strip()
                    if not url or url.lower() == "nan":
                        ignorados += 1
                        continue
                    if url in vistos:
                        ignorados += 1
                        continue
                    vistos.add(url)

                    nome = str(row.get("Nome") or "").strip()
                    if not nome:
                        nome = fallback_nome_por_url(url)

                    tipologia = norm_tipologia(row.get("Tipologia"))
                    segmento = norm_segmento(row.get("Segmento"))
                    tier = clamp_tier(row.get("Tier"))

                    try:
                        ex_url = media_por_url(url)
                        if ex_url:
                            if ex_url["cliente_id"] == cliente_id:
                                if atualizar_existentes:
                                    update_media(ex_url["id"], nome, url, tipologia, segmento, tier)
                                    atualizados += 1
                                else:
                                    ignorados += 1
                            else:
                                conflitos_outro_cliente += 1
                        else:
                            insert_media(nome, url, cliente_id, tipologia, segmento, tier)
                            inseridos += 1
                    except Exception:
                        erros += 1

                st.success(f"✅ Importação concluída. Total linhas: {total} | Inseridos: {inseridos} | Atualizados: {atualizados} | Ignorados: {ignorados} | Conflitos outro cliente: {conflitos_outro_cliente} | Erros: {erros}")
                st.rerun()

    # Expander para adicionar 1 media manualmente
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