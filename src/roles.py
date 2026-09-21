"""
roles.py

Role extraction from posting headers.
"""

import re

AI_ML_PATTERNS = [
    r"\bml engineer\b", r"\bmachine learning\b", r"\bml\b",
    r"\bai engineer\b", r"\bai researcher\b", r"\bai scientist\b",
    r"\bapplied scientist\b", r"\bresearch scientist\b",
    r"\bdeep learning\b", r"\bnlp\b", r"\bcomputer vision\b",
    r"\bllm\b", r"\bgenerative ai\b", r"\bgen ai\b",
    r"\bmlops\b", r"\bai/ml\b", r"\bml/ai\b",
]

DATA_SCIENCE_PATTERNS = [
    r"\bdata scientist\b", r"\bdata science\b",
    r"\bquantitative analyst\b", r"\bquant\b",
    r"\bstatistician\b", r"\bbiostatistician\b",
]

DATA_ENGINEERING_PATTERNS = [
    r"\bdata engineer\b", r"\banalytics engineer\b",
    r"\bdata platform\b", r"\bdata infrastructure\b",
    r"\betl\b", r"\bdata pipeline\b",
]

DATA_ANALYST_PATTERNS = [
    r"\bdata analyst\b", r"\bbusiness analyst\b",
    r"\bbusiness intelligence\b", r"\bbi analyst\b",
    r"\banalytics analyst\b",
]

SOFTWARE_ENGINEER_PATTERNS = [
    r"\bsoftware engineer\b", r"\bsoftware developer\b",
    r"\bfull ?-?stack\b", r"\bbackend\b", r"\bback ?-?end\b",
    r"\bfrontend\b", r"\bfront ?-?end\b",
    r"\bswe\b", r"\bengineer\b", r"\bdeveloper\b", r"\bprogrammer\b",
]

INFRASTRUCTURE_PATTERNS = [
    r"\bdevops\b", r"\bsre\b", r"\bsite reliability\b",
    r"\binfrastructure engineer\b", r"\bplatform engineer\b",
    r"\bcloud engineer\b", r"\bsystems engineer\b",
    r"\bkubernetes\b",
]

SECURITY_PATTERNS = [
    r"\bsecurity engineer\b", r"\bsecurity\b", r"\bappsec\b",
    r"\binfosec\b", r"\bpenetration tester\b", r"\bpentester\b",
]

MOBILE_PATTERNS = [
    r"\bios\b", r"\bandroid\b", r"\bmobile engineer\b",
    r"\bmobile developer\b", r"\breact native\b", r"\bflutter\b",
]

PRODUCT_PATTERNS = [
    r"\bproduct manager\b", r"\bproduct management\b",
    r"\btechnical program manager\b", r"\bprogram manager\b",
    r"\bproject manager\b", r"\bpm\b",
]

DESIGN_PATTERNS = [
    r"\bdesigner\b", r"\bux\b", r"\bui/ux\b", r"\bproduct design\b",
]

MULTIPLE_ROLES_PATTERNS = [
    r"\bmultiple roles\b", r"\bvarious roles\b", r"\bseveral roles\b",
    r"\bmultiple positions\b", r"\ball roles\b", r"\bmany roles\b",
]

SENIOR_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\bstaff\b", r"\bprincipal\b",
    r"\blead\b", r"\bdistinguished\b",
]

JUNIOR_PATTERNS = [
    r"\bjunior\b", r"\bjr\.?\b", r"\bintern\b", r"\binternship\b",
    r"\bentry ?-?level\b", r"\bnew grad\b", r"\bgraduate\b",
]

FOUNDING_PATTERNS = [
    r"\bfounding engineer\b", r"\bfounding\b", r"\bco-?founder\b",
    r"\bfirst engineer\b",
]


def compile_patterns(pattern_strings):
    return [re.compile(pattern, re.IGNORECASE) for pattern in pattern_strings]


ROLE_FAMILIES = {
    "role_ai_ml": compile_patterns(AI_ML_PATTERNS),
    "role_data_science": compile_patterns(DATA_SCIENCE_PATTERNS),
    "role_data_engineering": compile_patterns(DATA_ENGINEERING_PATTERNS),
    "role_data_analyst": compile_patterns(DATA_ANALYST_PATTERNS),
    "role_software_engineer": compile_patterns(SOFTWARE_ENGINEER_PATTERNS),
    "role_infrastructure": compile_patterns(INFRASTRUCTURE_PATTERNS),
    "role_security": compile_patterns(SECURITY_PATTERNS),
    "role_mobile": compile_patterns(MOBILE_PATTERNS),
    "role_product": compile_patterns(PRODUCT_PATTERNS),
    "role_design": compile_patterns(DESIGN_PATTERNS),
    "role_multiple": compile_patterns(MULTIPLE_ROLES_PATTERNS),
}

SENIORITY_FAMILIES = {
    "seniority_senior": compile_patterns(SENIOR_PATTERNS),
    "seniority_junior": compile_patterns(JUNIOR_PATTERNS),
    "seniority_founding": compile_patterns(FOUNDING_PATTERNS),
}


def matches_any(text, regexes):
    for regex in regexes:
        if regex.search(text) is not None:
            return True

    return False


def extract_role_flags(header):
    """
    Return a dict of role and seniority flags read from the header.

    Flags are independent: one posting can advertise several roles, and
    "Multiple Roles" postings often name none specifically.
    """
    flags = {}

    for family_name, regexes in ROLE_FAMILIES.items():
        flags[family_name] = matches_any(header, regexes)

    for family_name, regexes in SENIORITY_FAMILIES.items():
        flags[family_name] = matches_any(header, regexes)

    any_role_found = False

    for family_name in ROLE_FAMILIES:
        if flags[family_name]:
            any_role_found = True

    flags["role_found"] = any_role_found

    return flags