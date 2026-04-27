import streamlit as st
import pandas as pd
from Bio import Entrez
import datetime
import xml.etree.ElementTree as ET
import io
import PyPDF2

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="PubMed Toolkit Pro", layout="centered")

# --- CREDENCIALES ---
# Acceso seguro a variables de entorno
email = st.secrets["EMAIL"]
api_key = st.secrets["API_KEY"]

menu = st.sidebar.radio(
    "Módulo:",
    (
        "1. Búsqueda MeSH ➔ CSV", 
        "2. PMIDs ➔ Metadatos + PMC Full Text (.md)", 
        "3. PMIDs ➔ Solo Abstracts (.md)",
        "4. PDFs ➔ Documento Único (.md)"
    )
)

# Inicializar estados de sesión para evitar que los botones desaparezcan
if 'csv_data' not in st.session_state: st.session_state.csv_data = None
if 'md_report' not in st.session_state: st.session_state.md_report = None
if 'md_abstracts' not in st.session_state: st.session_state.md_abstracts = None
if 'error_log' not in st.session_state: st.session_state.error_log = None

# --- FUNCIONES DE EXTRACCIÓN ---
def fetch_full_text_from_pmc(pmcid):
    Entrez.email = email
    Entrez.api_key = api_key
    try:
        handle = Entrez.efetch(db="pmc", id=pmcid, rettype="fullxml", retmode="xml")
        xml_data = handle.read()
        handle.close()
        root = ET.fromstring(xml_data)
        body_parts = [p.text.strip() for body in root.iter('body') for p in body.iter('p') if p.text]
        return "\n\n".join(body_parts) if body_parts else None
    except:
        return None

def parse_article_data(article, extract_full_text=False):
    medline = article['MedlineCitation']
    article_data = medline['Article']
    pubmed_data = article['PubmedData']
    pmid = str(medline['PMID'])
    
    title = article_data.get('ArticleTitle', 'N/A')
    try:
        year = article_data['Journal']['JournalIssue']['PubDate']['Year']
    except:
        year = "N/A"
        
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
    st.title("Módulo 1: Búsqueda a CSV")
    query = st.text_area("Query MeSH:", value='("Femoral Fractures"[MeSH])')
    limit = st.number_input("Límite:", 1, 1000, 100)
    
    if st.button("Ejecutar Búsqueda"):
        with st.spinner("Buscando..."):
            Entrez.email, Entrez.api_key = email, api_key
            h = Entrez.esearch(db="pubmed", term=query, retmax=limit)
            ids = Entrez.read(h).get("IdList", [])
            if ids:
                records = Entrez.read(Entrez.efetch(db="pubmed", id=",".join(ids), retmode="xml")).get('PubmedArticle', [])
                df = pd.DataFrame([parse_article_data(r) for r in records])
                st.session_state.csv_data = df.to_csv(index=False).encode('utf-8')
    
    if st.session_state.csv_data:
        st.download_button("📥 Descargar CSV", st.session_state.csv_data, "busqueda.csv", "text/csv", use_container_width=True)

elif menu == "2. PMIDs ➔ Metadatos + PMC Full Text (.md)":
    st.title("Módulo 2: Full Text & Logs")
    pmid_in = st.text_area("PMIDs (uno por línea):")
    
    if st.button("Procesar Full Text"):
        ids = [p.strip() for p in pmid_in.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if ids:
            with st.spinner("Extrayendo XML de PMC..."):
                Entrez.email, Entrez.api_key = email, api_key
                records = Entrez.read(Entrez.efetch(db="pubmed", id=",".join(ids), retmode="xml")).get('PubmedArticle', [])
                md = ""
                errors = []
                for r in records:
                    p = parse_article_data(r, extract_full_text=True)
                    md += f"## {p['Titulo']}\n- PMID: {p['PMID']}\n- Abstract: {p['Abstract'] if p['Abstract'] else 'NO'}\n"
                    if p['Cuerpo']: md += f"### Cuerpo\n{p['Cuerpo']}\n"
                    md += "\n---\n"
                    if not p['Cuerpo']: errors.append({"PMID": p['PMID'], "Razon": "Sin PMC o XML Protegido"})
                
                st.session_state.md_report = md.encode('utf-8')
                st.session_state.error_log = pd.DataFrame(errors).to_csv(index=False).encode('utf-8') if errors else None

    if st.session_state.md_report:
        st.download_button("📥 Descargar Reporte (.md)", st.session_state.md_report, "reporte.md", use_container_width=True)
    if st.session_state.error_log:
        st.download_button("⚠️ Descargar Log de Errores (CSV)", st.session_state.error_log, "errores.csv", "text/csv", use_container_width=True)

elif menu == "3. PMIDs ➔ Solo Abstracts (.md)":
    st.title("Módulo 3: Solo Abstracts")
    pmid_in_abs = st.text_area("PMIDs para Abstracts:")
    
    if st.button("Generar Abstracts"):
        ids = [p.strip() for p in pmid_in_abs.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if ids:
            with st.spinner("Descargando..."):
                Entrez.email, Entrez.api_key = email, api_key
                records = Entrez.read(Entrez.efetch(db="pubmed", id=",".join(ids), retmode="xml")).get('PubmedArticle', [])
                md = ""
                for r in records:
                    p = parse_article_data(r)
                    md += f"### PMID: {p['PMID']}\n\n{p['Abstract'] if p['Abstract'] else 'No disponible'}\n\n---\n\n"
                st.session_state.md_abstracts = md.encode('utf-8')

    if st.session_state.md_abstracts:
        st.download_button("📥 Descargar Abstracts (.md)", st.session_state.md_abstracts, "abstracts.md", use_container_width=True)
elif menu == "4. PDFs ➔ Documento Único (.md)":
    st.title("Módulo 4: Parseo de PDFs a Markdown")
    st.info("Extrae el texto de múltiples artículos en formato PDF y consolídalos en un documento único.")
    
    # Inicializar estado de sesión para este módulo si no existe
    if 'pdf_md_report' not in st.session_state:
        st.session_state.pdf_md_report = None

    uploaded_files = st.file_uploader("Cargar archivos PDF", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Procesar PDFs a Markdown", type="primary", use_container_width=True):
        if uploaded_files:
            with st.spinner(f"Extrayendo texto de {len(uploaded_files)} documento(s)..."):
                md_content = f"# Compilación de Artículos PDF - {datetime.date.today()}\n\n"
                
                for pdf_file in uploaded_files:
                    md_content += f"## Documento: {pdf_file.name}\n\n"
                    try:
                        reader = PyPDF2.PdfReader(pdf_file)
                        text_parts = []
                        for page in reader.pages:
                            text = page.extract_text()
                            if text:
                                text_parts.append(text)
                        
                        if text_parts:
                            md_content += "\n\n".join(text_parts) + "\n\n"
                        else:
                            md_content += "*No se detectó texto extraíble (posible documento escaneado como imagen).*\n\n"
                    except Exception as e:
                        md_content += f"*Error en el parseo del archivo:* {e}\n\n"
                        
                    md_content += "---\n\n"
                
                st.session_state.pdf_md_report = md_content.encode('utf-8')
        else:
            st.warning("Ingrese al menos un archivo PDF válido.")

    # Renderizado persistente del botón de descarga
    if st.session_state.pdf_md_report:
        st.download_button(
            label="📥 Descargar Compilación (.md)", 
            data=st.session_state.pdf_md_report, 
            file_name=f"pdfs_compilados_{datetime.date.today()}.md", 
            mime="text/markdown", 
            use_container_width=True
        )
