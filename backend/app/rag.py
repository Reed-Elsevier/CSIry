"""
Enterprise Knowledge RAG over the parquet files.

Setup:   python -m pip install pandas pyarrow scikit-learn boto3 openai python-dotenv
Key:     set AWS_BEARER_TOKEN_BEDROCK and AWS credentials/profile, or OPENAI_API_KEY for fallback
Data:    run this file inside backend/data (or set DATA_DIR)

Commands:
  python rag_pipeline.py explore                 # look at the data: link checks + a sample conflict
  python rag_pipeline.py ask "how do I request elevated access?"
  python rag_pipeline.py gaps                    # searches that return no results
  python rag_pipeline.py projects                # pick a demo project with lots of material
  python rag_pipeline.py find "Horizon"          # project_id lookup by name fragment
  python rag_pipeline.py project PRJ000020       # decisions + open actions
"""
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MODEL = os.getenv("AWS_BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
MIN_SCORE = 0.08          # below this the KB probably has nothing relevant -> don't answer
CONFLICT_SIM = 0.90       # bodies less similar than this count as "conflicting"
STATUS_RANK = {"Published": 0, "Draft": 1, "Archived": 2}
TABLES = ["knowledge_articles", "knowledge_article_versions", "sops", "documents",
          "meetings", "action_items", "search_logs", "chat_channels", "chat_messages", "emails"]
HERE = Path(__file__).resolve().parent


def find_data_dir():
    if os.getenv("DATA_DIR"):
        return Path(os.environ["DATA_DIR"])
    for p in [HERE, HERE / "data", HERE.parent / "data"]:
        if (p / "knowledge_articles.parquet").exists():
            return p
    raise FileNotFoundError("Could not find the parquet files. Set DATA_DIR.")


def llm(prompt, system="", max_tokens=1200):
    if os.getenv("AWS_BEARER_TOKEN_BEDROCK") or (
        os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")
    ):
        import boto3

        region = os.getenv("AWS_REGION", "us-east-1")
        session_kwargs = {}
        if os.getenv("AWS_PROFILE"):
            session_kwargs["profile_name"] = os.getenv("AWS_PROFILE")
        session = boto3.Session(**session_kwargs)
        client_kwargs = {"region_name": region}

        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            client_kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID")
            client_kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")
            if os.getenv("AWS_SESSION_TOKEN"):
                client_kwargs["aws_session_token"] = os.getenv("AWS_SESSION_TOKEN")

        client = session.client("bedrock-runtime", **client_kwargs)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if system:
            body["system"] = system

        response = client.invoke_model(
            modelId=os.getenv("AWS_BEDROCK_MODEL_ID", MODEL),
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(response["body"].read())
        content = payload.get("content", [])
        return content[0].get("text", "") if content else ""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No model credentials found. Set AWS_BEARER_TOKEN_BEDROCK plus AWS credentials/profile, "
            "or OPENAI_API_KEY."
        )

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    messages = [{"role": "user", "content": prompt}]
    if system:
        messages.insert(0, {"role": "system", "content": system})

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


class KB:
    def __init__(self):
        d = find_data_dir()
        self.t = {n: pd.read_parquet(d / f"{n}.parquet") for n in TABLES
                  if (d / f"{n}.parquet").exists()}

        # SOPs have no body text: they are metadata (current? review due?) on top of articles
        sops = (self.t["sops"].sort_values(["is_current", "version"])
                .drop_duplicates("article_id", keep="last")
                .rename(columns={"version": "sop_version", "is_current": "sop_is_current",
                                 "review_due_date": "sop_review_due"})
                [["article_id", "sop_id", "sop_version", "sop_is_current", "sop_review_due"]])
        a = self.t["knowledge_articles"].merge(sops, on="article_id", how="left")
        a["text"] = a["title"] + ". " + a["tags"] + ". " + a["body"]
        self.articles = a.reset_index(drop=True)

        # Articles are short (~470 chars) so one article = one chunk, no splitting needed.
        # TF-IDF is the zero-cost baseline; swap in embeddings if the organizers give an endpoint.
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2,
                                   stop_words="english")
        self.X = self.vec.fit_transform(self.articles["text"])

    # ------------------------------------------------------------ retrieval
    def search(self, query, k=12):
        s = linear_kernel(self.vec.transform([query]), self.X).ravel()
        idx = np.argsort(-s)[:k]
        out = self.articles.iloc[idx].copy()
        out["raw_score"] = s[idx]
        return out

    def body_similarity(self, a, b):
        return float(linear_kernel(self.vec.transform([a]), self.vec.transform([b]))[0, 0])

    def resolve(self, hits):
        """Group hits by (topic_key, app_id). Within a group the primary is the Published,
        most recently reviewed, highest-version article; others that disagree are conflicts."""
        hits = hits.copy()
        hits["_rank"] = hits["status"].map(STATUS_RANK).fillna(3)
        primaries, conflicts = [], []
        # TODO: decide if division_id should also be part of the group key
        for _, g in hits.groupby(["topic_key", "app_id"]):
            g = g.sort_values(["_rank", "last_reviewed_at", "version"],
                              ascending=[True, False, False])
            p = g.iloc[0]
            primaries.append(p)
            for _, o in g.iloc[1:].iterrows():
                sim = self.body_similarity(p["body"], o["body"])
                if sim < CONFLICT_SIM:
                    conflicts.append({
                        "primary": p["article_id"], "other": o["article_id"],
                        "other_status": o["status"], "other_version": int(o["version"]),
                        "other_last_reviewed": str(o["last_reviewed_at"].date()),
                        "body_similarity": round(sim, 2)})
        prim = pd.DataFrame(primaries).sort_values("raw_score", ascending=False)
        return prim, conflicts

    # ------------------------------------------------------------ Q1: how-to with citations
    def _fmt(self, r, tag):
        sop = ""
        if pd.notna(r["sop_id"]):
            sop = (f" | {r['sop_id']} current={r['sop_is_current']} "
                   f"review_due={r['sop_review_due'].date()}")
        return (f"[{r['article_id']}] ({tag}) {r['title']}\n"
                f"status={r['status']} version={r['version']} "
                f"last_reviewed={r['last_reviewed_at'].date()}{sop}\n{r['body']}")

    def ask(self, question, n_primary=4):
        hits = self.search(question)
        if hits["raw_score"].max() < MIN_SCORE:
            return {"answer": "I couldn't find anything in the knowledge base about that.",
                    "sources": [], "conflicts": [], "invalid_citations": []}

        prim, conflicts = self.resolve(hits)
        prim = prim.head(n_primary)
        prim_ids = set(prim["article_id"])
        conf = [c for c in conflicts if c["primary"] in prim_ids]

        blocks = [self._fmt(r, "PRIMARY") for _, r in prim.iterrows()]
        by_id = self.articles.set_index("article_id", drop=False)
        for c in conf:
            blocks.append(self._fmt(by_id.loc[c["other"]], "CONFLICTING, differs from " + c["primary"]))

        system = (
            "You answer how-to questions using ONLY the sources provided. "
            "Cite every step or claim with its source id in square brackets, e.g. [KB000123]. "
            "Sources tagged PRIMARY are authoritative (Published, most recently reviewed). "
            "If a CONFLICTING source disagrees, follow the PRIMARY, then add a 'Heads up:' line "
            "naming both ids and what differs (and mention status/review date). "
            "If a source is Draft/Archived or its SOP is not current or overdue for review, say so. "
            "If the sources do not answer the question, say that. Never invent steps.")
        text = llm(f"Question: {question}\n\nSources:\n\n" + "\n\n---\n\n".join(blocks), system)

        shown = prim_ids | {c["other"] for c in conf}
        cited = set(re.findall(r"KB\d{6}", text))
        return {"answer": text, "sources": sorted(shown), "conflicts": conf,
                "invalid_citations": sorted(cited - shown)}  # should be empty

    # ------------------------------------------------------------ Q2: searches with no results
    def search_gaps(self, top=25):
        sl = self.t["search_logs"].copy()
        sl["month"] = sl["searched_at"].dt.to_period("M").astype(str)
        sl["zero"] = sl["results_count"] == 0
        sl["no_click"] = (sl["results_count"] > 0) & sl["clicked_article_id"].isna()

        summary = {
            "zero_result_rate": round(float(sl["zero"].mean()), 4),
            "zero_rate_by_source": sl.groupby("source")["zero"].mean().round(4).to_dict(),
            "no_click_rate_by_source": sl.groupby("source")["no_click"].mean().round(4).to_dict(),
        }
        monthly = sl.groupby("month")["zero"].mean().round(4)  # look for spikes

        q = (sl[sl["zero"]].groupby("query_text")
             .agg(searches=("search_id", "size"), users=("employee_id", "nunique"),
                  first_seen=("searched_at", "min"), last_seen=("searched_at", "max"))
             .sort_values("searches", ascending=False).head(top))

        # Content gap or findability problem? Compare each failed query to the nearest article.
        sims = linear_kernel(self.vec.transform(q.index), self.X)
        q["nearest_article"] = self.articles["article_id"].to_numpy()[sims.argmax(axis=1)]
        q["nearest_sim"] = sims.max(axis=1).round(2)
        q["diagnosis"] = np.where(q["nearest_sim"] >= 0.3,
                                  "article exists: fix synonyms/typos in search",
                                  "no matching content: write an article")  # tune 0.3
        return summary, monthly, q

    def explain_gaps(self, q):
        return llm("These search queries returned no results. Group them into 4-6 themes, "
                   "name each theme, give the query count, and suggest the knowledge article "
                   "to write or the search fix.\n" + q.reset_index().to_csv(index=False))

    # ------------------------------------------------------------ Q3: decisions + open actions
    def top_projects(self, n=10):
        m, docs, ai = self.t["meetings"], self.t["documents"], self.t["action_items"]
        a = m.groupby("project_id").size().rename("meetings")
        d = docs.groupby("project_id").size().rename("documents")
        j = ai.merge(m[["meeting_id", "project_id"]], on="meeting_id")
        o = j[j["status"].isin(["Open", "Overdue"])].groupby("project_id").size().rename("open_actions")
        df = pd.concat([a, d, o], axis=1).fillna(0).astype(int)
        df["total"] = df.sum(axis=1)
        return df.sort_values("total", ascending=False).head(n)

    def find_project(self, fragment):
        """No projects table exists, but project names appear inside titles."""
        m, d = self.t["meetings"], self.t["documents"]
        hit = pd.concat([m[m["title"].str.contains(fragment, case=False, na=False)][["project_id", "title"]],
                         d[d["title"].str.contains(fragment, case=False, na=False)][["project_id", "title"]]])
        return hit.dropna().drop_duplicates().head(20)

    def project_brief(self, project_id):
        m, ai, docs = self.t["meetings"], self.t["action_items"], self.t["documents"]
        pm = m[m["project_id"] == project_id].sort_values("start_ts")
        pdoc = docs[docs["project_id"] == project_id].sort_values("created_at")
        decisions = pdoc[pdoc["doc_type"].isin(["Decision Log", "Architecture Decision Record"])]

        acts = ai[ai["meeting_id"].isin(pm["meeting_id"])].merge(
            pm[["meeting_id", "title", "start_ts"]], on="meeting_id")
        # Open + Overdue = everything not completed (4,622 rows have completed_at null)
        open_actions = acts[acts["status"].isin(["Open", "Overdue"])].sort_values("due_date")

        ctx = ["DECISION DOCUMENTS:"] + [
            f"[{r.document_id}] {r.doc_type} ({r.created_at.date()}): {r.body[:700]}"
            for r in decisions.itertuples()]
        ctx += ["", "MEETINGS:"] + [
            f"[{r.meeting_id}] {r.meeting_type} ({r.start_ts.date()}): {r.transcript_summary[:500]}"
            for r in pm.itertuples()]
        summary = llm(
            f"Project {project_id}.\n" + "\n".join(ctx)
            + "\n\nSummarise the decisions made (newest last), citing [DOC...] or [MTG...] ids. "
              "Then give a 2-sentence status. Use only the text above.",
            system="You are a precise project analyst. Never invent decisions.", max_tokens=1500)

        # The open-actions list comes straight from the data, not from the LLM, so it is exact.
        cols = ["action_item_id", "description", "owner_employee_id", "due_date", "status", "meeting_id"]
        return {"summary": summary, "open_actions": open_actions[cols],
                "counts": {"meetings": len(pm), "docs": len(pdoc), "decision_docs": len(decisions),
                           "open_actions": len(open_actions),
                           "overdue": int((open_actions["status"] == "Overdue").sum())}}

    # ------------------------------------------------------------ look at the data
    def explore(self):
        a, s = self.articles, self.t["sops"]
        print("SOPs whose article_id is missing from knowledge_articles:",
              int((~s["article_id"].isin(a["article_id"])).sum()))
        print("Meetings with no project_id:", int(self.t["meetings"]["project_id"].isna().sum()))
        sl = self.t["search_logs"]
        print("Zero-result searches:", int((sl["results_count"] == 0).sum()), "of", len(sl))

        pub = a[a["status"] == "Published"]
        sizes = pub.groupby(["topic_key", "app_id"]).size().sort_values(ascending=False)
        print(f"\nGroups of Published articles sharing topic_key+app_id: {(sizes > 1).sum()}")
        key = sizes.index[0]
        print(f"\nBiggest group {key}: showing 3 articles to see what a conflict looks like\n")
        g = a[(a["topic_key"] == key[0]) & (a["app_id"] == key[1])].head(3)
        for r in g.itertuples():
            print(f"[{r.article_id}] {r.status} v{r.version} reviewed {r.last_reviewed_at.date()} "
                  f"division={r.division_id}\n  {r.body[:350]}\n")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "explore"
    kb = KB()
    if cmd == "explore":
        kb.explore()
    elif cmd == "ask":
        res = kb.ask(" ".join(sys.argv[2:]))
        print(res["answer"])
        print("\nsources:", res["sources"])
        print("conflicts:", json.dumps(res["conflicts"], indent=2))
        print("invalid citations:", res["invalid_citations"])
    elif cmd == "gaps":
        summary, monthly, q = kb.search_gaps()
        print(json.dumps(summary, indent=2))
        print("\nzero-result rate by month:\n", monthly.to_string())
        print("\n", q.to_string())
        print("\n", kb.explain_gaps(q))
    elif cmd == "projects":
        print(kb.top_projects().to_string())
    elif cmd == "find":
        print(kb.find_project(" ".join(sys.argv[2:])).to_string())
    elif cmd == "project":
        res = kb.project_brief(sys.argv[2])
        print(res["counts"], "\n\n", res["summary"], "\n\n", res["open_actions"].to_string())