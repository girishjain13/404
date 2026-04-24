# ============================================================
# IA AUDIT TOOL (STREAMLIT CLOUD SAFE VERSION)
# No tldextract dependency
# ============================================================

import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
import time
import hashlib

# -----------------------------
# HELPERS
# -----------------------------

def get_domain(url):
    return urlparse(url).netloc


def is_valid(url, base_domain):
    try:
        return urlparse(url).netloc == base_domain
    except:
        return False


def get_hash(content):
    return hashlib.md5(content.encode("utf-8")).hexdigest()


# -----------------------------
# CRAWLER
# -----------------------------

def crawl_site(start_url, max_pages=300):

    visited = set()
    to_visit = [(start_url, 0)]

    all_pages = []
    content_map = {}
    link_map = {}
    redirect_map = {}

    base_domain = get_domain(start_url)

    session = requests.Session()
    session.headers.update({"User-Agent": "IA-Audit-Crawler"})

    progress = st.progress(0)
    status = st.empty()

    while to_visit and len(visited) < max_pages:

        url, depth = to_visit.pop(0)

        if url in visited:
            continue

        try:
            res = session.get(url, timeout=10, allow_redirects=True)

            final_url = res.url
            status_code = res.status_code

            visited.add(url)

            all_pages.append({
                "URL": url,
                "Final URL": final_url,
                "Status": status_code,
                "Depth": depth
            })

            if url != final_url:
                redirect_map[url] = final_url

            if status_code >= 400:
                continue

            if "text/html" not in res.headers.get("Content-Type", ""):
                continue

            soup = BeautifulSoup(res.text, "lxml")

            # Duplicate detection
            text = soup.get_text()
            content_map[url] = get_hash(text)

            # Extract links
            links = []

            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])

                if is_valid(href, base_domain):
                    links.append(href)

                    if href not in visited:
                        to_visit.append((href, depth + 1))

            link_map[url] = links

        except:
            pass

        # Progress UI
        progress.progress(min(len(visited) / max_pages, 1.0))
        status.text(f"Crawled {len(visited)} pages")

        time.sleep(0.02)

    return all_pages, content_map, link_map, redirect_map


# -----------------------------
# ANALYSIS
# -----------------------------

def find_duplicates(content_map):
    reverse = {}

    for url, h in content_map.items():
        reverse.setdefault(h, []).append(url)

    return [url for urls in reverse.values() if len(urls) > 1 for url in urls]


def find_orphans(link_map, all_urls):
    linked = set()

    for links in link_map.values():
        linked.update(links)

    return [url for url in all_urls if url not in linked]


# -----------------------------
# STREAMLIT UI
# -----------------------------

st.set_page_config(page_title="IA Audit Tool", layout="wide")

tab1, tab2 = st.tabs(["📌 Existing App", "🚀 IA Audit"])

# -----------------------------
# TAB 1 (Your existing app)
# -----------------------------
with tab1:
    st.title("📌 Existing Application")
    st.info("Place your existing application here.")

# -----------------------------
# TAB 2 (IA Audit Tool)
# -----------------------------
with tab2:

    st.title("🚀 IA Audit Tool")

    start_url = st.text_input("Start URL", "https://example.com")

    max_pages = st.number_input(
        "Max Pages",
        min_value=100,
        max_value=20000,
        value=300,
        step=100
    )

    uploaded_file = st.file_uploader(
        "Upload URL list (CSV) for accurate orphan detection",
        type=["csv"]
    )

    run = st.button("Run Audit")

    if run:

        if not start_url:
            st.error("Please enter a valid URL")
            st.stop()

        with st.spinner("Running crawl..."):

            all_pages, content_map, link_map, redirect_map = crawl_site(
                start_url, max_pages
            )

        df = pd.DataFrame(all_pages)

        # 404
        df_404 = df[df["Status"] == 404]

        # duplicates
        duplicates = find_duplicates(content_map)
        df_duplicates = df[df["URL"].isin(duplicates)]

        # orphans
        if uploaded_file:
            df_input = pd.read_csv(uploaded_file)
            orphan_urls = list(set(df_input.iloc[:, 0]) - set(df["URL"]))
        else:
            orphan_urls = find_orphans(link_map, df["URL"].tolist())

        df_orphans = pd.DataFrame(orphan_urls, columns=["URL"])

        # redirects
        df_redirects = pd.DataFrame(
            list(redirect_map.items()), columns=["From", "To"]
        )

        # ---------------- UI ----------------

        st.success("Audit Completed")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Pages", len(df))
        col2.metric("404 Pages", len(df_404))
        col3.metric("Duplicates", len(df_duplicates))
        col4.metric("Orphans", len(df_orphans))

        st.subheader("404 Pages")
        st.dataframe(df_404)

        st.subheader("Duplicates")
        st.dataframe(df_duplicates)

        st.subheader("Orphans")
        st.dataframe(df_orphans)

        st.subheader("Redirects")
        st.dataframe(df_redirects)

        st.subheader("All Pages")
        st.dataframe(df)

        # ---------------- EXPORT ----------------

        file_name = "IA_Audit_Report.xlsx"

        with pd.ExcelWriter(file_name, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="All Pages", index=False)
            df_404.to_excel(writer, sheet_name="404", index=False)
            df_duplicates.to_excel(writer, sheet_name="Duplicates", index=False)
            df_orphans.to_excel(writer, sheet_name="Orphans", index=False)
            df_redirects.to_excel(writer, sheet_name="Redirects", index=False)

        with open(file_name, "rb") as f:
            st.download_button(
                "Download Excel Report",
                f,
                file_name="IA_Audit_Report.xlsx"
            )
