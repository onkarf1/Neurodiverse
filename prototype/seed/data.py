"""A reproducible school workspace. Every activity and observation is fictional."""

from datetime import datetime, timedelta, timezone


def build_seed():
    # Fixed for reproducibility, but never later than the reset itself so new work sorts first.
    anchor = min(datetime(2026, 11, 5, 16, 0, tzinfo=timezone.utc), datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(hours=1))

    def stamp(days=0, minutes=0):
        return (anchor + timedelta(days=days, minutes=minutes)).isoformat()

    users = [
        {"id": "u1", "name": "Maya Brooks", "email": "teacher@strivetrack.demo", "role": "teacher", "initials": "MB", "color": "lavender"},
        {"id": "u2", "name": "Casey Nguyen", "email": "casey@strivetrack.demo", "role": "teacher", "initials": "CN", "color": "mint"},
        {"id": "u3", "name": "Elena Rivera", "email": "admin@strivetrack.demo", "role": "admin", "initials": "ER", "color": "peach"},
    ]
    # Title, category, setting, three task cards. Cards do not imply a mastery score.
    contexts = [
        ("Plan a café opening routine", "Workplace", "the café counter", ["Place clean cups by the machine", "Wipe the counter", "Gather the cleaning supplies"]),
        ("Prepare a library return cart", "Workplace", "the library return desk", ["Group books by shelf label", "Collect the returned books", "Load the cart safely"]),
        ("Organize a grocery shelf", "Workplace", "the grocery aisle", ["Put older stock at the front", "Check the shelf labels", "Bring the matching stock to the aisle"]),
        ("Make a breakfast plan", "Daily living", "the practice kitchen", ["Serve the toast on a plate", "Gather bread and a plate", "Toast the bread"]),
        ("Set up a reception desk", "Workplace", "the reception area", ["Place visitor forms on the desk", "Clear yesterday’s materials", "Check which forms are needed today"]),
        ("Plan a bus stop departure", "Community", "the neighborhood bus stop", ["Walk to the stop", "Check the route and departure time", "Pack the travel card"]),
        ("Prepare a laundry load", "Daily living", "the laundry room", ["Choose the wash cycle", "Sort clothing by care label", "Place the suitable clothes in the machine"]),
        ("Restock an art supply trolley", "Workplace", "the art room", ["Place supplies in labeled bins", "Check which supplies are low", "Collect the replacement materials"]),
        ("Plan a shopping visit", "Community", "the neighborhood market", ["Find the items on the list", "Write the shopping list", "Check what is already in the cupboard"]),
        ("Assemble a welcome pack", "Workplace", "the visitor center", ["Check the finished pack", "Gather the brochure and map", "Place the materials in a folder"]),
        ("Open the garden workstation", "Workplace", "the school garden", ["Arrange tools within reach", "Check the work area is clear", "Collect gloves and hand tools"]),
        ("Prepare a simple lunch", "Daily living", "the practice kitchen", ["Pack the finished lunch", "Choose ingredients from the picture menu", "Assemble the sandwich"]),
        ("Sort community donation bags", "Community", "the donation center", ["Move sorted items to collection bins", "Read the donation categories", "Open one bag at a time"]),
        ("Plan a print-room job", "Workplace", "the print room", ["Collect the printed pages", "Check the requested page count", "Load the correct paper"]),
        ("Pack a workday bag", "Daily living", "the classroom practice area", ["Place selected items in the bag", "Check tomorrow’s schedule", "Gather the items needed for each activity"]),
        ("Set up a volunteer table", "Community", "the community hall", ["Arrange the sign-in materials", "Check the table location", "Bring the table supplies"]),
        ("Prepare a pet-care station", "Workplace", "the animal-care classroom", ["Put the prepared bowls at the station", "Check the care instruction card", "Measure the listed food and water"]),
        ("Plan a bedroom reset", "Daily living", "the independent-living room", ["Return supplies to their storage place", "Choose one area to tidy", "Put the items from that area away"]),
        ("Organize a meeting room", "Workplace", "the meeting room", ["Set out the requested materials", "Read the room booking note", "Arrange the chairs for the group"]),
        ("Plan a pharmacy collection", "Community", "the community practice desk", ["Join the collection queue", "Check opening hours", "Pack the fictional collection slip"]),
        ("Prepare a bakery delivery", "Workplace", "the bakery packing area", ["Place the delivery label on the box", "Match the order to the packing list", "Pack the listed items"]),
        ("Choose a morning routine", "Daily living", "the life-skills classroom", ["Leave for the planned activity", "Check the day’s start time", "Gather clothing and breakfast items"]),
        ("Set up a recycling station", "Community", "the community center", ["Place the category signs on the bins", "Identify the collection categories", "Move empty bins into the marked spaces"]),
        ("Prepare a hotel supply cart", "Workplace", "the hospitality classroom", ["Place supplies in the cart sections", "Read the room supply checklist", "Gather the matching supplies"]),
        ("Plan a grocery unpacking task", "Daily living", "the practice kitchen", ["Put cupboard items on their shelves", "Identify items that need cold storage", "Put chilled items in the refrigerator"]),
        ("Organize a makerspace bench", "Workplace", "the makerspace", ["Set the task materials on the bench", "Read the project materials card", "Clear a safe workspace"]),
        ("Prepare for a recreation visit", "Community", "the recreation center", ["Go to the activity room", "Check the booking time and location", "Gather the items listed for the activity"]),
        ("Plan a stockroom handover", "Workplace", "the stockroom", ["Leave the handover note in the tray", "Check the unfinished-task board", "Write down the materials still needed"]),
        ("Organize a shared kitchen shelf", "Daily living", "the shared kitchen", ["Return containers to the shelf", "Check the shelf space and labels", "Group containers by storage type"]),
        ("Prepare a community event kit", "Community", "the community hall store", ["Check the packed kit against the list", "Read the event equipment list", "Collect the listed items in the kit bag"]),
    ]
    support_sets = [
        ["Visual step cards", "Extra processing time"],
        ["Written instructions in plain language", "Read-aloud support on request"],
        ["Visual step cards", "A quiet workspace", "Extra processing time"],
        ["Large-print materials", "One instruction at a time"],
        ["A visual timer", "A short movement break when requested"],
    ]
    approved = {1, 2, 4, 7, 10, 13, 16, 19, 22, 25}
    blocked = {3, 9, 15, 21}
    rejected = {6, 12, 18, 24}
    unsure = {5, 11, 23}
    seed = {name: [] for name in ["goals", "activities", "revisions", "observations", "checks", "audit"]}
    seed["users"] = users

    for i, (title, category, setting, cards) in enumerate(contexts):
        n = i + 1
        gid, aid, rid = "g%02d" % n, "a%02d" % n, "r%02d" % n
        actor = users[i % 2]
        accommodations = list(support_sets[i % len(support_sets)])
        archived = i >= 27
        due_date = (anchor + timedelta(days=(i % 15) - 5)).date().isoformat()
        goal = {
            "id": gid, "title": title,
            "skill_description": "Given three task cards for %s, independently choose and explain a workable order before beginning the task." % setting,
            "success_criteria": "During three practice opportunities, create a three-step plan and explain one reason for the chosen order, using the approved supports.",
            "accommodations": accommodations, "category": category,
            "status": "archived" if archived else "active", "due_date": due_date,
            "created_by": actor["id"], "created_at": stamp(-24 + i // 2), "updated_at": stamp(-i // 4, -i * 7),
        }
        if i == 26:
            goal["success_criteria"] += " Offer a chance to pause before selecting the first card. Accept a spoken explanation, a written explanation, or pointing to an explanation card. Record which support was chosen without interpreting the choice as a change to the approved goal."
        seed["goals"].append(goal)

        if i in unsure:
            content = "Prepare %s before the next session. Complete the task when you are ready." % setting
        elif i in approved:
            content = "Your task is to prepare %s. Choose which card comes first, next, and last. Explain why your plan works.\n\nStep cards:\n%s\n\nApproved supports:\n%s" % (setting, "\n".join("- " + card for card in cards), "\n".join("- " + item for item in accommodations))
        else:
            content = "Follow these steps in order:\n1. %s\n2. %s\n3. %s\n\nCheck each step after you finish.\n\nApproved supports:\n%s" % (cards[2], cards[1], cards[0], "\n".join("- " + item for item in accommodations))
        activity_status = "archived" if archived else "approved" if i in approved else "needs_review" if i % 3 == 0 or i == 0 else "draft"
        activity = {
            "id": aid, "goal_id": gid, "title": title.replace("Plan a", "Practice a", 1) if title.startswith("Plan a") else title + " · activity",
            "content": content, "category": category, "status": activity_status, "due_date": due_date,
            "color": ["peach", "mint", "lavender", "lemon"][i % 4], "created_by": actor["id"],
            "created_at": stamp(-15 + i // 3), "updated_at": stamp(-i // 4, -i * 7),
        }
        seed["activities"].append(activity)

        kept_supports = accommodations[:-1] if i in blocked else list(accommodations)
        revision_content = "Your task is to prepare %s. You decide the order.\n\nChoose a first, next, and last step. Tell your teacher why this order works, then try your plan. You may change your plan if you notice something that would help.\n\nStep cards:\n%s\n\nApproved supports:\n%s" % (setting, "\n".join("- " + card for card in cards), "\n".join("- " + item for item in kept_supports))
        revision_status = "approved" if i in approved else "blocked" if i in blocked else "rejected" if i in rejected else "draft"
        revision = {
            "id": rid, "activity_id": aid, "goal_id": gid, "content": revision_content,
            "status": revision_status, "version": 1,
            "blocked_reason": ("Missing approved accommodation: " + accommodations[-1]) if i in blocked else None,
            "accommodations": kept_supports, "created_by": actor["id"],
            "created_at": stamp(-7 + i // 5, -i * 4), "updated_at": stamp(-i // 5, -i * 5),
        }
        seed["revisions"].append(revision)

        result = "unsure" if i in unsure else "aligned" if i in approved else "mismatch"
        finding = [] if result != "mismatch" else [{
            "type": "bypasses_skill", "explanation": "The worksheet supplies the order. The approved goal asks the learner to choose a plan, so following this sequence does the planning for them.",
            "evidence": "Follow these steps in order:", "confidence": 0.96,
        }]
        summary = {
            "aligned": "This activity leaves the planning decision with the learner and retains the listed supports.",
            "mismatch": "The activity gives away the sequence instead of asking the learner to plan it.",
            "unsure": "The instructions do not show enough of the activity to check who chooses the task order. Add the task cards and learner directions.",
        }[result]
        seed["checks"].append({"id": "c%02d" % n, "activity_id": aid, "goal_id": gid, "result": result, "summary": summary, "findings": finding, "created_at": stamp(-i // 5, -i * 6), "updated_at": stamp(-i // 5, -i * 6)})

        if i < 28:
            notes = [
                "Used the visual cards to arrange a plan and explained the first choice. Asked for extra thinking time before starting. Record the support used; this note does not determine goal mastery.",
                "Changed the order after noticing a missing material. I asked an open question and recorded the explanation without supplying the next step.",
                "Requested the directions read aloud, then selected a starting card. Next session, leave room for a longer pause before offering a prompt.",
                "The first practice attempt stopped at the materials check. We agreed to resume with the same supports next session; no completion judgment was made.",
                "Pointed to the explanation card instead of answering aloud. I recorded the selected reason and kept all approved supports available.",
                "Observed during a small-group rehearsal. The group was noisy, so we moved to the quiet workspace and repeated the instructions in plain language.",
                "Selected all three cards, then chose to take a short break before explaining the order. Teacher follow-up is scheduled for the next activity period.",
            ]
            seed["observations"].append({"id": "o%02d" % n, "activity_id": aid, "note": notes[i % len(notes)], "context": "" if i == 9 else ["Individual practice", "Small-group rehearsal", "Workplace simulation", "Follow-up session"][i % 4], "created_by": actor["id"], "created_at": stamp(-i // 4, -i * 9), "updated_at": stamp(-i // 4, -i * 9)})

        action = "approved" if i in approved else "blocked" if i in blocked else "rejected" if i in rejected else "checked"
        details = {
            "approved": "Teacher approved version 1 after reviewing the goal, evidence, and all approved accommodations.",
            "blocked": "The accommodation guard prevented approval because one approved support was missing.",
            "rejected": "Teacher requested a clearer choice of task cards before trying this activity.",
            "checked": "Local demo alignment check saved. Teacher review is required before learner access.",
        }
        seed["audit"].append({"id": "audit%03d" % n, "actor": actor["name"], "action": action, "target": activity["title"], "target_id": aid, "version": 1, "created_at": stamp(-i // 4, -i * 6), "detail": details[action]})

    for j in range(8):
        activity = seed["activities"][j]
        seed["audit"].append({"id": "audit%03d" % (31 + j), "actor": users[j % 2]["name"], "action": "created", "target": activity["title"], "target_id": activity["id"], "version": 1, "created_at": stamp(-12, -j * 20), "detail": "Created a synthetic practice activity linked to its existing approved goal."})
    return seed
