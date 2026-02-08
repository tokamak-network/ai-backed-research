"""Academic categories and journal classification system."""

from typing import Dict, List, Optional

# Academic category system - Major fields → Subfields
ACADEMIC_CATEGORIES = {
    "computer_science": {
        "name": "Computer Science",
        "icon": "💻",
        "subfields": {
            "ai_ml": {
                "name": "Artificial Intelligence & Machine Learning",
                "expert_pool": [
                    "deep_learning_expert",
                    "nlp_expert",
                    "computer_vision_expert"
                ]
            },
            "systems": {
                "name": "Systems, Networks & Distributed Computing",
                "expert_pool": [
                    "distributed_systems_expert",
                    "os_expert",
                    "networking_expert"
                ]
            },
            "theory": {
                "name": "Theory & Algorithms",
                "expert_pool": [
                    "algorithms_expert",
                    "complexity_theory_expert",
                    "formal_methods_expert"
                ]
            },
            "security": {
                "name": "Security, Cryptography & Privacy",
                "expert_pool": [
                    "cryptography_expert",
                    "network_security_expert",
                    "blockchain_expert"
                ]
            },
            "software_eng": {
                "name": "Software Engineering & Programming Languages",
                "expert_pool": [
                    "software_architecture_expert",
                    "programming_languages_expert",
                    "testing_expert"
                ]
            },
            "hci": {
                "name": "Human-Computer Interaction",
                "expert_pool": [
                    "ux_expert",
                    "interaction_design_expert",
                    "accessibility_expert"
                ]
            }
        }
    },

    "engineering": {
        "name": "Engineering & Technology",
        "icon": "⚙️",
        "subfields": {
            "electrical": {
                "name": "Electrical & Electronics Engineering",
                "expert_pool": [
                    "circuits_expert",
                    "signal_processing_expert",
                    "embedded_systems_expert"
                ]
            },
            "mechanical": {
                "name": "Mechanical Engineering",
                "expert_pool": [
                    "thermodynamics_expert",
                    "fluid_mechanics_expert",
                    "materials_expert"
                ]
            },
            "civil": {
                "name": "Civil & Structural Engineering",
                "expert_pool": [
                    "structural_analysis_expert",
                    "geotechnical_expert",
                    "transportation_expert"
                ]
            },
            "materials": {
                "name": "Materials Science",
                "expert_pool": [
                    "nanomaterials_expert",
                    "polymers_expert",
                    "metallurgy_expert"
                ]
            }
        }
    },

    "natural_sciences": {
        "name": "Natural Sciences",
        "icon": "🔬",
        "subfields": {
            "physics": {
                "name": "Physics & Astronomy",
                "expert_pool": [
                    "quantum_physics_expert",
                    "particle_physics_expert",
                    "astrophysics_expert"
                ]
            },
            "chemistry": {
                "name": "Chemistry",
                "expert_pool": [
                    "organic_chemistry_expert",
                    "inorganic_chemistry_expert",
                    "physical_chemistry_expert"
                ]
            },
            "biology": {
                "name": "Biology & Life Sciences",
                "expert_pool": [
                    "molecular_biology_expert",
                    "genetics_expert",
                    "ecology_expert"
                ]
            },
            "earth_science": {
                "name": "Earth & Environmental Sciences",
                "expert_pool": [
                    "climate_science_expert",
                    "geology_expert",
                    "oceanography_expert"
                ]
            },
            "mathematics": {
                "name": "Pure Mathematics",
                "expert_pool": [
                    "number_theory_expert",
                    "topology_expert",
                    "analysis_expert"
                ]
            }
        }
    },

    "social_sciences": {
        "name": "Social Sciences",
        "icon": "👥",
        "subfields": {
            "economics": {
                "name": "Economics",
                "expert_pool": [
                    "microeconomics_expert",
                    "macroeconomics_expert",
                    "econometrics_expert"
                ]
            },
            "sociology": {
                "name": "Sociology",
                "expert_pool": [
                    "social_theory_expert",
                    "urban_sociology_expert",
                    "social_networks_expert"
                ]
            },
            "political_science": {
                "name": "Political Science & International Relations",
                "expert_pool": [
                    "political_theory_expert",
                    "comparative_politics_expert",
                    "international_relations_expert"
                ]
            },
            "psychology": {
                "name": "Psychology & Behavioral Sciences",
                "expert_pool": [
                    "cognitive_psychology_expert",
                    "behavioral_economics_expert",
                    "social_psychology_expert"
                ]
            },
            "anthropology": {
                "name": "Anthropology",
                "expert_pool": [
                    "cultural_anthropology_expert",
                    "archaeology_expert",
                    "linguistic_anthropology_expert"
                ]
            }
        }
    },

    "humanities": {
        "name": "Humanities",
        "icon": "📚",
        "subfields": {
            "philosophy": {
                "name": "Philosophy",
                "expert_pool": [
                    "ethics_expert",
                    "epistemology_expert",
                    "metaphysics_expert"
                ]
            },
            "history": {
                "name": "History",
                "expert_pool": [
                    "ancient_history_expert",
                    "modern_history_expert",
                    "historiography_expert"
                ]
            },
            "literature": {
                "name": "Literature & Literary Studies",
                "expert_pool": [
                    "literary_theory_expert",
                    "comparative_literature_expert",
                    "poetry_expert"
                ]
            },
            "linguistics": {
                "name": "Linguistics",
                "expert_pool": [
                    "syntax_expert",
                    "semantics_expert",
                    "phonology_expert"
                ]
            }
        }
    },

    "business_economics": {
        "name": "Business & Economics",
        "icon": "💼",
        "subfields": {
            "finance": {
                "name": "Finance & Accounting",
                "expert_pool": [
                    "corporate_finance_expert",
                    "financial_markets_expert",
                    "accounting_expert"
                ]
            },
            "management": {
                "name": "Management & Strategy",
                "expert_pool": [
                    "strategic_management_expert",
                    "organizational_behavior_expert",
                    "leadership_expert"
                ]
            },
            "marketing": {
                "name": "Marketing",
                "expert_pool": [
                    "consumer_behavior_expert",
                    "digital_marketing_expert",
                    "brand_management_expert"
                ]
            }
        }
    },

    "medicine_health": {
        "name": "Medicine & Health Sciences",
        "icon": "⚕️",
        "subfields": {
            "clinical": {
                "name": "Clinical Medicine",
                "expert_pool": [
                    "internal_medicine_expert",
                    "surgery_expert",
                    "diagnostics_expert"
                ]
            },
            "public_health": {
                "name": "Public Health & Epidemiology",
                "expert_pool": [
                    "epidemiology_expert",
                    "health_policy_expert",
                    "disease_prevention_expert"
                ]
            },
            "pharmacology": {
                "name": "Pharmacology & Pharmaceutical Sciences",
                "expert_pool": [
                    "drug_discovery_expert",
                    "pharmacokinetics_expert",
                    "clinical_trials_expert"
                ]
            }
        }
    },

    "law_policy": {
        "name": "Law & Public Policy",
        "icon": "⚖️",
        "subfields": {
            "law": {
                "name": "Law & Legal Studies",
                "expert_pool": [
                    "constitutional_law_expert",
                    "international_law_expert",
                    "corporate_law_expert"
                ]
            },
            "policy": {
                "name": "Public Policy & Administration",
                "expert_pool": [
                    "policy_analysis_expert",
                    "public_administration_expert",
                    "governance_expert"
                ]
            }
        }
    }
}


def get_major_fields() -> List[Dict[str, str]]:
    """Get list of major academic fields."""
    return [
        {
            "id": field_id,
            "name": field_data["name"],
            "icon": field_data["icon"]
        }
        for field_id, field_data in ACADEMIC_CATEGORIES.items()
    ]


def get_subfields(major_field: str) -> List[Dict[str, str]]:
    """Get subfields for a major field."""
    if major_field not in ACADEMIC_CATEGORIES:
        return []

    field_data = ACADEMIC_CATEGORIES[major_field]
    return [
        {
            "id": subfield_id,
            "name": subfield_data["name"]
        }
        for subfield_id, subfield_data in field_data["subfields"].items()
    ]


def get_expert_pool(major_field: str, subfield: str) -> List[str]:
    """Get expert pool for a specific subfield."""
    if major_field not in ACADEMIC_CATEGORIES:
        return []

    field_data = ACADEMIC_CATEGORIES[major_field]
    if subfield not in field_data["subfields"]:
        return []

    return field_data["subfields"][subfield]["expert_pool"]


def get_category_name(major_field: str, subfield: str) -> str:
    """Get full category name."""
    if major_field not in ACADEMIC_CATEGORIES:
        return "Unknown"

    major_name = ACADEMIC_CATEGORIES[major_field]["name"]

    field_data = ACADEMIC_CATEGORIES[major_field]
    if subfield not in field_data["subfields"]:
        return major_name

    subfield_name = field_data["subfields"][subfield]["name"]
    return f"{major_name} → {subfield_name}"


def get_domain_description(major_field: str, subfield: str = "") -> str:
    """Get human-readable domain description for agent prompts.

    Returns e.g. "Philosophy (Ethics & Moral Theory)" or "Computer Science"
    """
    if major_field not in ACADEMIC_CATEGORIES:
        return "interdisciplinary research"

    major_name = ACADEMIC_CATEGORIES[major_field]["name"]
    if subfield and subfield in ACADEMIC_CATEGORIES[major_field]["subfields"]:
        sub_name = ACADEMIC_CATEGORIES[major_field]["subfields"][subfield]["name"]
        return f"{major_name} ({sub_name})"
    return major_name


def _build_category_list() -> str:
    """Build formatted category list for LLM prompt."""
    lines = []
    for major, data in ACADEMIC_CATEGORIES.items():
        for sub, sub_data in data["subfields"].items():
            lines.append(f"  {major}/{sub} — {data['name']}: {sub_data['name']}")
    return "\n".join(lines)


_CATEGORY_LIST_CACHE: Optional[str] = None


def _get_category_list() -> str:
    global _CATEGORY_LIST_CACHE
    if _CATEGORY_LIST_CACHE is None:
        _CATEGORY_LIST_CACHE = _build_category_list()
    return _CATEGORY_LIST_CACHE


async def suggest_category_llm(topic: str) -> dict:
    """Classify a research topic into an academic category using LLM.

    Works for any language — the LLM translates and understands the topic.
    Falls back to keyword matching if the LLM call fails.
    """
    import json as _json
    import logging
    logger = logging.getLogger(__name__)

    try:
        from .model_config import create_llm_for_role
        llm = create_llm_for_role("categorizer")

        prompt = f"""Classify this research topic into exactly one academic category.

TOPIC: {topic}

VALID CATEGORIES (format: major/subfield):
{_get_category_list()}

Respond with ONLY one line in this exact format:
major/subfield

Example: social_sciences/anthropology"""

        response = await llm.generate(
            prompt=prompt,
            system="You classify academic topics. Respond with ONLY the category in major/subfield format. No JSON, no explanation. The topic may be in any language.",
            temperature=0.0,
            max_tokens=50,
        )

        content = response.content.strip().lower()
        # Extract major/subfield from response
        for line in content.split("\n"):
            line = line.strip().strip("`").strip('"').strip("'")
            if "/" in line:
                parts = line.split("/")
                major = parts[0].strip()
                subfield = parts[1].strip()
                if major in ACADEMIC_CATEGORIES and subfield in ACADEMIC_CATEGORIES[major]["subfields"]:
                    return {"major": major, "subfield": subfield}

        logger.warning(f"LLM returned unparseable category '{content}', falling back to keywords")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"LLM category classification failed: {e}, falling back to keywords")

    return suggest_category_from_topic(topic)


def suggest_category_from_topic(topic: str) -> dict:
    """Suggest academic category based on English keyword matching (sync fallback)."""
    topic_lower = topic.lower()

    # Blockchain/Crypto
    if any(kw in topic_lower for kw in ['blockchain', 'crypto', 'ethereum', 'bitcoin', 'rollup', 'zk', 'zero-knowledge', 'smart contract', 'defi', 'consensus', 'proof of stake', 'proof of work']):
        return {"major": "computer_science", "subfield": "security"}
    # AI/ML
    if any(kw in topic_lower for kw in ['machine learning', 'deep learning', 'neural network', 'nlp', 'natural language', 'computer vision', 'reinforcement learning', 'transformer', 'gpt', 'llm']):
        return {"major": "computer_science", "subfield": "ai_ml"}
    # Systems
    if any(kw in topic_lower for kw in ['distributed', 'database', 'scalability', 'networking', 'cloud', 'operating system']):
        return {"major": "computer_science", "subfield": "systems"}
    # Software/HCI
    if any(kw in topic_lower for kw in ['software engineering', 'devops', 'programming language', 'compiler']):
        return {"major": "computer_science", "subfield": "software_eng"}
    if any(kw in topic_lower for kw in ['user experience', 'ux', 'hci', 'human-computer', 'interface design']):
        return {"major": "computer_science", "subfield": "hci"}
    # Medicine
    if any(kw in topic_lower for kw in ['medicine', 'clinical', 'surgery', 'diagnosis', 'therapeutic', 'patient', 'hospital']):
        return {"major": "medicine_health", "subfield": "clinical"}
    if any(kw in topic_lower for kw in ['epidemiology', 'public health', 'disease prevention', 'global health', 'pandemic', 'vaccine', 'health', 'pollution', 'smoke', 'mortality', 'nutrition', 'maternal']):
        return {"major": "medicine_health", "subfield": "public_health"}
    if any(kw in topic_lower for kw in ['pharmacology', 'drug', 'pharmaceutical', 'clinical trial', 'toxicology']):
        return {"major": "medicine_health", "subfield": "pharmacology"}
    # Biology
    if any(kw in topic_lower for kw in ['biology', 'genetics', 'genomics', 'molecular', 'ecology', 'evolution', 'dna', 'rna', 'protein', 'species', 'phylogen']):
        return {"major": "natural_sciences", "subfield": "biology"}
    # Chemistry
    if any(kw in topic_lower for kw in ['chemistry', 'chemical', 'molecule', 'reaction', 'catalyst', 'polymer']):
        return {"major": "natural_sciences", "subfield": "chemistry"}
    # Physics
    if any(kw in topic_lower for kw in ['physics', 'quantum', 'particle', 'astrophysics', 'cosmology', 'relativity', 'optics']):
        return {"major": "natural_sciences", "subfield": "physics"}
    # Earth
    if any(kw in topic_lower for kw in ['earth', 'climate', 'environment', 'geology', 'oceanography', 'sustainability', 'ecosystem']):
        return {"major": "natural_sciences", "subfield": "earth_science"}
    # Math
    if any(kw in topic_lower for kw in ['mathematics', 'theorem', 'algebra', 'topology', 'number theory', 'calculus', 'statistics']):
        return {"major": "natural_sciences", "subfield": "mathematics"}
    # Psychology
    if any(kw in topic_lower for kw in ['psychology', 'cognitive', 'behavioral', 'mental health', 'neuroscience']):
        return {"major": "social_sciences", "subfield": "psychology"}
    # Sociology
    if any(kw in topic_lower for kw in ['sociology', 'social structure', 'inequality', 'demography', 'urbanization']):
        return {"major": "social_sciences", "subfield": "sociology"}
    # Political Science
    if any(kw in topic_lower for kw in ['political', 'government', 'democracy', 'election', 'geopolitics', 'international relations', 'diplomacy']):
        return {"major": "social_sciences", "subfield": "political_science"}
    # Economics
    if any(kw in topic_lower for kw in ['economics', 'microeconomics', 'macroeconomics', 'econometrics', 'game theory']):
        return {"major": "social_sciences", "subfield": "economics"}
    # Anthropology
    if any(kw in topic_lower for kw in ['anthropology', 'ethnography', 'archaeology', 'indigenous', 'fossil', 'homo sapiens', 'hominid', 'paleontol']):
        return {"major": "social_sciences", "subfield": "anthropology"}
    # Philosophy
    if any(kw in topic_lower for kw in ['philosophy', 'ethics', 'ethical', 'epistemolog', 'metaphysic', 'moral', 'existential']):
        return {"major": "humanities", "subfield": "philosophy"}
    # History
    if any(kw in topic_lower for kw in ['history', 'ancient', 'medieval', 'colonial', 'war', 'civilization']):
        return {"major": "humanities", "subfield": "history"}
    # Literature
    if any(kw in topic_lower for kw in ['literature', 'literary', 'novel', 'poetry', 'narrative', 'fiction']):
        return {"major": "humanities", "subfield": "literature"}
    # Linguistics
    if any(kw in topic_lower for kw in ['linguistics', 'language', 'syntax', 'semantics', 'phonology', 'grammar']):
        return {"major": "humanities", "subfield": "linguistics"}
    # Law
    if any(kw in topic_lower for kw in ['law', 'legal', 'court', 'constitutional', 'jurisprudence', 'legislation']):
        return {"major": "law_policy", "subfield": "law"}
    # Policy
    if any(kw in topic_lower for kw in ['policy', 'regulation', 'governance', 'public administration', 'reform']):
        return {"major": "law_policy", "subfield": "policy"}
    # Finance/Business
    if any(kw in topic_lower for kw in ['finance', 'trading', 'market', 'investment', 'portfolio', 'accounting']):
        return {"major": "business_economics", "subfield": "finance"}
    if any(kw in topic_lower for kw in ['management', 'strategy', 'leadership', 'organizational', 'innovation', 'startup']):
        return {"major": "business_economics", "subfield": "management"}
    if any(kw in topic_lower for kw in ['marketing', 'brand', 'consumer', 'advertising']):
        return {"major": "business_economics", "subfield": "marketing"}
    # Engineering
    if any(kw in topic_lower for kw in ['electrical', 'circuit', 'signal processing', 'semiconductor']):
        return {"major": "engineering", "subfield": "electrical"}
    if any(kw in topic_lower for kw in ['mechanical', 'thermodynamics', 'fluid', 'robotics']):
        return {"major": "engineering", "subfield": "mechanical"}
    if any(kw in topic_lower for kw in ['civil', 'structural', 'construction', 'bridge', 'geotechnical']):
        return {"major": "engineering", "subfield": "civil"}
    if any(kw in topic_lower for kw in ['materials science', 'nanomaterial', 'metallurgy', 'composite', 'ceramic']):
        return {"major": "engineering", "subfield": "materials"}

    return {"major": "computer_science", "subfield": "theory"}
