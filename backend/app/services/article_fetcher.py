import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch_article(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else (soup.title.string if soup.title else "未知標題")
    main = soup.find("article") or soup.find("main") or soup.body
    text = " ".join(
        p.get_text(strip=True)
        for p in (main or soup).find_all("p")
        if len(p.get_text(strip=True)) > 30
    )
    if len(text) < 100:
        raise ValueError("無法擷取足夠的文章內容")
    return title, text
