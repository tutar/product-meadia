import pytest

from src.services.composition_sources import canonicalize_html


def test_canonical_composition_source_replaces_transient_media_urls_with_media_asset_references():
    source = canonicalize_html(
        '<audio src="https://store/voice?X-Amz-Signature=secret"></audio>'
        '<video src="https://store/clip?X-Amz-Signature=secret"></video>',
        ["11111111-1111-1111-1111-111111111111"],
        "22222222-2222-2222-2222-222222222222",
    )

    assert "X-Amz-Signature" not in source.canonical_html
    assert 'src="asset://22222222-2222-2222-2222-222222222222"' in source.canonical_html
    assert 'src="asset://11111111-1111-1111-1111-111111111111"' in source.canonical_html
