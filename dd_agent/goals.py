"""Goal profiles.

A goal decides which questions get asked, which searches run, and which sections the report has.
Switching the goal changes the content of the report, not just its headings.

Query placeholders: {name} subject name, {hint} disambiguating context from the anchor or registry,
{company} resolved company name (for people anchored to a company).
"""
from dataclasses import dataclass, field


@dataclass
class Question:
    id: str
    text: str
    queries: list[str] = field(default_factory=list)
    uses_registry: bool = False


@dataclass
class Goal:
    id: str
    label: str
    purpose: str
    questions: dict[str, list[Question]]  # keyed by subject kind
    outreach: bool = False


GOALS: dict[str, Goal] = {
    "procurement": Goal(
        id="procurement",
        label="Supplier due diligence (procurement)",
        purpose="Decide whether it is safe to sign a supply contract with the subject.",
        questions={
            "organization": [
                Question("legal_status", "Is the entity legally registered and active, and since when?",
                         [], uses_registry=True),
                Question("control", "Who manages and controls it, and are there red flags around those people?",
                         ['"{name}" owner OR CEO OR jednatel'], uses_registry=True),
                Question("legal_risk", "Is it involved in lawsuits, insolvency, sanctions or regulatory fines?",
                         ['"{name}" lawsuit OR insolvency OR sanctions OR fine',
                          '"{name}" soud OR insolvence OR pokuta'], uses_registry=True),
                Question("delivery_reputation", "Do customers or partners report delivery, quality or payment problems?",
                         ['"{name}" reviews complaints {hint}']),
                Question("esg", "Are there environmental, labour or safety violations?",
                         ['"{name}" environmental OR labour OR safety violation']),
            ],
            "person": [
                Question("roles", "Which companies does this person run or represent?",
                         ['"{name}" {hint} CEO OR owner OR director OR jednatel'], uses_registry=True),
                Question("legal_risk", "Is the person linked to lawsuits, insolvencies, fraud or sanctions?",
                         ['"{name}" {hint} lawsuit OR fraud OR insolvency OR sanctions']),
                Question("track_record", "What is their verifiable business track record?",
                         ['"{name}" {hint}']),
            ],
        },
    ),
    "hiring": Goal(
        id="hiring",
        label="Hiring",
        purpose="Verify a candidate's professional claims before an interview or offer "
                "(or, for an organization, check it as a prospective employer).",
        questions={
            "person": [
                Question("identity", "Which public profiles belong to this person (and which are namesakes)?",
                         ['"{name}" {hint} LinkedIn', '"{name}" {hint}']),
                Question("experience", "What professional experience can be verified from public sources?",
                         ['"{name}" {hint} experience OR engineer OR manager OR founder'], uses_registry=True),
                Question("public_work", "What public work shows their skills (code, talks, articles, projects)?",
                         ['"{name}" github OR conference talk OR article']),
                Question("conduct", "Are there public professional-conduct concerns?",
                         ['"{name}" {hint} controversy OR lawsuit OR dismissed']),
            ],
            "organization": [
                Question("stability", "Is the employer stable (age, insolvency, layoffs, funding)?",
                         ['"{name}" layoffs OR funding OR acquisition'], uses_registry=True),
                Question("workplace", "What do employees publicly report about working there?",
                         ['"{name}" employee reviews OR atmoskop OR glassdoor']),
                Question("leadership", "Who leads the company?",
                         ['"{name}" CEO OR founder OR leadership'], uses_registry=True),
            ],
        },
    ),
    "sales": Goal(
        id="sales",
        label="Sales prospecting",
        purpose="Prepare a relevant, well-informed first conversation with the subject.",
        outreach=True,
        questions={
            "person": [
                Question("role", "What is their current role and how much buying authority do they likely have?",
                         ['"{name}" {hint} LinkedIn'], uses_registry=True),
                Question("priorities", "What are they and their company currently focused on?",
                         ['"{name}" {hint} interview OR talk OR post']),
                Question("hooks", "What recent public activity could open a conversation?",
                         ['"{name}" {hint} 2026']),
            ],
            "organization": [
                Question("decision_makers", "Who are the decision makers?",
                         ['"{name}" CEO OR CTO OR head of'], uses_registry=True),
                Question("priorities", "What is the company focused on right now (news, expansion, hiring)?",
                         ['"{name}" news 2026', '"{name}" hiring OR expansion OR launches']),
                Question("profile", "What does the company do, how big is it, and who are its customers?",
                         ['"{name}" {hint} customers OR clients OR products'], uses_registry=True),
            ],
        },
    ),
    "investor": Goal(
        id="investor",
        label="Investment / partnership due diligence",
        purpose="Decide whether to invest in or partner with the subject, and separate a strong pitch from "
                "verifiable substance.",
        questions={
            "organization": [
                Question("legal_entity", "Is it a registered legal entity, and since when?",
                         ['"{name}" company registration OR founded OR "s.r.o." OR "a.s."'], uses_registry=True),
                Question("founders_owners", "Who founded and owns it?",
                         ['"{name}" founder OR CEO OR co-founder'], uses_registry=True),
                Question("traction", "What traction is verifiable: product, customers, revenue signals?",
                         ['"{name}" customers OR product OR launch OR github', '"{name}" {hint}']),
                Question("funding", "Has it raised money, and from whom?",
                         ['"{name}" funding OR investors OR seed OR raised']),
                Question("red_flags", "Are there red flags: lawsuits, insolvency, failed ventures?",
                         ['"{name}" lawsuit OR insolvency OR scam OR controversy'], uses_registry=True),
            ],
            "person": [
                Question("ventures", "Which companies has the founder started or run?",
                         ['"{name}" {hint} founder OR CEO OR co-founder'], uses_registry=True),
                Question("track_record", "What verifiable track record backs the public claims?",
                         ['"{name}" {hint}', '"{name}" github OR hackathon OR project']),
                Question("red_flags", "Are there red flags: lawsuits, insolvencies, disputes?",
                         ['"{name}" {hint} lawsuit OR fraud OR insolvency']),
            ],
        },
    ),
}


def get_goal(goal_id: str) -> Goal:
    if goal_id not in GOALS:
        raise ValueError(f"Unknown goal '{goal_id}'. Choose one of: {', '.join(GOALS)}")
    return GOALS[goal_id]
