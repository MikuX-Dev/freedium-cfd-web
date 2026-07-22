"""The Economist article client — dual method (GraphQL API + web scraping).

Method 1 (primary): HMAC-signed GraphQL query to api.economist.com.
  Reverse-engineered from com.economist.lamarr (classes2.dex). Full article.
Method 2 (fallback): curl_cffi (Chrome impersonation) → __NEXT_DATA__ JSON.
  Works when the GraphQL endpoint is down or the URL format changes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
import uuid
import urllib.parse
import urllib.request
from typing import Any

from loguru import logger

GRAPHQL_URL = "https://api.economist.com/teg/content/b2c-mobile/cp2-gateway/graphql"
SECRET_KEY = b"PxT9RqXllrEiW1o01DFegvK63EZy4g2H"
DEEPLINK_OP_ID = "5b3f755e2732bec2f7fc24cbc65d56e73c446986568a61bcf7cb99000913149c"

# Full query from the decompiled app (com.economist.lamarr classes2.dex).
# Must include ALL variables + fragments — the server validates strictly.
DEEPLINK_QUERY = 'query ArticleDeeplinkQuery($ref: String!, $includeRelatedArticles: Boolean = true , $includeImageCredits: Boolean = false , $selectionMethod: NarrationSelectionMethod!) { findArticleByUrl(url: $ref) { __typename ...ArticleDataFragment } }  fragment ContentIdentityFragment on ContentIdentity { articleType forceAppWebView leadMediaType }  fragment NarrationFragment on Narration { album bitrate duration filename id provider url isAiGenerated fileHash }  fragment ImageTeaserFragment on ImageComponent { altText height imageType source url width credit @include(if: $includeImageCredits) caption @include(if: $includeImageCredits) { text textJson annotations { type length index attributes { name value } } } }  fragment PodcastAudioFragment on PodcastEpisode { id audio { url durationInSeconds } subscriberContent }  fragment PodcastShowFragment on PodcastShow { id cadence category description imageUrl slug summary title topic topics type seasonCount availableSeasons teaserColourLight teaserColourDark }  fragment ArticleTeaserFragment on Article { id tegId url rubric headline flyTitle brand byline dateFirstPublished dateline dateModified datePublished dateRevised estimatedReadTime wordCount printHeadline contentIdentity { __typename ...ContentIdentityFragment } section { tegId name } teaserImage { __typename type ...ImageTeaserFragment } leadComponent { __typename type ...ImageTeaserFragment } narration(selectionMethod: $selectionMethod) { __typename ...NarrationFragment } podcast { __typename ...PodcastAudioFragment show { __typename ...PodcastShowFragment } } }  fragment AnnotatedTextFragment on AnnotatedText { text textJson annotations { type length index attributes { name value } } }  fragment ImageComponentFragment on ImageComponent { altText caption { __typename ...AnnotatedTextFragment } credit height imageType mode source url width }  fragment BlockQuoteComponentFragment on BlockQuoteComponent { text textJson annotations { type length index attributes { name value } } }  fragment BookInfoComponentFragment on BookInfoComponent { text textJson annotations { type length index attributes { name value } } }  fragment ParagraphComponentFragment on ParagraphComponent { text textJson annotations { type length index attributes { name value } } }  fragment PullQuoteComponentFragment on PullQuoteComponent { text textJson annotations { type length index attributes { name value } } }  fragment CrossheadComponentFragment on CrossheadComponent { text }  fragment OrderedListComponentFragment on OrderedListComponent { items { __typename ...AnnotatedTextFragment } }  fragment UnorderedListComponentFragment on UnorderedListComponent { items { __typename ...AnnotatedTextFragment } }  fragment VideoComponentFragment on VideoComponent { url title thumbnailImage }  fragment InfoboxComponentFragment on InfoboxComponent { components { __typename type ...BlockQuoteComponentFragment ...BookInfoComponentFragment ...ParagraphComponentFragment ...PullQuoteComponentFragment ...CrossheadComponentFragment ...OrderedListComponentFragment ...UnorderedListComponentFragment ...VideoComponentFragment } }  fragment InfographicComponentFragment on InfographicComponent { url title width fallback { __typename ...ImageComponentFragment } altText height width }  fragment ArticleTagsFragment on Tag { id name url }  fragment PodcastTopicsFragment on PodcastEpisode { show { topics } }  fragment ArticleDataFragment on Article { id url brand byline rubric headline layout { headerStyle } contentIdentity { __typename ...ContentIdentityFragment } dateline dateFirstPublished dateModified datePublished dateRevised estimatedReadTime narration(selectionMethod: $selectionMethod) { __typename ...NarrationFragment } printFlyTitle printHeadline printRubric flyTitle wordCount section { tegId name articles(pagingInfo: { pagingType: OFFSET pageSize: 6 pageNumber: 1 } ) @include(if: $includeRelatedArticles) { edges { node { __typename ...ArticleTeaserFragment } } } } teaserImage { __typename type ...ImageComponentFragment } tegId leadComponent { __typename type ...ImageComponentFragment } body { __typename type ...BlockQuoteComponentFragment ...BookInfoComponentFragment ...ParagraphComponentFragment ...PullQuoteComponentFragment ...CrossheadComponentFragment ...OrderedListComponentFragment ...UnorderedListComponentFragment ...InfoboxComponentFragment ...ImageComponentFragment ...VideoComponentFragment ...InfographicComponentFragment } footer { __typename type ...ParagraphComponentFragment } tags { __typename ...ArticleTagsFragment } ads { adData } podcast { __typename ...PodcastAudioFragment ...PodcastTopicsFragment } aiSummary { __typename type ...UnorderedListComponentFragment } }'


def _sign_headers(op_name: str, op_id: str) -> dict[str, str]:
    ts = str(int(time.time() * 1000))
    cid = str(uuid.uuid4())
    sig = base64.b64encode(
        hmac.new(SECRET_KEY, f"{cid}:{ts}".encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "user-agent": "Liskov/4.96.0(4727665) (android)",
        "x-teg-client-name": "Economist-Android",
        "x-teg-client-version": "4.96.0",
        "x-economist-consumer": "TheEconomist-Liskov-android-4.96.0-4727665",
        "x-consumer-service": "liskov",
        "accept": "application/json",
        "x-teg-correlation-id": cid,
        "x-teg-timestamp": ts,
        "x-teg-signature": sig,
        "x-apollo-operation-name": op_name,
        "x-apollo-operation-id": op_id,
    }


def fetch_via_graphql(url: str) -> dict[str, Any]:
    """Primary: HMAC-signed GraphQL query (full article body)."""
    headers = _sign_headers("ArticleDeeplinkQuery", DEEPLINK_OP_ID)
    params = {
        "operationName": "ArticleDeeplinkQuery",
        "variables": json.dumps(
            {"ref": url, "includeRelatedArticles": False,
             "includeImageCredits": True,
             "selectionMethod": "PREFER_ACTOR_NARRATION"},
            separators=(",", ":"),
        ),
        "query": DEEPLINK_QUERY,
    }
    full = GRAPHQL_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    req = urllib.request.Request(full, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    return data.get("data", {}).get("findArticleByUrl") or {}


def fetch_via_web(url: str) -> dict[str, Any]:
    """Fallback: curl_cffi → __NEXT_DATA__ JSON from the web page."""
    from curl_cffi import requests as creq

    r = creq.get(url, impersonate="chrome120", timeout=15)
    r.raise_for_status()
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text
    )
    if not m:
        raise ValueError("No __NEXT_DATA__ in page")
    data = json.loads(m.group(1))
    return data.get("props", {}).get("pageProps", {}).get("content") or {}


def fetch_article(url: str) -> dict[str, Any]:
    """Try GraphQL first, fall back to web scraping."""
    try:
        art = fetch_via_graphql(url)
        if art and art.get("body"):
            art["_method"] = "graphql"
            return art
    except Exception as exc:
        logger.debug(f"Economist GraphQL failed: {exc}")
    try:
        art = fetch_via_web(url)
        if art:
            art["_method"] = "web"
            return art
    except Exception as exc:
        logger.debug(f"Economist web fallback failed: {exc}")
    raise ValueError("Could not fetch Economist article via either method")
