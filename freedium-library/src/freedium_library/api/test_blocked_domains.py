"""Tests for the non-article domain denylist."""
from freedium_library.api.blocked_domains import is_blocked_domain


def test_blocks_exact_and_subdomains():
    assert is_blocked_domain("https://youtube.com/watch?v=x")
    assert is_blocked_domain("https://www.youtube.com/watch?v=x")
    assert is_blocked_domain("https://m.youtube.com/watch?v=x")
    assert is_blocked_domain("https://x.com/user/status/1")
    # suffix rule: google.com blocks every subdomain
    assert is_blocked_domain("https://mail.google.com/")
    assert is_blocked_domain("https://docs.google.com/document/d/abc")
    assert is_blocked_domain("https://google.com/search?q=x")


def test_blocks_collapsed_slash_form():
    # SvelteKit collapses // -> / in the path it forwards as render content.
    assert is_blocked_domain("https:/youtube.com/watch?v=x")
    assert is_blocked_domain("https:/x.com/user")


def test_blocks_bare_host():
    assert is_blocked_domain("youtube.com/watch?v=x")


def test_does_not_block_articles_or_ids():
    assert not is_blocked_domain("https://medium.com/@u/some-article-c636de890607")
    assert not is_blocked_domain("https:/medium.com/cloud-security/foo-c636de890607")
    assert not is_blocked_domain("https://the-ken.com/tradetricks/foo/")
    # a bare Medium post id has no host -> never blocked
    assert not is_blocked_domain("c636de890607")
    assert not is_blocked_domain("")


def test_does_not_block_lookalike_suffix():
    # "notyoutube.com" must NOT be caught by the youtube.com rule
    assert not is_blocked_domain("https://notyoutube.com/x")
    assert not is_blocked_domain("https://youtube.com.evil.test/x")
