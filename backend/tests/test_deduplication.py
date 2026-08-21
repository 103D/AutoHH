


from app.utils.hash import compute_content_hash, normalize_url


def test_normalize_url():
    """Test URL normalization."""

    # Remove tracking params
    url1 = "https://example.com/job/123?utm_source=google&utm_campaign=test"
    url2 = "https://example.com/job/123"
    assert normalize_url(url1) == normalize_url(url2)

    # Case insensitive
    url3 = "HTTPS://EXAMPLE.COM/Job/123"
    assert normalize_url(url3) == normalize_url(url2)

    # Remove trailing slash
    url4 = "https://example.com/job/123/"
    assert normalize_url(url4) == normalize_url(url2)

    # Keep meaningful params, sort them
    url5 = "https://example.com/job?id=123&page=2"
    url6 = "https://example.com/job?page=2&id=123"
    assert normalize_url(url5) == normalize_url(url6)

def test_compute_content_hash():
    """Test content hash computation."""

    # Same content = same hash
    hash1 = compute_content_hash(
        "Senior Python Developer",
        "Tech Corp",
        "We are looking for a senior Python developer...",
        "Almaty"
    )
    hash2 = compute_content_hash(
        "Senior Python Developer",
        "Tech Corp",
        "We are looking for a senior Python developer...",
        "Almaty"
    )
    assert hash1 == hash2

    # Case insensitive
    hash3 = compute_content_hash(
        "senior python developer",
        "tech corp",
        "we are looking for a senior python developer...",
        "almaty"
    )
    assert hash1 == hash3

    # Different content = different hash
    hash4 = compute_content_hash(
        "Junior Python Developer",
        "Tech Corp",
        "We are looking for a senior Python developer...",
        "Almaty"
    )
    assert hash1 != hash4

    # Whitespace normalized
    hash5 = compute_content_hash(
        "Senior   Python    Developer",
        "Tech Corp",
        "We are looking for a senior Python developer...",
        "Almaty"
    )
    assert hash1 == hash5
