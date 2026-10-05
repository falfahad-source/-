"""«الذكاء الاصطناعي في الإعجاز العلمي»: sends a verse with the researcher prompt to an
external AI platform and returns its report, labeled UNVERIFIED_CLAIM.

Until the platform's API is available the section runs in test mode (`AFAQ_AI_PROVIDER`
unset or "mock"): the whole flow works end to end, but the report is a fixed template that
says plainly it is not research. See `providers.py` for how to connect the real platform.
"""
