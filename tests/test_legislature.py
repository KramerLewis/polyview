from ingest.legislature import match_members, split_names


def test_split_names_keeps_initials():
    assert split_names("Walsh, Wilson, C., Wilson, J., Ybarra") == [
        "Walsh", "Wilson, C.", "Wilson, J.", "Ybarra"]


def test_match_members_uses_initial_for_shared_last_names():
    members = [
        {"biennium": "2025-26", "chamber": "Senate", "last_name": "Wilson", "first_name": "Claire",
         "member_id": "1", "district": "30", "party": "D"},
        {"biennium": "2025-26", "chamber": "Senate", "last_name": "Wilson", "first_name": "Jeff",
         "member_id": "2", "district": "19", "party": "R"},
    ]
    votes = [{"biennium": "2025-26", "chamber": "Senate", "member": "Wilson, J."},
             {"biennium": "2025-26", "chamber": "Senate", "member": "Wilson"}]
    assert match_members(votes, members) == 1  # bare "Wilson" is ambiguous
    assert votes[0]["member_id"] == "2" and votes[1]["member_id"] == ""


def test_classify_motion():
    from ingest.legislature import classify_motion
    assert classify_motion("Final Passage as Recommended by the Conference Committee")["vote_type"] == "final_passage"
    assert classify_motion("3rd Reading & Final Passage")["vote_type"] == "passage"
    a = classify_motion("937 Couture Pg 99 Ln 10")
    assert (a["vote_type"], a["amendment"], a["amendment_sponsor"]) == ("amendment", "937", "Couture")
    assert classify_motion("234 Gildon Striker")["amendment_sponsor"] == "Gildon"
    assert classify_motion("Motion to Immediately Transmit to Senate")["vote_type"] == "procedural"
