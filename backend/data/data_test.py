"""
Prints the structure of every .parquet file next to this script
and saves the same report to schema_report.txt.

Run from anywhere:  python inspect_data.py
Then paste the contents of schema_report.txt back into the chat.
"""
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent
REPORT = DATA_DIR / "schema_report.txt"
MAX_CELL = 80  # truncate long text so the report stays readable


def short(v):
    s = str(v).replace("\n", " ")
    return s if len(s) <= MAX_CELL else s[:MAX_CELL] + "..."


def describe(path):
    df = pd.read_parquet(path)
    lines = [f"\n{'=' * 70}", f"{path.stem}  rows={len(df):,}  cols={df.shape[1]}", "=" * 70]

    for col in df.columns:
        s = df[col]
        try:
            n_unique = s.nunique()
        except TypeError:  # unhashable values such as lists
            n_unique = "n/a"
        sample = s.dropna().iloc[0] if s.notna().any() else None
        extra = ""
        if pd.api.types.is_string_dtype(s) and s.notna().any():
            avg_len = s.dropna().astype(str).str.len().mean()
            if avg_len > 100:
                extra = f"  [LONG TEXT, avg {avg_len:.0f} chars]"
        lines.append(
            f"- {col:<28} {str(s.dtype):<16} nulls={s.isna().sum():<7} "
            f"unique={n_unique:<8} e.g. {short(sample)}{extra}"
        )

    # low-cardinality columns: show the values (useful for status, type, etc.)
    for col in df.columns:
        try:
            if 1 < df[col].nunique() <= 12:
                vc = df[col].value_counts(dropna=False).head(12).to_dict()
                lines.append(f"  values of {col}: {vc}")
        except TypeError:
            pass

    return "\n".join(lines)


def main():
    files = sorted(DATA_DIR.glob("*.parquet"))
    if not files:
        print(f"No .parquet files found in {DATA_DIR}")
        return

    out = [f"Found {len(files)} parquet files in {DATA_DIR}"]
    for f in files:
        try:
            out.append(describe(f))
        except Exception as e:  # keep going if one file fails
            out.append(f"\n{f.stem}: could not read ({e})")

    text = "\n".join(out)
    print(text)
    REPORT.write_text(text, encoding="utf-8")
    print(f"\nSaved to {REPORT}")


if __name__ == "__main__":
    main()