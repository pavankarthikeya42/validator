import re
import unicodedata

def normalize_text(text: str) -> str:
    """
    Normalizes input text according to validation rules:
    - lowercase
    - Unicode normalize (NFKC)
    - remove punctuation (keep spaces and basic alphanumerics)
    - collapse whitespace
    - normalize line breaks
    - trim spaces
    """
    if not text:
        return ""
    
    # Unicode normalize
    text = unicodedata.normalize("NFKC", text)
    
    # Lowercase
    text = text.lower()
    
    # Normalize line breaks to spaces
    text = re.sub(r'[\r\n]+', ' ', text)
    
    # Remove punctuation, keeping alphanumeric characters and spaces
    # We can also keep some basic symbols if needed, but the prompt says:
    # "remove punctuation, collapse whitespace, normalize line breaks, trim spaces"
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Trim spaces
    return text.strip()
