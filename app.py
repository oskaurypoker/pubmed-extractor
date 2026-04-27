import streamlit as st
import pandas as pd
from Bio import Entrez
import datetime

# --- CONFIGURACIÓN DE PÁGINA (Optimizada para Móvil) ---
st.set_page_config(page_title="PubMed Toolkit", layout="centered", initial_sidebar_state="collapsed")

# --- BARRA LATERAL: Credenciales y Navegación ---
st.sidebar.header("⚙️ Configuración Global")
email = st.sidebar.text_input("Correo", value="oskaury@gmail.com")
api_key = st.sidebar.text_input("API Key", value="8a50c52b53b3524290dd952d574b7e7bab08", type="password")

st.sidebar.markdown("---")
st.sidebar.header("🛠️ Herramientas")
menu = st.sidebar.radio(
    "Seleccione un módulo:",
    ("1. Búsqueda PubMed ➔ CSV", "2. PMIDs ➔ Metadatos Completos (.md)", "3. PMIDs ➔ Solo Abstracts (.md)")
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
    is_free = "Gratis (PMC)" if any(aid.attributes.get('IdType') == 'pmc' for aid in pubmed_data['ArticleIdList']) else "Pago"
    pub_types = [pt.strip() for pt in article_data.get('PublicationTypeList', [])]
    
    return {
        "PMID": pmid, "Titulo": title, "Año": year, "Autor": ", ".join(authors),
        "Abstract": abstract, "DOI": doi, "Acceso": is_free, "Tipo": ", ".join(pub_types)
    }

# --- MÓDULO 1: BÚSQUEDA A CSV ---
if menu == "1. Búsqueda PubMed ➔ CSV":
    st.title("Buscador MeSH a CSV")
    
    query_default = '("Femoral Fractures"[MeSH]) AND "Fracture Fixation, Intramedullary"[MeSH]'
    search_query = st.text_area("Query de Búsqueda", value=query_default, height=100)
    
    col1, col2 = st.columns(2)
    with col1:
        retmax = st.number_input("Límite (retmax)", min_value=1, max_value=5000, value=100)
    with col2:
        current_year = datetime.datetime.now().year
        year_range = st.slider("Años", min_value=1990, max_value=current_year, value=(2015, current_year))
        
    art_types_options = ["Clinical Trial", "Randomized Controlled Trial", "Systematic Review", "Meta-Analysis", "Review"]
    selected_types = st.multiselect("Filtro: Tipo de Artículo", options=art_types_options)

    if st.button("Ejecutar Extracción CSV", type="primary", use_container_width=True):
        with st.spinner('Procesando...'):
            try:
                id_list = execute_esearch(search_query, retmax, year_range, selected_types)
                if not id_list:
                    st.warning("Sin resultados.")
                else:
                    articles = execute_efetch(id_list)
                    data = [parse_article_data(art) for art in articles]
                    df = pd.DataFrame(data)
                    
                    st.success(f"{len(df)} artículos recuperados.")
                    st.download_button("📥 Descargar CSV", data=df.to_csv(index=False, encoding='utf-8'), 
                                       file_name=f"pubmed_export_{datetime.date.today()}.csv", mime="text/csv", use_container_width=True)
            except Exception as e:
                st.error(f"Error: {e}")

# --- MÓDULO 2: PMIDs A METADATOS (.MD) ---
elif menu == "2. PMIDs ➔ Metadatos Completos (.md)":
    st.title("Metadatos a Markdown")
    pmid_input = st.text_area("Lista de PMIDs:", height=150, placeholder="Ej: 32456123\n31098452")
    
    if st.button("Generar Markdown Completo", type="primary", use_container_width=True):
        clean_pmids = [p.strip() for p in pmid_input.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if not clean_pmids:
            st.error("Ingrese PMIDs válidos.")
        else:
            with st.spinner('Procesando PMIDs...'):
                try:
                    articles = execute_efetch(clean_pmids)
                    md_content = f"# Revisión - {datetime.date.today()}\n\n"
                    
                    for art in articles:
                        parsed = parse_article_data(art)
                        md_content += f"### PMID: {parsed['PMID']}\n"
                        md_content += f"- **Autores:** {parsed['Autor']}\n"
                        md_content += f"- **Año:** {parsed['Año']}\n"
                        md_content += f"- **DOI:** {parsed['DOI']}\n\n"
                        md_content += f"**Abstract:**\n{parsed['Abstract']}\n\n---\n\n"
                        
                    st.success("Documento generado.")
                    st.download_button("📥 Descargar .md", data=md_content, 
                                       file_name=f"metadatos_{datetime.date.today()}.md", mime="text/markdown", use_container_width=True)
                    with st.expander("Previsualizar"):
                        st.markdown(md_content)
                except Exception as e:
                    st.error(f"Error: {e}")

# --- MÓDULO 3: PMIDs A SOLO ABSTRACTS (.MD) ---
elif menu == "3. PMIDs ➔ Solo Abstracts (.md)":
    st.title("Extracción Aislada de Abstracts")
    pmid_input = st.text_area("Lista de PMIDs:", height=150, placeholder="Ej: 32456123\n31098452")
    
    if st.button("Generar Documento de Abstracts", type="primary", use_container_width=True):
        clean_pmids = [p.strip() for p in pmid_input.replace(',', '\n').split('\n') if p.strip().isdigit()]
        if not clean_pmids:
            st.error("Ingrese PMIDs válidos.")
        else:
            with st.spinner('Aislando abstracts...'):
                try:
                    articles = execute_efetch(clean_pmids)
                    md_content = f"# Abstracts - {datetime.date.today()}\n\n"
                    
                    for art in articles:
                        parsed = parse_article_data(art)
                        md_content += f"### PMID: {parsed['PMID']}\n\n{parsed['Abstract']}\n\n---\n\n"
                        
                    st.success("Documento generado.")
                    st.download_button("📥 Descargar .md", data=md_content, 
                                       file_name=f"abstracts_{datetime.date.today()}.md", mime="text/markdown", use_container_width=True)
                except Exception as e:
                    st.error(f"Error: {e}")