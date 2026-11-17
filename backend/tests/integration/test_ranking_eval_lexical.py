from sqlalchemy.orm import Session

from app.domains.evaluation.ranking_eval import lexical_rankings
from app.domains.evaluation.talentclef import TCDataset, TCJob, TCResume


def test_lexical_rankings_use_production_fts_on_a_temp_table(db_session: Session) -> None:
    ds = TCDataset(
        jobs={"q": TCJob("q", "Cashier with cash handling skills", ("Cash Handling",), None)},
        resumes={
            "r1": TCResume("r1", "Experienced cashier. Cash handling and customer service.", None),
            "r2": TCResume("r2", "Mechanical engineer designing HVAC systems.", None),
            "r3": TCResume("r3", "Cash office supervisor.", None),
        },
        qrels={},
    )
    ranked = lexical_rankings(db_session, ds)["q"]
    assert ranked[0] == "r1" and "r2" not in ranked  # OR semantics, ts_rank_cd ordering
