import streamlit as st
import pandas as pd
from Bio import Entrez
import datetime
import xml.etree.ElementTree as ET
import io
import PyPDF2

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="PubMed Toolkit Pro", layout="centered")

# --- SISTEMA DE AUTENTICACIÓN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("Acceso Restringido")
        pwd = st.text_input("Contraseña:", type="password")
        if st.button("Entrar"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Clave incorrecta")
        return False
    return True

if not check_password():
    st.stop()

# --- CARGA DE CREDENCIALES DESDE SECRETS ---
email = st.secrets["EMAIL"]
api_key = st.secrets["API_KEY"]

# --- INTERFAZ ---
st.sidebar.header("Menú Principal")
menu = st.sidebar.radio(
    "Módulo:",
    (
        "1. Búsqueda MeSH ➔ CSV", 
        "2. PMIDs ➔ Metadatos + PMC Full Text (.md)", 
        "3. PMIDs ➔ Solo Abstracts (.md)",
        "4. PDFs ➔ Documento Único (.md)"
    )
)

# Inicializar estados de sesión
for key in ['csv_data', 'md_report', 'md_abstracts', 'error_log', 'pdf_md_report']:
    if key not in st.session_state: st.session_state[key] = None

# --- FUNCIONES TÉCNICAS ---
def fetch_full_text_from_pmc(pmcid):
    Entrez.email, Entrez.api_key = email, api_key
    try:
        handle = Entrez.efetch(db="pmc", id=pmcid, rettype="fullxml", retmode="xml")
        xml_data = handle.read()
        handle.close()
        root = ET.fromstring(xml_data)
        body_parts = [p.text.strip() for body in root.iter('body') for p in body.iter('p') if p.text]
        return "\n\n".join(body_parts) if body_parts else None
    except: return None

def parse_article_data(article, extract_full_text=False):
    medline = article['MedlineCitation']
    article_data = medline['Article']
    pubmed_data = article['PubmedData']
    pmid = str(medline['PMID'])
    title = article_data.get('ArticleTitle', 'N/A')
    
    try: year = article_data['Journal']['JournalIssue']['PubDate']['Year']
    except: year = "N/A"
        
    authors = [f"{a.get('LastName', '')} {a.get('Initials', '')}".strip() 
               for a in article_data.get('AuthorList', []) if isinstance(a, dict)]

    abstract = None
    if 'Abstract' in article_data and 'AbstractText' in article_data['Abstract']:
        abstract = "\n\n".join([str(text) for text in article_data['Abstract']['AbstractText']])
    
    pmc_id = next((str(aid) for aid in pubmed_data['ArticleIdList'] if aid.attributes.get('IdType') == 'pmc'), None)
    doi = next((str(aid) for aid in pubmed_data['ArticleIdList'] if aid.attributes.get('IdType') == 'doi'), "N/A")
    
    body_text = None
    if extract_full_text and pmc_id:
        body_text = fetch_full_text_from_pmc(pmc_id)

    return {
        "PMID": pmid, "Titulo": title, "Año": year, "Autor": ", ".join(authors),
        "Abstract": abstract, "DOI": doi, "PMCID": pmc_id, "Cuerpo": body_text,
        "URL": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/" if pmc_id else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    }

# --- LÓGICA DE MÓDULOS ---

if menu == "1. Búsqueda MeSH ➔ CSV":
    st.title("Extracción PubMed a CSV")
    query = st.text_area("Query MeSH:", value='("Femoral Fractures"[MeSH])')
    limit = st.number_input("Límite:", 1, 1000, 100)
    
    if st.button("Buscar"):
        with st.spinner("Procesando..."):
            Entrez.email, Entrez.api_key = email, api_key
            h = Entrez.esearch(db="pubmed", term=query, retmax=limit)
            ids = Entrez.read(h).get("IdList", [])
            if ids:
                records = Entrez.read(Entrez.efetch(db="pubmed", id=",".join(ids), retmode="xml")).get('PubmedArticle', [])
                df = pd.DataFrame([parse_article_data(r) for r in records])
                st.session_state.csv_data = df.to_csv(index=False).encode('utf-8')
    
    if st.session_state.csv_data:
        st.download_button("📥 Descargar CSV", st.session_state.csv_data, "pubmed_search.csv", "text/csv")

elif menu == "2. PMIDs ➔ Metadatos + PMC Full Text (.md)":
    st.title("Extracción Full Text (PMC)")
    pmid_in = st.text_area("PMIDs (uno por línea):")
    
    if st.button("Procesar"):
        ids = [p.strip() for p in pmid_in.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if ids:
            with st.spinner("Descargando XML de PMC..."):
                Entrez.email, Entrez.api_key = email, api_key
                records = Entrez.read(Entrez.efetch(db="pubmed", id=",".join(ids), retmode="xml")).get('PubmedArticle', [])
                md, errors = "", []
                for r in records:
                    p = parse_article_data(r, extract_full_text=True)
                    md += f"## {p['Titulo']}\n- PMID: {p['PMID']}\n- Abstract: {p['Abstract'] if p['Abstract'] else 'NO'}\n"
                    if p['Cuerpo']: md += f"### Cuerpo\n{p['Cuerpo']}\n"
                    md += "\n---\n"
                    if not p['Cuerpo']: errors.append({"PMID": p['PMID'], "Razon": "Sin PMC o XML Protegido"})
                
                st.session_state.md_report = md.encode('utf-8')
                st.session_state.error_log = pd.DataFrame(errors).to_csv(index=False).encode('utf-8') if errors else None

    if st.session_state.md_report:
        st.download_button("📥 Descargar Reporte (.md)", st.session_state.md_report, "full_report.md")
    if st.session_state.error_log:
        st.download_button("⚠️ Descargar Log de Errores", st.session_state.error_log, "failed_pmc.csv")

elif menu == "3. PMIDs ➔ Solo Abstracts (.md)":
    st.title("Compilación de Abstracts")
    pmid_in_abs = st.text_area("PMIDs:")
    
    if st.button("Generar"):
        ids = [p.strip() for p in pmid_in_abs.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if ids:
            with st.spinner("Extrayendo..."):
                Entrez.email, Entrez.api_key = email, api_key
                records = Entrez.read(Entrez.efetch(db="pubmed", id=",".join(ids), retmode="xml")).get('PubmedArticle', [])
                md = ""
                for r in records:
                    p = parse_article_data(r)
                    md += f"### PMID: {p['PMID']}\n\n{p['Abstract'] if p['Abstract'] else 'No disponible'}\n\n---\n\n"
                st.session_state.md_abstracts = md.encode('utf-8')

    if st.session_state.md_abstracts:
        st.download_button("📥 Descargar Abstracts", st.session_state.md_abstracts, "abstracts.md")

elif menu == "4. PDFs ➔ Documento Único (.md)":
    st.title("Conversión PDF a Markdown")
    uploaded_files = st.file_uploader("Cargar PDFs", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Convertir"):
        if uploaded_files:
            with st.spinner("Extrayendo texto..."):
                md_content = f"# Compilación PDF - {datetime.date.today()}\n\n"
                for pdf_file in uploaded_files:
                    md_content += f"## {pdf_file.name}\n\n"
                    try:
                        reader = PyPDF2.PdfReader(pdf_file)
                        text_parts = [page.extract_text() for page in reader.pages if page.extract_text()]
                        md_content += "\n\n".join(text_parts) + "\n\n" if text_parts else "*Sin texto extraíble.*\n\n"
                    except Exception as e:
                        md_content += f"*Error:* {e}\n\n"
                    md_content += "---\n\n"
                st.session_state.pdf_md_report = md_content.encode('utf-8')

    if st.session_state.pdf_md_report:
        st.download_button("📥 Descargar Compilación", st.session_state.pdf_md_report, "pdf_to_md.md")
