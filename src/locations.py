"""
locations.py

Location extraction from posting headers.

There is no location field in the convention, so we match a gazetteer of
city and region names against the header text. This is recall-limited by
design: a city we do not list is simply not found, which is preferable to
guessing from ambiguous tokens.


"Washington" means the state in "Seattle, Washington" and the city in
"Washington, DC". We match the DC forms first so the state does not
swallow them.

Two-letter codes (NY, CA, SF) are matched only with word boundaries and
only alongside a comma or a known city, since bare "CA" appears in
unrelated contexts.

Pay-transparency laws are keyed to jurisdiction, so states with such laws
get their own flags: Colorado (Jan 2021), NYC (Nov 2022), California and
Washington (Jan 2023).
"""

import re

# Order matters within each group: longer and more specific forms first.
NYC_PATTERNS = [
    r"\bnew york city\b",
    r"\bnew york,?\s*n\.?y\.?\b",
    r"\bnyc\b",
    r"\bbrooklyn\b",
    r"\bmanhattan\b",
    r"\bqueens,?\s*ny\b",
    r"\bnew york\b",
]

# DC must be tested before Washington state.
DC_PATTERNS = [
    r"\bwashington,?\s*d\.?c\.?\b",
    r"\bwashington dc\b",
    r"\bd\.c\.\b",
]

CALIFORNIA_PATTERNS = [
    r"\bsan francisco\b",
    r"\bsf bay area\b",
    r"\bbay area\b",
    r"\bsilicon valley\b",
    r"\blos angeles\b",
    r"\bsan diego\b",
    r"\bsan jose\b",
    r"\bpalo alto\b",
    r"\bmountain view\b",
    r"\bmenlo park\b",
    r"\bsanta monica\b",
    r"\bsanta clara\b",
    r"\bsunnyvale\b",
    r"\bcupertino\b",
    r"\boakland\b",
    r"\bberkeley\b",
    r"\bpasadena\b",
    r"\birvine\b",
    r"\bcalifornia\b",
    r"\bsfba\b",
    r"\bsf\b",
    r",\s*ca\b",
]

COLORADO_PATTERNS = [
    r"\bdenver\b",
    r"\bboulder\b",
    r"\bcolorado springs\b",
    r"\bcolorado\b",
    r",\s*co\b",
]

WASHINGTON_STATE_PATTERNS = [
    r"\bseattle\b",
    r"\bbellevue\b",
    r"\bredmond\b",
    r"\bwashington state\b",
    r",\s*wa\b",
]

# Other US metros, for the control group. Not exhaustive; recall matters
# less here than not misclassifying them as treated jurisdictions.
OTHER_US_PATTERNS = [
    r"\bboston\b", r"\bcambridge,?\s*ma\b", r"\bchicago\b", r"\baustin\b",
    r"\bdallas\b", r"\bhouston\b", r"\batlanta\b", r"\bmiami\b",
    r"\bportland,?\s*or\b", r"\bphiladelphia\b", r"\bphoenix\b",
    r"\bpittsburgh\b", r"\bnashville\b", r"\bminneapolis\b", r"\bdetroit\b",
    r"\bsalt lake city\b", r"\bras vegas\b", r"\blas vegas\b",
    r"\bann arbor\b", r"\braleigh\b", r"\bdurham,?\s*nc\b", r"\bcharlotte\b",
    r"\bst\.? louis\b", r"\bkansas city\b", r"\bcolumbus\b",
    r"\bnew jersey\b", r"\bconnecticut\b", r"\bmassachusetts\b",
    r"\btexas\b", r"\bflorida\b", r"\billinois\b", r"\butah\b",
    r"\bunited states\b", r"\busa\b", r"\bu\.s\.a?\.?\b", r"\(us\)",
    r"\bus only\b", r"\bus-based\b",
]

# Non-US locations. Used to exclude them from the US-only DiD sample.
NON_US_PATTERNS = [
    r"\blondon\b", r"\bberlin\b", r"\bparis\b", r"\bamsterdam\b",
    r"\bdublin\b", r"\bbarcelona\b", r"\bmadrid\b", r"\blisbon\b",
    r"\bstockholm\b", r"\bcopenhagen\b", r"\boslo\b", r"\bhelsinki\b",
    r"\bzurich\b", r"\bgeneva\b", r"\bmunich\b", r"\bhamburg\b",
    r"\bvienna\b", r"\bprague\b", r"\bwarsaw\b", r"\bkrakow\b",
    r"\bwroclaw\b", r"\bbudapest\b", r"\bbucharest\b", r"\bathens\b",
    r"\bmilan\b", r"\brome\b", r"\bbrussels\b", r"\bbruges\b",
    r"\btoronto\b", r"\bvancouver\b", r"\bmontreal\b", r"\bottawa\b",
    r"\bcalgary\b", r"\bcanada\b",
    r"\bsydney\b", r"\bmelbourne\b", r"\bbrisbane\b", r"\baustralia\b",
    r"\bauckland\b", r"\bnew zealand\b",
    r"\bbangalore\b", r"\bbengaluru\b", r"\bmumbai\b", r"\bdelhi\b",
    r"\bhyderabad\b", r"\bpune\b", r"\bchennai\b", r"\bindia\b",
    r"\bsingapore\b", r"\btokyo\b", r"\bjapan\b", r"\bseoul\b",
    r"\bhong kong\b", r"\bshanghai\b", r"\bbeijing\b", r"\btaipei\b",
    r"\bbangkok\b", r"\bthailand\b", r"\bjakarta\b", r"\bmanila\b",
    r"\btel aviv\b", r"\bisrael\b", r"\bdubai\b", r"\babu dhabi\b",
    r"\bsao paulo\b", r"\bs[ãa]o paulo\b", r"\brio de janeiro\b",
    r"\bflorianopolis\b", r"\bbrazil\b", r"\bbuenos aires\b",
    r"\bargentina\b", r"\bmexico city\b", r"\bmexico\b", r"\bbogota\b",
    r"\bcolombia\b", r"\bsantiago\b", r"\bchile\b", r"\blima\b",
    r"\bcape town\b", r"\bjohannesburg\b", r"\bnairobi\b", r"\blagos\b",
    r"\bcairo\b", r"\bistanbul\b", r"\bmoscow\b", r"\bkyiv\b", r"\bkiev\b",
    r"\bedinburgh\b", r"\bmanchester\b", r"\bbristol\b", r"\bcambridge,?\s*uk\b",
    r"\boxford\b", r"\bglasgow\b", r"\bbelfast\b", r"\bleeds\b",
    r"\buk\b", r"\bunited kingdom\b", r"\bengland\b", r"\bscotland\b",
    r"\bireland\b", r"\bgermany\b", r"\bfrance\b", r"\bspain\b",
    r"\bitaly\b", r"\bportugal\b", r"\bnetherlands\b", r"\bbelgium\b",
    r"\bswitzerland\b", r"\bsweden\b", r"\bnorway\b", r"\bdenmark\b",
    r"\bfinland\b", r"\bpoland\b", r"\bczech\b", r"\baustria\b",
    r"\bromania\b", r"\bgreece\b", r"\bhungary\b", r"\bestonia\b",
    r"\btallinn\b", r"\briga\b", r"\bvilnius\b", r"\beurope\b",
    r"\beu\b", r"\bemea\b", r"\bapac\b", r"\blatam\b",
]


def compile_patterns(pattern_strings):
    return [re.compile(pattern, re.IGNORECASE) for pattern in pattern_strings]


NYC_REGEXES = compile_patterns(NYC_PATTERNS)
DC_REGEXES = compile_patterns(DC_PATTERNS)
CALIFORNIA_REGEXES = compile_patterns(CALIFORNIA_PATTERNS)
COLORADO_REGEXES = compile_patterns(COLORADO_PATTERNS)
WASHINGTON_STATE_REGEXES = compile_patterns(WASHINGTON_STATE_PATTERNS)
OTHER_US_REGEXES = compile_patterns(OTHER_US_PATTERNS)
NON_US_REGEXES = compile_patterns(NON_US_PATTERNS)


def matches_any(text, regexes):
    for regex in regexes:
        if regex.search(text) is not None:
            return True

    return False


def extract_location_flags(header):
    """
    Return a dict of location flags read from the header.

    A posting can match several places at once ("London / SF / NYC"), so
    these are independent booleans rather than a single category. The
    notebook decides how to handle multi-location postings.
    """
    mentions_dc = matches_any(header, DC_REGEXES)

    # Strip DC before testing Washington state, so "Washington, DC"
    # does not register as Seattle's state.
    header_without_dc = header

    if mentions_dc:
        for regex in DC_REGEXES:
            header_without_dc = regex.sub(" ", header_without_dc)

    mentions_nyc = matches_any(header, NYC_REGEXES)
    mentions_california = matches_any(header, CALIFORNIA_REGEXES)
    mentions_colorado = matches_any(header, COLORADO_REGEXES)
    mentions_washington = matches_any(header_without_dc, WASHINGTON_STATE_REGEXES)
    mentions_other_us = matches_any(header, OTHER_US_REGEXES)
    mentions_non_us = matches_any(header, NON_US_REGEXES)

    mentions_any_us = (
        mentions_nyc
        or mentions_california
        or mentions_colorado
        or mentions_washington
        or mentions_dc
        or mentions_other_us
    )

    return {
        "mentions_nyc": mentions_nyc,
        "mentions_california": mentions_california,
        "mentions_colorado": mentions_colorado,
        "mentions_washington": mentions_washington,
        "mentions_dc": mentions_dc,
        "mentions_other_us": mentions_other_us,
        "mentions_non_us": mentions_non_us,
        "mentions_any_us": mentions_any_us,
        "location_found": mentions_any_us or mentions_non_us,
    }