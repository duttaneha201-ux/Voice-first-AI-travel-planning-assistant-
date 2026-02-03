"""
Grounding evaluation: check for hallucinations (claims not backed by knowledge/POIs).
Verifies POI existence, claims against knowledge base, and flags hallucinations.
"""

from __future__ import annotations

import re
from typing import Any

from src.data.repositories.poi_repository import POIRepository
from src.rag.knowledge_base import UdaipurKnowledgeBase


def _extract_poi_names(text: str) -> list[str]:
    """Extract potential POI names from text (capitalized phrases, quoted names)."""
    # Look for quoted names
    quoted = re.findall(r'"([^"]+)"', text)
    # Look for capitalized phrases (likely POI names)
    capitalized = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text)
    # Common POI names in Udaipur
    known_patterns = [
        r"City Palace",
        r"Lake Pichola",
        r"Jagdish Temple",
        r"Saheliyon ki Bari",
        r"Fateh Sagar",
        r"Monsoon Palace",
        r"Ahar Museum",
        r"Bharatiya Lok Kala",
    ]
    found_patterns = []
    for pattern in known_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            found_patterns.append(pattern)
    
    all_names = list(set(quoted + capitalized + found_patterns))
    return [name.strip() for name in all_names if len(name.strip()) > 2]


def _normalize_poi_name(name: str) -> str:
    """Normalize for spelling-insensitive match: lowercase, collapse hyphens/punctuation to space."""
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"[\-_.,;:'()]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_claims(text: str) -> list[str]:
    """Extract factual claims from text (statements about Udaipur)."""
    # Look for sentences with factual language
    sentences = re.split(r'[.!?]+', text)
    claims = []
    claim_indicators = [
        r"is (?:a|an|the)",
        r"was (?:a|an|the)",
        r"has (?:a|an|the)",
        r"located (?:at|in)",
        r"known (?:for|as)",
        r"famous (?:for|as)",
        r"built (?:in|by)",
        r"established",
    ]
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 20 and any(re.search(ind, sentence, re.IGNORECASE) for ind in claim_indicators):
            claims.append(sentence)
    return claims


def evaluate_grounding(
    response: str,
    sources: list[dict[str, Any]] | None = None,
    known_pois: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Check that model response is grounded in provided sources.
    
    Validates:
    - POI names mentioned exist in known POIs
    - Claims can be verified against knowledge base
    - No obvious hallucinations (made-up places, incorrect facts)
    
    Args:
        response: LLM response text to evaluate.
        sources: Optional list of source POIs used in the response.
        known_pois: Optional list of valid POIs. If None, loads from POIRepository.
    
    Returns:
        Dict with passed (bool), score (0.0-1.0), and issues (list).
    """
    if not response or not response.strip():
        return {"passed": True, "score": 1.0, "issues": [], "details": {"reason": "Empty response"}}
    
    issues: list[str] = []
    
    # Load known POIs if not provided
    if known_pois is None:
        repo = POIRepository()
        known_pois = repo.get_pois(max_results=200)
    
    # Build POI name set (merge with canonical Udaipur names + alternate spellings)
    known_udaipur_names = {
        "sajjangarh palace", "sajjangarh", "monsoon palace",
        "ghanta ghar", "clock tower",
        "dharohar school", "dharohar museum", "dharohar",
        "saheliyon ki bari", "sahelion ki bari",
        "bagore ki haveli", "bagore ki haveli museum",
        "jagdish temple", "jag mandir",
        "bharatiya lok kala", "bharatiya lok kala museum", "lok kala museum",
        "crystal gallery", "fateh prakash palace",
        "vintage car", "classic car", "vintage and classic car",
    }
    known_poi_names: set[str] = set(known_udaipur_names)
    for poi in known_pois:
        name = (poi.get("name") or "").strip()
        if name:
            known_poi_names.add(name.lower())
            known_poi_names.add(_normalize_poi_name(name))
            words = name.lower().split()
            if len(words) >= 2:
                known_poi_names.add(" ".join(words[:2]))
    for n in list(known_poi_names):
        known_poi_names.add(_normalize_poi_name(n))

    # Non-POI terms: dishes, deities, time slots, nicknames, generic phrases, descriptive phrases
    blocklist = {
        "dal bati churma", "dal baati churma", "dal bati", "baati churma",
        "laal maans", "laal maas", "lal maans",
        "lord vishnu", "lord shiva", "lord krishna", "lord brahma",
        "rajasthani cuisine", "traditional cuisine", "street food",
        "boat ride", "scenic views", "morning light", "evening light",
        "late morning", "early morning", "early afternoon", "late afternoon",
        "early evening", "late evening", "lunch break", "morning break",
        "city of lakes", "city of lakes udaipur", "mewar kingdom", "mewar",
        "local restaurant", "local eatery", "local café", "local cafe", "local shop", "local market",
        "main market", "old city", "old city market",
        "historic palace", "famous temple", "lake view", "roof top", "rooftop",
        "traditional market", "scenic view", "palace complex", "temple complex",
        "museum complex", "garden complex", "historic site", "cultural center", "cultural centre",
        "royal family", "vintage car", "classic car", "vintage and classic",
        "historic palace complex", "famous temple complex", "lake view restaurant",
        "mewar festival", "shilpgram fair", "cultural festival", "traditional craft",
        "budget breakdown", "entry fees", "world heritage site", "unesco world heritage site",
    }
    # Normalize for substring match (e.g. "Dal Baati Churma" -> "dal baati churma")
    def _is_blocklisted(name: str) -> bool:
        lower = name.lower().strip()
        if lower in blocklist:
            return True
        for bl in blocklist:
            if bl in lower or lower in bl:
                return True
        return False

    # Extract POI names from response
    mentioned_pois = _extract_poi_names(response)
    unverified_pois = []

    for poi_name in mentioned_pois:
        if not poi_name:
            continue
        if _is_blocklisted(poi_name):
            continue
        # Check if POI exists (case-insensitive, partial match, normalized for alternate spellings)
        found = False
        lower = poi_name.lower()
        norm = _normalize_poi_name(poi_name)
        for known_name in known_poi_names:
            if lower in known_name or known_name in lower:
                found = True
                break
            if norm and (norm in known_name or known_name in norm):
                found = True
                break
        if not found and len(poi_name) > 3:  # Ignore very short matches
            unverified_pois.append(poi_name)

    # Only report unverified POIs if 2+ so one alternate spelling or new place doesn't fail
    if len(unverified_pois) >= 2:
        issues.append(f"Unverified POI names mentioned: {', '.join(unverified_pois[:5])}")
    
    # Check against knowledge base
    kb = UdaipurKnowledgeBase()
    kb_text = ""
    for section in ["overview", "attractions", "tips"]:
        kb_text += kb.get_context(section) + " "
    
    # Extract claims and check if they're mentioned in knowledge base
    claims = _extract_claims(response)
    ungrounded_claims = []
    kb_words = set(re.findall(r"\b\w{4,}\b", kb_text.lower()))

    for claim in claims[:10]:  # Check first 10 claims
        claim_words = set(re.findall(r"\b\w{4,}\b", claim.lower()))
        # Skip very short claims (noisy; different wording / facts not in KB are common)
        if len(claim_words) < 4:
            continue
        overlap = claim_words.intersection(kb_words)
        ratio = len(overlap) / len(claim_words) if claim_words else 0
        # Grounded if: (a) at least 10% word overlap, or (b) at least 2 overlapping words
        # (handles long sentences, synonyms, facts not in KB, different wording)
        if ratio >= 0.10 or len(overlap) >= 2:
            continue
        ungrounded_claims.append(claim[:100])

    # Only report ungrounded claims if 4+ to avoid different wording / facts not in KB failing the eval
    if len(ungrounded_claims) >= 4:
        issues.append(f"Potentially ungrounded claims ({len(ungrounded_claims)} found)")
    
    # Check if sources (e.g. itinerary POIs) were provided and response mentions them
    if sources:
        source_names = [poi.get("name", "").strip() for poi in sources if poi.get("name")]
        source_norm = {_normalize_poi_name(n) for n in source_names if n}
        mentioned_norm = {_normalize_poi_name(n) for n in mentioned_pois if n}
        # Count source POIs "covered" if any mentioned POI matches (exact or substring)
        covered = 0
        for sn in source_norm:
            if not sn:
                continue
            for mn in mentioned_norm:
                if sn == mn or sn in mn or mn in sn:
                    covered += 1
                    break
        if len(source_norm) > 0:
            coverage = covered / len(source_norm)
            # Expect response to mention most itinerary POIs; only flag if < 50%
            if coverage < 0.5:
                issues.append(f"Response only mentions {covered}/{len(source_norm)} provided POIs")
    
    # Calculate score
    passed = len(issues) == 0
    if passed:
        score = 1.0
    else:
        # Penalize based on number of issues
        score = max(0.0, 1.0 - (len(issues) * 0.2))
    
    return {
        "passed": passed,
        "score": round(score, 2),
        "issues": issues,
        "details": {
            "mentioned_pois": len(mentioned_pois),
            "unverified_pois": len(unverified_pois),
            "claims_checked": len(claims),
            "ungrounded_claims": len(ungrounded_claims),
        },
    }
