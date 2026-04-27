import streamlit as st
import pandas as pd
from Bio import Entrez
import datetime
import xml.etree.ElementTree as ET

# --- CONFIGURACIÓN UI ---
st.set_page_config(page_title="PubMed/PMC Toolkit", layout="centered", initial_sidebar_state="collapsed")

# --- CREDENCIALES ---
st.sidebar.header("⚙️ Configuración Global")
email = st.sidebar.text_input("Correo API", value="oskaury@gmail.com")
api_key = st.sidebar.text_input("API Key", value="8a50c52b53b3524290dd952d574b7e7bab08", type="password")

st.sidebar.markdown("---")
menu = st.sidebar.radio(
    "Seleccione Módulo de Extracción:",
    ("1. Búsqueda MeSH ➔ CSV", "2. PMIDs ➔ Metadatos + PMC Full Text (.md)", "3. PMIDs ➔ Solo Abstracts (.md)")
)

# --- FUNCIONES CORE ---
def execute_esearch(query, max_results, years, art_types):
    Entrez.email = email
    Entrez.api_key = api_key
    final_query = query
    if art_types:
        ptyp_query = " OR ".join([f'"{pt}"[Publication Type]' for pt in art_types])
        final_query += f" AND ({ptyp_query})"
        
    search_handle = Entrez.esearch(
        db="pubmed", term=final_query, retmax=max_results,
        mindate=str(years[0]), maxdate=str(years[1]), datetype="pdat"
    )
    search_results = Entrez.read(search_handle)
    search_handle.close()
    return search_results.get("IdList", [])

def execute_efetch_pubmed(pmid_list):
    Entrez.email = email
    Entrez.api_key = api_key
    fetch_handle = Entrez.efetch(db="pubmed", id=",".join(pmid_list), retmode="xml")
    records = Entrez.read(fetch_handle)
    fetch_handle.close()
    return records.get('PubmedArticle', [])

def fetch_full_text_from_pmc(pmcid):
    """Extrae el XML completo de PMC e itera sobre los nodos <body> y <p>"""
    Entrez.email = email
    Entrez.api_key = api_key
    try:
        handle = Entrez.efetch(db="pmc", id=pmcid, rettype="fullxml", retmode="xml")
        xml_data = handle.read()
        handle.close()
        
        root = ET.fromstring(xml_data)
        body_parts = []
        for body in root.iter('body'):
            for p in body.iter('p'):
                if p.text:
                    body_parts.append(p.text.strip())
                    
        return "\n\n".join(body_parts) if body_parts else "Formato XML cerrado o estructurado sin nodos <p> estándar. Revisar link directo."
    except Exception as e:
        return f"Excepción en parser PMC: {e}"

def parse_article_data(article, extract_full_text=False):
    medline = article['MedlineCitation']
    article_data = medline['Article']
    pubmed_data = article['PubmedData']
    
    pmid = str(medline['PMID'])
    title = article_data.get('ArticleTitle', 'N/A')
    
    try:
        year = article_data['Journal']['JournalIssue']['PubDate']['Year']
    except KeyError:
        year = "N/A"
        
    authors = [f"{a.get('LastName', '')} {a.get('Initials', '')}".strip() 
               for a in article_data.get('AuthorList', []) if isinstance(a, dict)]
    
    abstract = "Abstract no disponible."
    if 'Abstract' in article_data and 'AbstractText' in article_data['Abstract']:
        abstract = "\n\n".join([str(text) for text in article_data['Abstract']['AbstractText']])
        
    doi = next((str(aid) for aid in pubmed_data['ArticleIdList'] if aid.attributes.get('IdType') == 'doi'), "N/A")
    pmc_id = next((str(aid) for aid in pubmed_data['ArticleIdList'] if aid.attributes.get('IdType') == 'pmc'), None)
    
    full_text_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/" if pmc_id else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    acceso_status = "Gratis (PMC)" if pmc_id else "Posible Pago (Revisar Link)"
    
    body_text = ""
    if extract_full_text and pmc_id:
        body_text = fetch_full_text_from_pmc(pmc_id)

    return {
        "PMID": pmid, "Titulo": title, "Año": year, "Autor": ", ".join(authors),
        "Abstract": abstract, "DOI": doi, "Acceso": acceso_status, "URL": full_text_url,
        "PMCID": pmc_id, "Cuerpo": body_text
    }

# --- INTERFAZ GRÁFICA ---

if menu == "1. Búsqueda MeSH ➔ CSV":
    st.title("Extracción de Metadatos (CSV)")
    search_query = st.text_area("Query (PubMed/MeSH Sintaxis)", value='("Femoral Fractures"[MeSH]) AND "Fracture Fixation, Intramedullary"[MeSH]', height=100)
    col1, col2 = st.columns(2)
    with col1:
        retmax = st.number_input("N Max Resultados", 1, 5000, 100)
    with col2:
        year_range = st.slider("Filtro Temporal", 1990, datetime.datetime.now().year, (2018, 2026))

    if st.button("Ejecutar Query", type="primary", use_container_width=True):
        with st.spinner('Consumiendo API NCBI...'):
            id_list = execute_esearch(search_query, retmax, year_range, [])
            if id_list:
                articles = execute_efetch_pubmed(id_list)
                df = pd.DataFrame([parse_article_data(art) for art in articles])
                df.drop(columns=['Cuerpo', 'PMCID'], inplace=True, errors='ignore') # Limpieza para CSV
                st.dataframe(df)
                st.download_button("📥 Descargar Database", df.to_csv(index=False).encode('utf-8'), "pubmed_dataset.csv", "text/csv", use_container_width=True)

elif menu == "2. PMIDs ➔ Metadatos + PMC Full Text (.md)":
    st.title("Parser de Texto Completo (PMC)")
    st.info("Nota técnica: Solo se extraerá el cuerpo del texto de aquellos manuscritos indexados en PubMed Central (PMCID) cuyo XML no esté protegido por DRM.")
    pmid_input = st.text_area("Input PMIDs (Lote de IDs numéricos):", height=150)
    
    if st.button("Compilar Markdown (.md)", type="primary", use_container_width=True):
        clean_pmids = [p.strip() for p in pmid_input.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if clean_pmids:
            with st.spinner('Procesando XML de PubMed y PMC...'):
                articles = execute_efetch_pubmed(clean_pmids)
                md_content = f"# Reporte Clínico/Bibliográfico - {datetime.date.today()}\n\n"
                
                for art in articles:
                    p = parse_article_data(art, extract_full_text=True)
                    md_content += f"## {p['Titulo']}\n"
                    md_content += f"- **PMID:** {p['PMID']} | **PMCID:** {p['PMCID'] or 'N/A'}\n"
                    md_content += f"- **Año:** {p['Año']} | **DOI:** {p['DOI']}\n"
                    md_content += f"- **Acceso:** {p['Acceso']} - **[Link al Documento]({p['URL']})**\n\n"
                    
                    md_content += f"### Abstract\n{p['Abstract']}\n\n"
                    
                    if p['PMCID']:
                        md_content += f"### Full Text Body (Extracción PMC)\n{p['Cuerpo']}\n\n"
                    
                    md_content += "---\n\n"
                
                st.download_button("📥 Descargar Reporte Completo (.md)", md_content.encode('utf-8'), "full_text_report.md", "text/markdown", use_container_width=True)

elif menu == "3. PMIDs ➔ Solo Abstracts (.md)":
    st.title("Aislamiento de Abstracts")
    pmid_input = st.text_area("Input PMIDs:", height=150)
    
    if st.button("Generar Compilación", type="primary", use_container_width=True):
        clean_pmids = [p.strip() for p in pmid_input.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if clean_pmids:
            with st.spinner('Petición en curso...'):
                articles = execute_efetch_pubmed(clean_pmids)
                md_content = f"# Compilación de Abstracts - {datetime.date.today()}\n\n"
                for art in articles:
                    p = parse_article_data(art)
                    md_content += f"### PMID: {p['PMID']}\n\n{p['Abstract']}\n\n---\n\n"
                st.download_button("📥 Descargar Abstracts (.md)", md_content.encode('utf-8'), "abstracts_only.md", "text/markdown", use_container_width=True)
