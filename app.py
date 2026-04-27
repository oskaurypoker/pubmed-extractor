import streamlit as st
import pandas as pd
from Bio import Entrez
import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="PubMed Toolkit Pro", layout="centered", initial_sidebar_state="collapsed")

# --- CREDENCIALES Y NAVEGACIÓN ---
st.sidebar.header("⚙️ Configuración")
email = st.sidebar.text_input("Correo", value="oskaury@gmail.com")
api_key = st.sidebar.text_input("API Key", value="8a50c52b53b3524290dd952d574b7e7bab08", type="password")

st.sidebar.markdown("---")
menu = st.sidebar.radio(
    "Seleccione Herramienta:",
    ("1. Búsqueda PubMed ➔ CSV", "2. PMIDs ➔ Metadatos + Full Text (.md)", "3. PMIDs ➔ Solo Abstracts (.md)")
)

# --- LÓGICA DE EXTRACCIÓN ---
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

def execute_efetch(pmid_list):
    Entrez.email = email
    Entrez.api_key = api_key
    fetch_handle = Entrez.efetch(db="pubmed", id=",".join(pmid_list), retmode="xml")
    records = Entrez.read(fetch_handle)
    fetch_handle.close()
    return records.get('PubmedArticle', [])

def parse_article_data(article):
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
    
    # LÓGICA PARA FREE FULL TEXT (PMC)
    pmc_id = next((str(aid) for aid in pubmed_data['ArticleIdList'] if aid.attributes.get('IdType') == 'pmc'), None)
    if pmc_id:
        full_text_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
        acceso_status = "Gratis (PMC)"
    else:
        full_text_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" # Link a PubMed para buscar links externos
        acceso_status = "Posible Pago / Revisar en PubMed"

    return {
        "PMID": pmid, "Titulo": title, "Año": year, "Autor": ", ".join(authors),
        "Abstract": abstract, "DOI": doi, "Acceso": acceso_status, "Full_Text_URL": full_text_url
    }

# --- INTERFAZ ---
if menu == "1. Búsqueda PubMed ➔ CSV":
    st.title("Buscador a CSV")
    search_query = st.text_area("Query MeSH", value='("Femoral Fractures"[MeSH]) AND "Fracture Fixation, Intramedullary"[MeSH]', height=100)
    col1, col2 = st.columns(2)
    with col1:
        retmax = st.number_input("Resultados", 1, 5000, 100)
    with col2:
        year_range = st.slider("Años", 1990, datetime.datetime.now().year, (2018, 2026))

    if st.button("Extraer CSV", type="primary", use_container_width=True):
        with st.spinner('Descargando...'):
            id_list = execute_esearch(search_query, retmax, year_range, [])
            if id_list:
                articles = execute_efetch(id_list)
                df = pd.DataFrame([parse_article_data(art) for art in articles])
                st.dataframe(df)
                st.download_button("📥 Descargar CSV", df.to_csv(index=False), "pubmed_data.csv", "text/csv", use_container_width=True)

elif menu == "2. PMIDs ➔ Metadatos + Full Text (.md)":
    st.title("Metadatos y Enlaces Full Text")
    pmid_input = st.text_area("Lista de PMIDs:", height=150)
    
    if st.button("Generar Markdown con Enlaces", type="primary", use_container_width=True):
        clean_pmids = [p.strip() for p in pmid_input.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if clean_pmids:
            with st.spinner('Procesando...'):
                articles = execute_efetch(clean_pmids)
                md_content = f"# Revisión de Artículos - {datetime.date.today()}\n\n"
                for art in articles:
                    p = parse_article_data(art)
                    md_content += f"## {p['Titulo']}\n"
                    md_content += f"- **PMID:** {p['PMID']}\n"
                    md_content += f"- **Año:** {p['Año']} | **DOI:** {p['DOI']}\n"
                    md_content += f"- **Acceso:** {p['Acceso']}\n"
                    md_content += f"- **[Link al Texto Completo]({p['Full_Text_URL']})**\n\n"
                    md_content += f"**Abstract:**\n{p['Abstract']}\n\n---\n\n"
                
                st.download_button("📥 Descargar .md", md_content, "revision_full.md", "text/markdown", use_container_width=True)
                st.markdown(md_content)

elif menu == "3. PMIDs ➔ Solo Abstracts (.md)":
    st.title("Solo Abstracts")
    pmid_input = st.text_area("Lista de PMIDs:", height=150)
    if st.button("Generar Abstracts", type="primary", use_container_width=True):
        clean_pmids = [p.strip() for p in pmid_input.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if clean_pmids:
            articles = execute_efetch(clean_pmids)
            md_content = ""
            for art in articles:
                p = parse_article_data(art)
                md_content += f"### PMID: {p['PMID']}\n\n{p['Abstract']}\n\n---\n\n"
            st.download_button("📥 Descargar .md", md_content, "abstracts.md", "text/markdown", use_container_width=True)
