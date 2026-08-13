import hashlib
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

def normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    parsed = urlparse(url)
    
    # Remove query parameters that don't affect content
    query_params = parse_qs(parsed.query)
    
    # Keep only meaningful params (exclude tracking, session, etc)
    exclude_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 
                     'session', 'sessionid', 'sid', 'fbclid', 'gclid'}
    
    filtered_params = {k: v for k, v in query_params.items() if k.lower() not in exclude_params}
    
    # Sort params for consistency
    sorted_query = urlencode(sorted(filtered_params.items()), doseq=True)
    
    # Reconstruct URL
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip('/').lower(),
        '',
        sorted_query,
        ''
    ))
    
    return normalized

def compute_content_hash(title: str, company: str, description: str, location: str | None = None) -> str:
    """Compute content hash for deduplication."""
    # Normalize text
    title_norm = ' '.join(title.lower().split())
    company_norm = ' '.join(company.lower().split())
    desc_norm = ' '.join(description.lower().split())[:1000]  # First 1000 chars
    location_norm = ' '.join(location.lower().split()) if location else ''
    
    # Combine
    combined = f"{title_norm}|{company_norm}|{desc_norm}|{location_norm}"
    
    # Hash
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()