
"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

ONTOLOGY MODULE
This module defines the Schema class, which provides the base semantics and ontological principles in the BTWIN toolkit.

© Angelo Massafra, 2025
"""

class Schema():

    @staticmethod
    def RelationshipNames() -> dict:
        """
        Returns ontology-aware relationship patterns used by BTWIN.

        Returns:
            dict: {
                "<predicate CURIE>": {
                    "IRI": "<predicate IRI>",
                    "pairs": [
                        {
                            "subject": {"label": "<CURIE>", "IRI": "<IRI>"},
                            "object":  {"label": "<CURIE>", "IRI": "<IRI>"}
                        },
                        ...
                    ]
                },
                ...
            }
        """
        # --- Namespaces ---------------
        nsMap = {
            "brick": "https://brickschema.org/schema/Brick#",
            "bot":   "https://w3id.org/bot#",
            "ifc":   "https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#",
            "eko":   "http://energy.linkeddata.es/em-kpi/ontology#",
            "kpi":   "http://bimerr.iot.linkeddata.es/def/key-performance-indicator#",
            "btwin": "btwin#",          # placeholder
            "top":   "top#",            # placeholder
        }

        def IRI(ns: str, local: str) -> str:
            """Build full IRI from namespace and local name."""
            base = nsMap.get(ns)
            if not base:
                raise ValueError(f"Unknown namespace prefix: {ns}")
            return f"{base}{local}"

        def term(label: str) -> dict:
            """Return {'label', 'IRI'} from 'prefix:Local'."""
            if ":" not in label:
                raise ValueError(f"Label must be CURIE-like 'prefix:Local': {label}")
            prefix, local = label.split(":", 1)
            return {"label": label, "IRI": IRI(prefix, local)}

        # --- Brick location classes for OBJECT side of brick:hasLocation -------
        brickLocationLabels = [
            "brick:Portfolio", "brick:Region", "bot:Site",
            "bot:Building", "bot:Storey", "bot:Space",
            "brick:Zone", "brick:Energy_Zone", "brick:Fire_Zone",
        ]
        brickLocation = {lbl: term(lbl) for lbl in brickLocationLabels}

        # --- Convenience BOT classes -------------------------------------------
        botClasses = {lbl: term(lbl) for lbl in ["bot:Site", "bot:Building", "bot:Storey", "bot:Space", "bot:Zone", "bot:Interface", "bot:Element"]}

        # --- Base relationships map --------------------------------------------
        relationshipsMap = {
            # 1) Spatial/location relations (Brick)
            "brick:hasLocation": {
                "IRI": IRI("brick", "hasLocation"),
                "pairs": [
                    {"subject": botClasses["bot:Space"],    "object": brickLocation["bot:Storey"]},
                    {"subject": botClasses["bot:Space"],    "object": brickLocation["brick:Zone"]},
                    {"subject": botClasses["bot:Space"],    "object": brickLocation["brick:Energy_Zone"]},
                    {"subject": botClasses["bot:Space"],    "object": brickLocation["brick:Fire_Zone"]},
                    {"subject": botClasses["bot:Storey"],   "object": brickLocation["bot:Building"]},
                    {"subject": botClasses["bot:Building"], "object": brickLocation["bot:Site"]},
                    {"subject": botClasses["bot:Site"],     "object": brickLocation["brick:Region"]},
                    {"subject": brickLocation["brick:Zone"],        "object": brickLocation["bot:Building"]},
                    {"subject": brickLocation["brick:Energy_Zone"], "object": brickLocation["bot:Building"]},
                    {"subject": brickLocation["brick:Fire_Zone"],   "object": brickLocation["bot:Building"]},
                    {"subject": brickLocation["brick:Region"],      "object": brickLocation["brick:Portfolio"]},
                    # Elements/equipment located in spaces
                    {"subject": term("brick:Equipment"), "object": brickLocation["bot:Space"]},
                    {"subject": term("ifc:Sensor"),      "object": brickLocation["bot:Space"]},  # IFC mapped to Brick space
                ],
            },

            # 2) Systems feeding relations (Brick)
            "brick:isFedBy": {
                "IRI": IRI("brick", "isFedBy"),
                "pairs": [
                    {"subject": botClasses["bot:Building"], "object": term("brick:System")},
                    {"subject": term("brick:Energy_Zone"),  "object": term("brick:System")},
                ],
            },

            # 3) Interfaces (BOT) — replace non-standard 'bot:hasInterface'
            "bot:interfaceOf": {
                "IRI": IRI("bot", "interfaceOf"),
                "pairs": [
                    {"subject": botClasses["bot:Interface"], "object": botClasses["bot:Space"]},
                    {"subject": botClasses["bot:Interface"], "object": botClasses["bot:Element"]},
                    {"subject": botClasses["bot:Interface"], "object": term("top:Face")},
                    {"subject": botClasses["bot:Interface"], "object": term("top:Aperture")},
                    {"subject": term("top:Face"), "object": botClasses["bot:Space"]},
                    {"subject": term("top:Aperture"), "object": botClasses["bot:Space"]},
                    {"subject": botClasses["bot:Space"], "object": term("top:Aperture")},
                ],
            },

            # 4) BTWIN-specific relations
            "btwin:isAdjacentTo": {
                "IRI": IRI("btwin", "isAdjacentTo"),
                "pairs": [
                    {"subject": botClasses["bot:Space"], "object": botClasses["bot:Space"]},
                ],
            },
            "btwin:hasPassageTo": {
                "IRI": IRI("btwin", "hasPassageTo"),
                "pairs": [
                    {"subject": botClasses["bot:Space"], "object": botClasses["bot:Space"]},
                ],
            },
            "btwin:isDocumentOf": {
                "IRI": IRI("btwin", "isDocumentOf"),
                "pairs": [
                    {"subject": term("btwin:Document"), "object": botClasses["bot:Building"]},
                ],
            },
            "btwin:hasDocument": {
                "IRI": IRI("btwin", "hasDocument"),
                "pairs": [
                    {"subject": botClasses["bot:Building"], "object": term("btwin:Document")},
                ],
            },

            # 5) KPI
            "kpi:relatedScenario": {
                "IRI": IRI("kpi", "relatedScenario"),
                "pairs": [
                    {"subject": term("btwin:KPISet"), "object": term("kpi:Scenario")},
                    {"subject": term("btwin:Document"), "object": term("kpi:Scenario")}
                ]
            }

        }

        # --- Expand rules for "all spatial element types" ----------------------
        spatialElementTypes = list(Schema.Types().keys())  # expects CURIE labels
        # 4.a IFC property sets
        relationshipsMap["ifc:HasPropertySets"] = {
            "IRI": IRI("ifc", "HasPropertySets"),  # placeholder: verify your IFC predicate IRI
            "pairs": [{"subject": term(lbl), "object": term("ifc:IfcPropertySet")} for lbl in spatialElementTypes],
        }
        # 4.b EKO KPI association
        relationshipsMap["eko:hasAssociatedObject"] = {
            "IRI": IRI("eko", "hasAssociatedObject"),
            "pairs":
                # from each spatial element type to eko:KPI
                [{"subject": term(lbl), "object": term("eko:KPI")} for lbl in spatialElementTypes]
        }

        # 4.c BTWIN document attachment
        relationshipsMap["btwin:hasDocument"] = {
            "IRI": IRI("btwin", "hasDocument"),
            "pairs": [{"subject": term(lbl), "object": term("btwin:Document")} for lbl in spatialElementTypes],
        }


        # --- Basic defensive checks (optional but handy) -----------------------
        # Ensure each pair has both subject/object IRIs
        for relLabel, relDef in relationshipsMap.items():
            if "IRI" not in relDef or "pairs" not in relDef:
                raise ValueError(f"Relationship '{relLabel}' is missing 'IRI' or 'pairs'.")
            for p in relDef["pairs"]:
                if "subject" not in p or "object" not in p:
                    raise ValueError(f"Relationship '{relLabel}' has a malformed pair: {p}")
                if "IRI" not in p["subject"] or "IRI" not in p["object"]:
                    raise ValueError(f"Missing IRI in subject/object for '{relLabel}': {p}")

        return relationshipsMap

    @staticmethod
    def Types() -> dict:
        """
        Return canonical types used by BTWIN.

        Returns:
            dict: A mapping where each key is a compact label (e.g., "bot:Site",
                  "brick:Zone") and each value is a dictionary with:
                  - "IRI": the canonical IRI of the class
                  - "description": a short human-readable description
        """
        return {
            # --- Brick (https://brickschema.org/schema/Brick#) ---
            "brick:Portfolio": {
                "IRI": "https://brickschema.org/schema/Brick#Portfolio",
                "description": "A collection that groups one or more Sites (e.g., an owner's portfolio)."
            },
            "brick:Region": {
                "IRI": "https://brickschema.org/schema/Brick#Region",
                "description": "A location representing a geographic/administrative region used for grouping."
            },
            "brick:Zone": {
                "IRI": "https://brickschema.org/schema/Brick#Zone",
                "description": "A logical grouping of spaces defined by a subsystem (e.g., HVAC, lighting, fire)."
            },
            "brick:Energy_Zone": {
                "IRI": "https://brickschema.org/schema/Brick#Energy_Zone",
                "description": "A Zone used for energy metering/management boundaries; subclass of brick:Zone."
            },
            "brick:Fire_Zone": {
                "IRI": "https://brickschema.org/schema/Brick#Fire_Zone",
                "description": "A subsection of the building that can be isolated by fire barriers/doors."
            },

            # --- BOT (https://w3id.org/bot#) ---
            "bot:Site": {
                "IRI": "https://w3id.org/bot#Site",
                "description": "Top-level spatial container (e.g., campus/plot) that may contain Buildings."
            },
            "bot:Building": {
                "IRI": "https://w3id.org/bot#Building",
                "description": "A building within a Site; contains one or more Storeys and Spaces."
            },
            "bot:Storey": {
                "IRI": "https://w3id.org/bot#Storey",
                "description": "A level of a building (above/below ground) that contains Spaces."
            },
            "bot:Space": {
                "IRI": "https://w3id.org/bot#Space",
                "description": "A bounded part of the built environment (e.g., room, corridor)."
            },

            # --- IFC (https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#) ---
            "ifc:IfcPropertySet": {
                "IRI": "https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#IfcPropertySet",
                "description": "The IfcPropertySet is a container that holds properties within a property tree. These properties are interpreted according to their name attribute."
            },

            # --- BTWIN (custom types)
            "btwin:KPISet":{
                "IRI" : "btwin#KPISet",
                "description": "A group of key performance indicators."
            },
            "btwin:Document":{
                "IRI" : "btwin#Document",
                "description": "A document, model or database."
            },

            # --- KPI Ontologu
            "kpi:Scenario":{
                "IRI": "http://bimerr.iot.linkeddata.es/def/key-performance-indicator#Scenario",
                "description": "Hypothetical simulated situation of a state or building (e.g. The simluation of a building renovation work.)"
            },

            # --- Brick Equipment & Point (used in RelationshipNames pairs) ---
            "brick:Equipment": {
                "IRI": "https://brickschema.org/schema/Brick#Equipment",
                "description": "A device or piece of equipment in a building (generic superclass)."
            },
            "brick:Point": {
                "IRI": "https://brickschema.org/schema/Brick#Point",
                "description": "A generic Brick point (sensor, setpoint, command, status, alarm)."
            },
            "brick:System": {
                "IRI": "https://brickschema.org/schema/Brick#System",
                "description": "A Brick system that groups equipment serving a common function."
            },
            "ifc:Sensor": {
                "IRI": "https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#Sensor",
                "description": "An IFC sensor device mapped into the Brick location model."
            },

            # --- BOT additional ---
            "bot:Interface": {
                "IRI": "https://w3id.org/bot#Interface",
                "description": "An interface between two building zones or elements."
            },
            "bot:Element": {
                "IRI": "https://w3id.org/bot#Element",
                "description": "A building element (wall, slab, window, etc.)."
            },

            # Topologic
            "top:Face": {
                "IRI": "top#Face",
                "description": "A topologic face representing a building surface."
            },
            "top:Aperture": {
                "IRI": "top#Aperture",
                "description": "A topologic aperture (window, door opening)."
            },
        }
