"""AI-CONTEXT: Uzbek coaching explanations, DRAFTED — never released by this script.

WHAT THIS IS FOR. Q-9 says a driver whose language has no released coaching sees an honest
"not yet in your language" rather than English. That has been the state since M15 shipped,
and it is correct rather than lazy — but it protects a gap, and the gap is what a driver
came for. This drafts the first language.

WHY IT DOES NOT RELEASE, unlike the officer content drafted beside it. The owner waived
review for the ENGLISH officer lines: if one is clumsy a driver hears a slightly odd
sentence from a simulated policeman. **Coaching is the one place in this module where a
mistranslation teaches something false.** It is the text that explains WHY an answer missed,
in the driver's own language, to someone who cannot check it against the English. Entry 185
declined to draft Uzbek at all for exactly this reason — "unreviewed Uzbek in the table is a
thing waiting to be released by mistake" — and the thing that changed is not the risk, it is
that the owner reads Uzbek and can be the named reviewer Q-6 requires.

So: drafted here, reviewed and released by a human in /admin/roadside, and only then given a
voice by the synthesis job — in `uz-UZ-SardorNeural`, not the officer's English voice.

THE ENGLISH IS NOT TRANSLATED WORD FOR WORD, and that is the point of writing them rather
than passing the English through a translator. Each explains what the officer is ASKING FOR
and what a complete answer contains — the glossable nouns stay English because they are what
the driver must recognise at a real window ("logbook" is not usefully rendered as anything
else when the officer will say "logbook").
"""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.m15_roadside.domain.enums import ContentStatus
from app.modules.m15_roadside.domain.models import CoachingContent, Intent
from db_registry import import_all_models

LOCALE = "uz"

EXPLANATIONS = {
    "destination": {
        "explanation": (
            "Bu savolda inspektor yukni QAYERGA olib ketayotganingizni so'rayapti — "
            "yakuniy manzilni. To'liq javob shahar nomini o'z ichiga oladi, masalan "
            "\"Chicago\" yoki \"Dallas, Texas\". Qayerdan yuk olganingizni emas, qayerga "
            "borayotganingizni ayting."
        ),
        "glosses": {
            "destination": "manzil — yukni tushiradigan joyingiz",
            "load": "yuk — tirkamangizdagi mol",
        },
    },
    "hos_hours_driven": {
        "explanation": (
            "Inspektor bugun necha SOAT haydaganingizni so'rayapti. Javobda raqam bo'lishi "
            "kerak — \"besh soat\", \"olti yarim soat\". Necha kun yo'ldasiz yoki qancha "
            "masofa bosganingiz emas, faqat bugungi haydash soatlari."
        ),
        "glosses": {
            "hours": "soat — bugun rulda o'tkazgan vaqtingiz",
            "logbook": "logbook — ish soatlaringiz yozib boriladigan daftar yoki planshet",
        },
    },
    "logbook_request": {
        "explanation": (
            "Bu buyruq, savol emas: inspektor logbook'ingizni ko'rmoqchi. Qisqa tasdiq "
            "yetarli — \"Ha, mana\" yoki \"Bir daqiqa, hozir olaman\". Uni qidirayotgan "
            "bo'lsangiz, shuni aytib qo'ying; jim turish inspektorga tushunmagandek "
            "ko'rinadi."
        ),
        "glosses": {
            "logbook": "logbook — ish soatlaringiz yozib boriladigan daftar yoki planshet",
        },
    },
}


def main() -> None:
    import_all_models()
    db = SessionLocal()
    try:
        added = skipped = replaced = 0
        for key, payload in EXPLANATIONS.items():
            intent = db.scalar(select(Intent).where(Intent.key == key))
            if intent is None:
                print(f"  ! no intent {key!r} on this box — skipped")
                continue
            existing = db.scalar(
                select(CoachingContent).where(
                    CoachingContent.intent_id == intent.id,
                    CoachingContent.locale == LOCALE,
                )
            )
            if existing is not None:
                # AI-CONTEXT: A DRAFT IS BY DEFINITION NOT YET BLESSED, so overwrite it —
                # but never touch a row a human has already reviewed or released. The rows
                # this found on first run were PLACEHOLDERS in English sitting in the `uz`
                # slot ("[draft uz coaching for destination — owner-track content
                # pending]"), which is precisely the hazard entry 185 named: text waiting
                # in a language column to be released by mistake. Skipping them would have
                # left that live and reported success.
                if existing.review_status is not ContentStatus.draft:
                    print(f"  ! {key}: already {existing.review_status.value} — left alone")
                    skipped += 1
                    continue
                existing.explanation = payload["explanation"]
                existing.glosses = payload["glosses"]
                replaced += 1
                continue
            db.add(
                CoachingContent(
                    intent_id=intent.id,
                    locale=LOCALE,
                    explanation=payload["explanation"],
                    glosses=payload["glosses"],
                    review_status=ContentStatus.draft,
                )
            )
            added += 1
        db.commit()
        print(
            f"uz coaching: +{added} new, {replaced} draft rows replaced, "
            f"{skipped} left alone — ALL still `draft`."
        )
        print("Review and release them in /admin/roadside. Q-6: a named human, or nothing.")
        print("Released rows get a uz-UZ voice from the m15_content_audio job.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
