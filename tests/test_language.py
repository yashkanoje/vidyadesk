from leadagent.language import REWRITE_INSTRUCTION, rewrite_script, script_of


def test_script_of_moved_here_unchanged():
    assert script_of("ନମସ୍କାର, ଫି କେତେ?") == "odia"
    assert script_of("नमस्ते, फीस कितनी है?") == "devanagari"
    assert script_of("namaskar, fees kete?") == "latin"
    assert script_of("123 ?!") == "none"


def test_a_reply_in_another_script_must_be_rewritten():
    assert rewrite_script("क्या सेक्टर 19 से बस है?", "Yes, there is a bus from Sector 19.") == "devanagari"
    assert rewrite_script("mu sir sahita katha heba ku chahunchi", "ଆମର ଟିମ୍ ଶୀଘ୍ର ଯୋଗାଯୋଗ କରିବେ।") == "latin"
    assert rewrite_script("ଡେମୋ କ୍ଲାସ୍ ଅଛି କି?", "Haan, pehle do class free hain.") == "odia"


def test_a_reply_in_the_same_script_is_left_alone():
    assert rewrite_script("What is the fee?", "The fee is 68,000 rupees a year.") is None
    assert rewrite_script("नमस्ते", "नमस्ते! मैं सहायक हूँ।") is None
    assert rewrite_script("123", "Hello") is None  # the user wrote no letters at all
    assert rewrite_script("hello", "") is None


def test_every_target_script_has_an_instruction():
    assert set(REWRITE_INSTRUCTION) == {"odia", "devanagari", "latin"}
