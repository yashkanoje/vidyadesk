from leadagent.crypto import encrypt
from leadagent.store.models import Institute, Lead


FACTS = {
    "institute_name": "BrightPath Classes",
    "address": "Plot 12, Civil Township, Rourkela, Odisha 769004",
    "phone": "0661-2400000",
    "timings": "Monday to Saturday, 9 am to 8 pm",
    "courses": [
        {
            "name": "JEE Main + Advanced",
            "for_classes": "Class 11 and 12",
            "fee": "₹68,000 per year",
            "batches": ["Mon to Sat 6 am to 8 am", "Mon to Sat 5 pm to 7:30 pm"],
        },
        {
            "name": "NEET",
            "for_classes": "Class 11 and 12",
            "fee": "₹62,000 per year",
            "batches": ["Mon to Sat 4 pm to 6:30 pm"],
        },
    ],
    "faq": [{"q": "Is there a demo class?", "a": "Yes, the first two classes are free."}],
}




def make_institute(session, slug="bright", owner_chat_id="999", whatsapp_phone_number_id=None, active=True):
    institute = Institute(
        slug=slug,
        name=slug.title() + " Classes",
        active=active,
        facts=FACTS,
        telegram_bot_token_enc=encrypt(f"token-{slug}"),
        telegram_secret=f"secret-{slug}",
        owner_telegram_chat_id=owner_chat_id,
        whatsapp_phone_number_id=whatsapp_phone_number_id,
        whatsapp_token_enc=encrypt("wa-token") if whatsapp_phone_number_id else None,
    )
    session.add(institute)
    session.commit()
    return institute


def make_lead(session, institute, user_id="111", channel="telegram", **fields):
    lead = Lead(institute_id=institute.id, channel=channel, channel_user_id=user_id, **fields)
    session.add(lead)
    session.commit()
    return lead
