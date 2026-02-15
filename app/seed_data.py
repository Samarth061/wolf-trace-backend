"""Seed data translated from frontend mock-data.ts for testing backend data flow."""
from datetime import datetime, timedelta

from app.graph_state import (
    add_node,
    add_edge,
    add_report,
    clear_all,
    set_case_metadata,
)
from app.models.graph import EdgeType, GraphEdge, GraphNode, NodeType
from app.utils.ids import generate_edge_id

# Frontend status -> backend status mapping (reverse of frontend's mapStatus)
STATUS_MAP = {
    "Investigating": "active",
    "Confirmed": "verified",
    "Debunked": "debunked",
    "All-clear": "resolved",
    "Closed": "closed",
}

# ============================================================================
# Cases (from mockCases in mock-data.ts)
# ============================================================================
MOCK_CASES = [
    {
        "id": "case-001",
        "codename": "The Clocktower Signal",
        "location": "North Campus Bell Tower",
        "status": "Investigating",
        "summary": "Multiple reports of unusual radio frequency emissions near the bell tower during midnight hours. Campus security found no physical anomalies but electromagnetic readings are elevated.",
        "storyText": "On January 28th, three independent witnesses reported strange humming sounds emanating from the North Campus Bell Tower between 11:45 PM and 12:30 AM. Campus security conducted a sweep but found no physical cause. However, a student radio club member detected anomalous RF signals in the 433 MHz band. Subsequent analysis suggests the signals may be encoded data transmissions.",
        "evidenceCount": 10,
    },
    {
        "id": "case-002",
        "codename": "The Vanishing Mural",
        "location": "Arts District - Block 7",
        "status": "Confirmed",
        "summary": "A large mural appeared overnight on the Block 7 wall, then vanished completely within 48 hours. Paint analysis shows non-standard compounds.",
        "storyText": "A striking 20-foot mural depicting a wolf silhouette was discovered on the east wall of Block 7 at 6:15 AM on February 2nd. CCTV footage from the area shows a 4-hour gap in recordings. The mural disappeared by February 4th with no residue. Paint chip analysis reveals photoreactive compounds not commercially available.",
        "evidenceCount": 8,
    },
    {
        "id": "case-003",
        "codename": "The Fog Machine",
        "location": "Engineering Lab B",
        "status": "Investigating",
        "summary": "Unidentified aerosol emissions from a basement vent in Engineering Lab B. Multiple students reported dizziness.",
        "storyText": "Starting February 5th, students in the Engineering Lab B basement reported periodic fog-like emissions from air vent 3B. Building maintenance found no HVAC malfunction. Air quality tests show elevated but non-toxic particulate matter. The emissions occur at roughly 90-minute intervals and last approximately 3 minutes each.",
        "evidenceCount": 9,
    },
    {
        "id": "case-004",
        "codename": "The Phantom Ledger",
        "location": "Library Archives - Sub-Level 2",
        "status": "Debunked",
        "summary": "Reports of a hidden financial ledger found in the library archives turned out to be a student art project for their thesis on institutional transparency.",
        "storyText": "A tip suggested a hidden financial ledger was discovered in Sub-Level 2 of the university library. Investigation revealed the documents were part of a graduate art installation by student M. Chen, exploring themes of institutional secrecy. The department confirmed the project.",
        "evidenceCount": 4,
    },
    {
        "id": "case-005",
        "codename": "The Midnight Whistle",
        "location": "Stadium South Gate",
        "status": "Investigating",
        "summary": "A distinct whistle pattern has been heard near the south gate at exactly midnight for seven consecutive nights. Security cameras show no visible source.",
        "storyText": "Since February 1st, campus security and night-shift workers have reported a melodic whistle pattern near Stadium South Gate at precisely 00:00. The pattern repeats three times, each lasting approximately 12 seconds. Directional microphone analysis places the source underground.",
        "evidenceCount": 6,
    },
    {
        "id": "case-006",
        "codename": "The Copper Wire Trail",
        "location": "Maintenance Tunnel C",
        "status": "Confirmed",
        "summary": "Unauthorized copper wiring discovered running through maintenance tunnels, connecting two buildings. Purpose unknown.",
        "storyText": "During routine maintenance, workers discovered approximately 200 meters of unregistered copper wiring routed through Tunnel C, connecting the Science Building to the Communications Center. The wire appears professionally installed with military-grade insulation.",
        "evidenceCount": 5,
    },
    {
        "id": "case-007",
        "codename": "The Glass Eye",
        "location": "Student Union - Room 404",
        "status": "All-clear",
        "summary": "Suspicious camera-like device found in Room 404 was identified as an old smoke detector model.",
        "storyText": "A student reported finding what appeared to be a hidden camera in Room 404 of the Student Union. Facilities management identified the device as a discontinued Kidde smoke detector model from 2003, left from a previous renovation.",
        "evidenceCount": 3,
    },
    {
        "id": "case-008",
        "codename": "The Echo Chamber",
        "location": "Music Hall Basement",
        "status": "Investigating",
        "summary": "Audio recordings captured in the Music Hall basement contain layered voices not present during the recording session.",
        "storyText": "During a late-night recording session, audio engineer T. Reeves captured anomalous audio layers in the Music Hall basement studio. Spectral analysis reveals human voice patterns at frequencies below the audible range. The building sits above a decommissioned civil defense tunnel.",
        "evidenceCount": 7,
    },
    {
        "id": "case-009",
        "codename": "The Paper Trail",
        "location": "Admin Building - 3rd Floor",
        "status": "Closed",
        "summary": "Missing procurement documents were located in an incorrectly labeled filing cabinet. No foul play suspected.",
        "storyText": "Investigation into missing procurement documents concluded after records were found in a mislabeled cabinet on the 3rd floor. Administrative error confirmed by three independent staff members.",
        "evidenceCount": 2,
    },
    {
        "id": "case-010",
        "codename": "The Blank Frequency",
        "location": "Radio Tower - East Ridge",
        "status": "Investigating",
        "summary": "The campus radio tower is broadcasting on an unregistered frequency during early morning hours. Content appears to be numeric sequences.",
        "storyText": "Campus radio operators discovered an unauthorized broadcast on 107.3 FM between 3:00 and 4:00 AM. The broadcast contains repeated numeric sequences read by a synthesized voice. FCC records show no licensed operation on this frequency in the area.",
        "evidenceCount": 5,
    },
]

# ============================================================================
# Evidence (from mockEvidence in mock-data.ts)
# ============================================================================
MOCK_EVIDENCE = [
    # Case 001 - The Clocktower Signal
    {"id": "ev-001", "caseId": "case-001", "type": "text", "title": "Witness Statement - J. Harper",
     "text_body": "Night security guard J. Harper heard humming at 11:52 PM lasting approximately 8 minutes. No visible source identified. Subject Alpha reference noted.",
     "location": {"building": "Bell Tower", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["J. Harper", "Night Security", "Subject Alpha"], "locations": ["Bell Tower", "North Campus"],
     "key_points": ["Heard humming at 11:52 PM", "Duration approx 8 minutes", "No visible source identified"]},
    {"id": "ev-002", "caseId": "case-001", "type": "text", "title": "Witness Statement - K. Osei",
     "text_body": "Radio Club member K. Osei detected a 433 MHz signal. The signal was pulsed, not continuous. Recorded a 14-second sample for analysis.",
     "location": {"building": "Bell Tower", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["K. Osei", "Radio Club"], "locations": ["Bell Tower", "Physics Lab"],
     "key_points": ["Detected 433 MHz signal", "Signal was pulsed, not continuous", "Recorded 14-second sample"]},
    {"id": "ev-003", "caseId": "case-001", "type": "image", "title": "RF Spectrum Analysis Screenshot",
     "text_body": "RF spectrum analysis shows clear spike at 433.92 MHz. Signal pattern repeats every 90 seconds. Bandwidth suggests data modulation.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Bell Tower perimeter", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["RTL-SDR", "Spectrum Analyzer"], "locations": ["Bell Tower perimeter"],
     "key_points": ["Clear spike at 433.92 MHz", "Signal pattern repeats every 90 seconds", "Bandwidth suggests data modulation"]},
    {"id": "ev-004", "caseId": "case-001", "type": "video", "title": "Security Camera Footage - Tower Base",
     "text_body": "Security camera footage shows unidentified figure approaching Bell Tower at 11:48 PM. Face not visible. Carries metallic object. Departs at 12:15 AM.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Bell Tower entrance", "lat": 0.0, "lng": 0.0}, "authenticity": "suspicious",
     "entities": ["Camera 7B", "Unidentified Figure"], "locations": ["Bell Tower entrance", "North path"],
     "key_points": ["Figure approaches at 11:48 PM", "Face not visible", "Carries metallic object", "Departs at 12:15 AM"]},
    {"id": "ev-005", "caseId": "case-001", "type": "text", "title": "EMF Reading Report",
     "text_body": "Dr. Fielding conducted EMF readings at the Bell Tower. Elevated EMF at roof level. Normal readings below Level 2. Peak readings between 11 PM and 1 AM.",
     "location": {"building": "Bell Tower - Level 3", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Dr. Fielding", "EMF Meter"], "locations": ["Bell Tower - Level 3", "Bell Tower - Roof"],
     "key_points": ["Elevated EMF at roof level", "Normal readings below Level 2", "Peak readings between 11 PM and 1 AM"]},
    {"id": "ev-006", "caseId": "case-001", "type": "image", "title": "Photo of Antenna Mount on Roof",
     "text_body": "Photo shows non-standard antenna mount on Bell Tower roof NE corner. Recently installed based on bolt condition. No work orders match this installation.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Bell Tower roof - NE corner", "lat": 0.0, "lng": 0.0}, "authenticity": "unknown",
     "entities": ["Antenna", "Mounting Bracket"], "locations": ["Bell Tower roof - NE corner"],
     "key_points": ["Non-standard antenna mount", "Recently installed based on bolt condition", "No work orders match this installation"]},
    {"id": "ev-007", "caseId": "case-001", "type": "text", "title": "Maintenance Log Review",
     "text_body": "Facilities Dept maintenance log review: No authorized roof access in past 60 days. Last maintenance was electrical inspection on Dec 15. Roof hatch lock was reported damaged on Jan 20.",
     "location": {"building": "Bell Tower", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Facilities Dept", "Work Order #4471"], "locations": ["Bell Tower"],
     "key_points": ["No authorized roof access in past 60 days", "Last maintenance was electrical inspection on Dec 15", "Roof hatch lock was reported damaged on Jan 20"]},
    {"id": "ev-008", "caseId": "case-001", "type": "video", "title": "Student Phone Video - Strange Light",
     "text_body": "Student phone video shows blinking light on Bell Tower at 12:05 AM. Pattern appears non-random: 4 seconds on, 2 seconds off.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Bell Tower - viewed from quad", "lat": 0.0, "lng": 0.0}, "authenticity": "suspicious",
     "entities": ["Anonymous Student", "LED Indicator"], "locations": ["Bell Tower - viewed from quad"],
     "key_points": ["Blinking light visible on tower at 12:05 AM", "Pattern appears non-random", "Duration 4 seconds on, 2 seconds off"]},
    {"id": "ev-009", "caseId": "case-001", "type": "image", "title": "Decoded Signal Fragment",
     "text_body": "Partial decode of 433 MHz signal contains repeating 16-byte header. Payload appears encrypted.",
     "media_url": "/placeholder-evidence.jpg", "authenticity": "unknown",
     "entities": ["Binary Sequence", "Decryption Attempt"], "locations": [],
     "key_points": ["Partial decode of 433 MHz signal", "Contains repeating 16-byte header", "Payload appears encrypted"]},
    {"id": "ev-010", "caseId": "case-001", "type": "text", "title": "Anonymous Tip - Insider Knowledge",
     "text_body": "Anonymous tip claims tower is used for unauthorized research. Mentions 'Project Theta'. Alleges faculty involvement in CS Department.",
     "location": {"building": "Bell Tower", "lat": 0.0, "lng": 0.0}, "authenticity": "suspicious",
     "entities": ["Anonymous", "Research Project Theta"], "locations": ["Bell Tower", "CS Department"],
     "key_points": ["Claims tower is used for unauthorized research", "Mentions 'Project Theta'", "Alleges faculty involvement"]},
    # Case 002 - The Vanishing Mural
    {"id": "ev-011", "caseId": "case-002", "type": "image", "title": "Mural Photo - Full View",
     "text_body": "20-foot mural with wolf motif photographed at 6:20 AM Feb 2. High detail visible on Block 7 East Wall.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Arts District", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Wolf Silhouette", "Block 7"], "locations": ["Arts District", "Block 7 East Wall"],
     "key_points": ["20-foot mural, wolf motif", "Photographed at 6:20 AM Feb 2", "High detail visible"]},
    {"id": "ev-012", "caseId": "case-002", "type": "video", "title": "CCTV Gap Analysis",
     "text_body": "CCTV analysis shows 4-hour recording gap from 1 AM to 5 AM. No system errors logged. Manual override suspected.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Block 7 perimeter", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Camera 12A", "System Admin"], "locations": ["Block 7 perimeter"],
     "key_points": ["4-hour recording gap: 1 AM to 5 AM", "No system errors logged", "Manual override suspected"]},
    {"id": "ev-013", "caseId": "case-002", "type": "text", "title": "Paint Analysis Report",
     "text_body": "Paint analysis by Dr. Voss in Chemistry Dept reveals photoreactive titanium dioxide compound. Not commercially available. UV-activated degradation possible.",
     "location": {"building": "Chemistry Lab", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Dr. Voss", "Chemistry Dept"], "locations": ["Block 7", "Chemistry Lab"],
     "key_points": ["Photoreactive titanium dioxide compound", "Not commercially available", "UV-activated degradation possible"]},
    {"id": "ev-014", "caseId": "case-002", "type": "image", "title": "Wall After Disappearance",
     "text_body": "Photo of Block 7 East Wall after mural disappeared. No paint residue. No cleaning marks. Surface identical to pre-mural state.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Block 7 East Wall", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Clean Wall"], "locations": ["Block 7 East Wall"],
     "key_points": ["No paint residue", "No cleaning marks", "Surface identical to pre-mural state"]},
    {"id": "ev-015", "caseId": "case-002", "type": "text", "title": "Art Department Inquiry",
     "text_body": "Art Department inquiry by Prof. Nakamura: No student projects match. No faculty permissions granted. Compound is research-grade.",
     "location": {"building": "Arts Building", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Prof. Nakamura", "Art Dept"], "locations": ["Arts Building"],
     "key_points": ["No student projects match", "No faculty permissions granted", "Compound is research-grade"]},
    {"id": "ev-016", "caseId": "case-002", "type": "image", "title": "Close-up - Paint Texture",
     "text_body": "Close-up macro photography of paint texture shows layered application technique. Minimal brush strokes. Spray application suspected.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Block 7 East Wall", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Paint Sample"], "locations": ["Block 7 East Wall"],
     "key_points": ["Layered application technique", "Minimal brush strokes", "Spray application suspected"]},
    {"id": "ev-017", "caseId": "case-002", "type": "text", "title": "Security Guard Report",
     "text_body": "Officer Daniels patrolled area at 12:30 AM, no mural present. Did not return until 5:30 AM. Mural fully present at 5:30.",
     "location": {"building": "Block 7", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Officer Daniels"], "locations": ["Block 7"],
     "key_points": ["Patrolled area at 12:30 AM, no mural", "Did not return until 5:30 AM", "Mural fully present at 5:30"]},
    {"id": "ev-018", "caseId": "case-002", "type": "text", "title": "Anonymous Note Found at Scene",
     "text_body": "Handwritten note found at Block 7 base: 'The Pack watches'. Paper is aged parchment style. Found taped to wall base after mural disappeared.",
     "location": {"building": "Block 7 base", "lat": 0.0, "lng": 0.0}, "authenticity": "suspicious",
     "entities": ["The Pack"], "locations": ["Block 7 base"],
     "key_points": ["Handwritten note: 'The Pack watches'", "Found taped to wall base after mural disappeared", "Paper is aged parchment style"]},
    # Case 003 - The Fog Machine
    {"id": "ev-019", "caseId": "case-003", "type": "text", "title": "Student Health Reports (3)",
     "text_body": "Three students reported dizziness after exposure to emissions in Engineering Lab B basement. Symptoms lasted 15-30 minutes with no long-term effects.",
     "location": {"building": "Engineering Lab B", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Health Center", "Students A, B, C"], "locations": ["Engineering Lab B", "Health Center"],
     "key_points": ["Three students reported dizziness", "Symptoms lasted 15-30 minutes", "No long-term effects"]},
    {"id": "ev-020", "caseId": "case-003", "type": "video", "title": "Vent 3B Emission Footage",
     "text_body": "Video footage confirms visible fog from vent 3B. 90-minute emission cycle confirmed. Each emission lasts approximately 3 minutes.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Engineering Lab B Basement", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Vent 3B", "Aerosol Emission"], "locations": ["Engineering Lab B Basement"],
     "key_points": ["Visible fog from vent", "90-minute emission cycle confirmed", "Lasts approximately 3 minutes"]},
    {"id": "ev-021", "caseId": "case-003", "type": "text", "title": "Air Quality Test Results",
     "text_body": "Air quality tests show elevated PM2.5 during emissions. Non-toxic particulate. Glycol-based compound detected.",
     "location": {"building": "Engineering Lab B Basement", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Environmental Safety", "PM2.5"], "locations": ["Engineering Lab B Basement"],
     "key_points": ["Elevated PM2.5 during emissions", "Non-toxic particulate", "Glycol-based compound detected"]},
    {"id": "ev-022", "caseId": "case-003", "type": "text", "title": "HVAC System Inspection",
     "text_body": "HVAC inspection by facilities team: No malfunction found. Ductwork clear. Source not in main HVAC system.",
     "location": {"building": "Engineering Lab B", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Facilities Team", "HVAC Unit 3"], "locations": ["Engineering Lab B"],
     "key_points": ["No HVAC malfunction found", "Ductwork clear", "Source not in main HVAC system"]},
    {"id": "ev-023", "caseId": "case-003", "type": "image", "title": "Vent Interior Photo",
     "text_body": "Photo of vent 3B interior shows foreign tubing connected to unknown reservoir. Installation appears deliberate.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Vent 3B Interior", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Residue", "Tubing"], "locations": ["Vent 3B Interior"],
     "key_points": ["Foreign tubing inside vent", "Connected to unknown reservoir", "Installation appears deliberate"]},
    {"id": "ev-024", "caseId": "case-003", "type": "image", "title": "Reservoir Device Photo",
     "text_body": "Photo of battery-powered timer circuit with fluid reservoir. Holds approximately 2 liters of glycol solution. Commercial fog machine components modified.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Vent 3B Plenum Space", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Timer Circuit", "Fluid Reservoir"], "locations": ["Vent 3B Plenum Space"],
     "key_points": ["Battery-powered timer circuit", "Holds approximately 2 liters of glycol solution", "Commercial fog machine components modified"]},
    {"id": "ev-025", "caseId": "case-003", "type": "text", "title": "Purchase Records Search",
     "text_body": "Purchase records search: Components available from multiple retailers. No campus purchase orders match. Estimated cost under $50.",
     "authenticity": "unknown",
     "entities": ["Online Retailer", "Fog Machine Parts"], "locations": [],
     "key_points": ["Components available from multiple retailers", "No campus purchase orders match", "Estimated cost under $50"]},
    {"id": "ev-026", "caseId": "case-003", "type": "text", "title": "Building Access Log",
     "text_body": "Building access logs show 7 after-hours access events in past 2 weeks. 3 from unregistered card. Card reader logs show 2 AM entries.",
     "location": {"building": "Engineering Lab B", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Card Reader 3B", "After-hours Access"], "locations": ["Engineering Lab B"],
     "key_points": ["7 after-hours access events in past 2 weeks", "3 from unregistered card", "Card reader logs show 2 AM entries"]},
    {"id": "ev-027", "caseId": "case-003", "type": "video", "title": "Hallway Camera - Suspicious Entry",
     "text_body": "Hallway camera shows person in hoodie entering at 2:14 AM carrying heavy backpack. Exits at 2:47 AM without backpack.",
     "media_url": "/placeholder-evidence.jpg", "location": {"building": "Engineering Lab B - Hall 3", "lat": 0.0, "lng": 0.0}, "authenticity": "verified",
     "entities": ["Hooded Figure", "Backpack"], "locations": ["Engineering Lab B - Hall 3"],
     "key_points": ["Person in hoodie enters at 2:14 AM", "Carrying heavy backpack", "Exits at 2:47 AM without backpack"]},
]

# ============================================================================
# Evidence Connections (from mockEvidenceConnections in mock-data.ts)
# ============================================================================
MOCK_EVIDENCE_CONNECTIONS = [
    # Case 001 connections
    {"fromId": "ev-001", "toId": "ev-002", "relation": "supports", "caseId": "case-001"},
    {"fromId": "ev-002", "toId": "ev-003", "relation": "supports", "caseId": "case-001"},
    {"fromId": "ev-003", "toId": "ev-005", "relation": "supports", "caseId": "case-001"},
    {"fromId": "ev-004", "toId": "ev-001", "relation": "related", "caseId": "case-001"},
    {"fromId": "ev-006", "toId": "ev-007", "relation": "supports", "caseId": "case-001"},
    {"fromId": "ev-008", "toId": "ev-006", "relation": "related", "caseId": "case-001"},
    {"fromId": "ev-009", "toId": "ev-002", "relation": "supports", "caseId": "case-001"},
    {"fromId": "ev-010", "toId": "ev-006", "relation": "related", "caseId": "case-001"},
    {"fromId": "ev-004", "toId": "ev-008", "relation": "contradicts", "caseId": "case-001"},
    # Case 002 connections
    {"fromId": "ev-011", "toId": "ev-014", "relation": "contradicts", "caseId": "case-002"},
    {"fromId": "ev-012", "toId": "ev-017", "relation": "supports", "caseId": "case-002"},
    {"fromId": "ev-013", "toId": "ev-015", "relation": "supports", "caseId": "case-002"},
    {"fromId": "ev-016", "toId": "ev-013", "relation": "related", "caseId": "case-002"},
    {"fromId": "ev-018", "toId": "ev-011", "relation": "related", "caseId": "case-002"},
    # Case 003 connections
    {"fromId": "ev-019", "toId": "ev-020", "relation": "supports", "caseId": "case-003"},
    {"fromId": "ev-020", "toId": "ev-021", "relation": "supports", "caseId": "case-003"},
    {"fromId": "ev-022", "toId": "ev-023", "relation": "supports", "caseId": "case-003"},
    {"fromId": "ev-023", "toId": "ev-024", "relation": "supports", "caseId": "case-003"},
    {"fromId": "ev-026", "toId": "ev-027", "relation": "supports", "caseId": "case-003"},
    {"fromId": "ev-024", "toId": "ev-025", "relation": "related", "caseId": "case-003"},
]

# ============================================================================
# Tips (from mockTips in mock-data.ts)
# ============================================================================
MOCK_TIPS = [
    {
        "id": "tip-001", "type": "text", "category": "Suspicious",
        "location": "West Parking Garage",
        "content": "Saw someone carrying large equipment boxes into the basement access of the west garage at 3 AM last Tuesday.",
        "anonymous": True,
    },
    {
        "id": "tip-002", "type": "image", "category": "Rumor",
        "location": "Dining Hall",
        "content": "Found this weird symbol scratched into a table in the back corner of the dining hall.",
        "anonymous": False, "name": "Alex Rivera", "email": "a.rivera@university.edu",
    },
    {
        "id": "tip-003", "type": "video", "category": "Safety",
        "location": "Science Building Roof",
        "content": "Drone footage showing an open access panel on the science building roof that shouldnt be there.",
        "anonymous": True,
    },
    {
        "id": "tip-004", "type": "text", "category": "Scam",
        "location": "Student Union",
        "content": "Someone is posting fake QR codes on bulletin boards that redirect to a phishing site mimicking the university portal.",
        "anonymous": False, "name": "Jordan Kim",
    },
]


# ============================================================================
# Seed function
# ============================================================================
def seed_all() -> dict:
    """Populate in-memory graph state with mock data. Idempotent (clears first)."""
    clear_all()
    now = datetime.utcnow()

    # 1. Set case metadata (for label, status, location, summary, story display)
    for case in MOCK_CASES:
        set_case_metadata(case["id"], {
            "label": case["codename"],
            "status": STATUS_MAP.get(case["status"], "active"),
            "location": case["location"],
            "summary": case["summary"],
            "story": case["storyText"],
            "updated_at": (now - timedelta(minutes=15)).isoformat(),
        })

    # 2. Add evidence as GraphNode objects
    for ev in MOCK_EVIDENCE:
        case_id = ev["caseId"]
        node_data = {
            "text_body": ev.get("text_body", ""),
            "media_url": ev.get("media_url", ""),
            "timestamp": (now - timedelta(hours=3)).isoformat(),
            "reviewed": ev.get("authenticity") == "verified",
            "location": ev.get("location"),
            "claims": [{"text": kp} for kp in ev.get("key_points", [])],
            "entities": ev.get("entities", []),
            "extracted_locations": ev.get("locations", []),
            "authenticity": ev.get("authenticity", "unknown"),
            "title": ev.get("title", ""),
        }
        node = GraphNode(
            id=ev["id"],
            node_type=NodeType.REPORT,
            case_id=case_id,
            data=node_data,
            created_at=now - timedelta(hours=2),
        )
        add_node(node)

        # Also add as a report entry so get_all_cases/get_all_reports finds it
        report_data = {
            "case_id": case_id,
            "report_id": ev["id"],
            "text_body": ev.get("text_body", ""),
            "location": ev.get("location"),
            "timestamp": (now - timedelta(hours=3)).isoformat(),
            "anonymous": True,
            "status": "triaged",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        }
        add_report(case_id, ev["id"], report_data, report_node_id=ev["id"])

    # 2b. For cases with no evidence in MOCK_EVIDENCE, create a placeholder report node
    cases_with_evidence = {ev["caseId"] for ev in MOCK_EVIDENCE}
    for case in MOCK_CASES:
        if case["id"] not in cases_with_evidence:
            placeholder_id = f"rpt-{case['id']}"
            node_data = {
                "text_body": case["summary"],
                "media_url": "",
                "timestamp": (now - timedelta(hours=3)).isoformat(),
                "reviewed": False,
                "location": {"building": case["location"]},
                "claims": [],
                "title": case["codename"],
            }
            node = GraphNode(
                id=placeholder_id,
                node_type=NodeType.REPORT,
                case_id=case["id"],
                data=node_data,
                created_at=now - timedelta(hours=2),
            )
            add_node(node)
            report_data = {
                "case_id": case["id"],
                "report_id": placeholder_id,
                "text_body": case["summary"],
                "location": {"building": case["location"]},
                "timestamp": (now - timedelta(hours=3)).isoformat(),
                "anonymous": True,
                "status": "triaged",
                "created_at": (now - timedelta(hours=2)).isoformat(),
            }
            add_report(case["id"], placeholder_id, report_data, report_node_id=placeholder_id)

    # 3. Add evidence connections as GraphEdge objects
    relation_map = {
        "supports": EdgeType.SIMILAR_TO,
        "contradicts": EdgeType.DEBUNKED_BY,
        "related": EdgeType.SIMILAR_TO,
    }
    for conn in MOCK_EVIDENCE_CONNECTIONS:
        edge = GraphEdge(
            id=generate_edge_id(),
            edge_type=relation_map.get(conn["relation"], EdgeType.SIMILAR_TO),
            source_id=conn["fromId"],
            target_id=conn["toId"],
            case_id=conn["caseId"],
            data={"relation": conn["relation"]},
            created_at=now - timedelta(hours=1),
        )
        add_edge(edge)

    # 4. Add tips as report entries
    for tip in MOCK_TIPS:
        tip_case_id = f"TIP-CASE-{tip['id']}"
        set_case_metadata(tip_case_id, {
            "label": f"Tip: {tip['location']}",
            "status": "pending",
            "location": tip["location"],
            "summary": tip["content"][:200],
        })
        report_data = {
            "case_id": tip_case_id,
            "report_id": tip["id"],
            "text_body": tip["content"],
            "location": {"building": tip["location"]} if tip.get("location") else None,
            "timestamp": (now - timedelta(hours=5)).isoformat(),
            "anonymous": tip.get("anonymous", True),
            "contact": tip.get("email", ""),
            "status": "pending",
            "created_at": (now - timedelta(hours=5)).isoformat(),
        }
        add_report(tip_case_id, tip["id"], report_data)

        # Also add as a node
        tip_node = GraphNode(
            id=tip["id"],
            node_type=NodeType.REPORT,
            case_id=tip_case_id,
            data={
                "text_body": tip["content"],
                "location": {"building": tip["location"]} if tip.get("location") else None,
                "timestamp": (now - timedelta(hours=5)).isoformat(),
                "reviewed": False,
            },
            created_at=now - timedelta(hours=5),
        )
        add_node(tip_node)

    return {
        "cases": len(MOCK_CASES),
        "evidence": len(MOCK_EVIDENCE),
        "connections": len(MOCK_EVIDENCE_CONNECTIONS),
        "tips": len(MOCK_TIPS),
    }
