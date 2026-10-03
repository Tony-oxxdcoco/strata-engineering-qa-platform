"""Hand-authored controlled configuration examples, never engineering standards."""
import copy


def advanced_fixtures(combination):
    configuration = copy.deepcopy(combination)
    configuration["configuration_complete"] = True
    bad_configuration = copy.deepcopy(configuration)
    bad_configuration["combinations"][0]["terms"][0]["factor"] = 1.4
    missing_configuration = copy.deepcopy(configuration)
    missing_configuration.pop("configuration_complete")
    source = {"synthetic": True, "project": {"name": "Controlled ETABS handoff", "revision": "E1"}, "units": {"force": "kN"}, "transfer": {"vertical": 100}}
    target = {"synthetic": True, "project": {"name": "Controlled SAFE handoff", "revision": "S1"}, "units": {"force": "N"}, "transfer": {"vertical": 100000}}
    bad_target = copy.deepcopy(target)
    bad_target["transfer"]["vertical"] = 120000
    seismic = {"synthetic": True, "configuration_complete": True, "project": {"name": "Controlled settings", "revision": "S1"}, "seismic": {"period_method": "supplied-profile", "eccentricity": 0.05}}
    seismic_bad = copy.deepcopy(seismic)
    seismic_bad["seismic"]["eccentricity"] = 0.2
    mass = {"synthetic": True, "configuration_complete": True, "project": {"name": "Controlled settings", "revision": "M1"}, "mass": {"include_self_weight": True, "source": "approved-schedule"}}
    mass_missing = copy.deepcopy(mass)
    mass_missing["mass"].pop("source")
    settings = {"synthetic": True, "configuration_complete": True, "project": {"name": "Controlled settings", "revision": "A1"}, "settings": {"diaphragm": "rigid", "mesh_size": 1.0}}
    cases = [
        ("Combination configuration · correct", configuration, "combination-configuration"),
        ("Combination configuration · wrong factor", bad_configuration, "combination-configuration"),
        ("Combination configuration · completeness unknown", missing_configuration, "combination-configuration"),
        ("ETABS handoff · source E1", source, "handoff"),
        ("SAFE handoff · matching target S1", target, "handoff"),
        ("SAFE handoff · deliberate mismatch", bad_target, "handoff"),
        ("Seismic settings · correct", seismic, "seismic-configuration"),
        ("Seismic settings · deliberate error", seismic_bad, "seismic-configuration"),
        ("Mass source · correct", mass, "mass-source"),
        ("Mass source · missing evidence", mass_missing, "mass-source"),
        ("Additional settings · two explicit checks", settings, "additional-settings"),
    ]
    rules = [
        {"id": "COMB-CONFIG", "task": "combination-configuration", "title": "Controlled combination configuration", "text": "SYNTHETIC CHECKLIST. The complete supplied export must contain base cases SDL and LIVE and exactly C1=1.2 SDL+1.5 LIVE and C2=SDL-LIVE. Factor tolerance is 0.000001. This chosen checklist is not an Australian Standard.", "parameters": {"required_base_cases": ["SDL", "LIVE"], "required_combinations": [{"id": "C1", "terms": [{"caseId": "SDL", "factor": 1.2}, {"caseId": "LIVE", "factor": 1.5}]}, {"id": "C2", "terms": [{"caseId": "SDL", "factor": 1}, {"caseId": "LIVE", "factor": -1}]}], "allow_extra_base_cases": False, "allow_extra_combinations": False, "factor_tolerance": 0.000001}},
        {"id": "HANDOFF", "task": "handoff", "title": "Controlled E1 to S1 transfer manifest", "text": "SYNTHETIC TRANSFER MANIFEST. Compare E1 source transfer.vertical with S1 target transfer.vertical, converting the explicitly supplied force units to kN. Absolute tolerance 0.001 kN and relative tolerance zero. This is an approved test mapping, not proof of native CSI interoperability or structural correctness.", "parameters": {"source_revision": "E1", "target_revision": "S1", "required_source_paths": ["/transfer/vertical"], "required_target_paths": ["/transfer/vertical"], "mappings": [{"id": "vertical-transfer", "source_path": "/transfer/vertical", "target_path": "/transfer/vertical", "source_unit_path": "/units/force", "target_unit_path": "/units/force", "comparison_unit": "kN", "absolute_tolerance": 0.001, "relative_tolerance": 0}]}},
        {"id": "SEISMIC", "task": "seismic-configuration", "title": "Controlled seismic settings checklist", "text": "SYNTHETIC CHECKLIST. Require seismic.period_method supplied-profile and eccentricity in [0.04,0.06] for this fixture only. These values have no claimed code authority; actual seismic criteria must be supplied and approved by the client.", "parameters": {"settings": [{"path": "/seismic/period_method", "operator": "eq", "value": "supplied-profile"}, {"path": "/seismic/eccentricity", "operator": "range", "min": 0.04, "max": 0.06}]}},
        {"id": "MASS-SOURCE", "task": "mass-source", "title": "Controlled mass source checklist", "text": "SYNTHETIC CHECKLIST. Require mass.include_self_weight to be true and mass.source approved-schedule. A missing field is NOT VERIFIED. This is a software configuration example, not engineering validation of a real mass source.", "parameters": {"settings": [{"path": "/mass/include_self_weight", "operator": "eq", "value": True}, {"path": "/mass/source", "operator": "eq", "value": "approved-schedule"}]}},
        {"id": "SETTINGS", "task": "additional-settings", "title": "Two controlled additional settings", "text": "SYNTHETIC CHECKLIST. For this fixture require settings.diaphragm rigid and mesh_size in [0.5,2]. These two extra settings demonstrate the bounded rule extension mechanism; they do not establish acceptable settings for a client model.", "parameters": {"settings": [{"path": "/settings/diaphragm", "operator": "eq", "value": "rigid"}, {"path": "/settings/mesh_size", "operator": "range", "min": 0.5, "max": 2}]}},
    ]
    return cases, rules
