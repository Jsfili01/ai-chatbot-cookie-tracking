import sys
import pandas as pd

df = pd.read_excel(sys.argv[1])
df = df[df["Last Found"].notna()].copy()          # drops BuiltWith's footer notice row
first = df["Location on Site"].astype(str).str.split("\n").str[0]
df["url"] = first.str.replace("/*", "", regex=False).str.strip()
df["url"] = df["url"].apply(lambda u: u if u.startswith("http") else "https://" + u)
for c in ("First Detected", "Last Found"):
    df[c] = pd.to_datetime(df[c], unit="D", origin="1899-12-30")
cut = pd.Timestamp.today() - pd.Timedelta(days=90)
recent = df[df["Last Found"] >= cut]
print(f"{len(df)} sites in file, {len(recent)} seen in the last 90 days")

# keep only what the study needs; the PII columns (emails, phones, people) are dropped
cols = {"Root Domain": "root_domain", "url": "url", "Country": "country",
        "Vertical": "vertical", "Tranco": "tranco_rank",
        "First Detected": "first_detected", "Last Found": "last_found",
        "Compliance": "builtwith_compliance"}
recent[list(cols)].rename(columns=cols).to_csv("chatbase_sites_clean.csv", index=False)
recent["url"].to_csv("candidates_chatbase.txt", index=False, header=False)
print("wrote chatbase_sites_clean.csv and candidates_chatbase.txt")
