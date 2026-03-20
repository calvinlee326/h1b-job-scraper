import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import os
from datetime import datetime, timedelta

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def scrape_h1b_jobs():
    url = "https://h1bdata.info/topcompanies.php"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to retrieve data from {url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    companies = []

    table = soup.find("table", {"class": "table"})

    if not table:
        print("Table not found on the page.")
        return []

    for row in table.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) >= 4:
            company = {
                'Rank': cols[0].text.strip(),
                'Company Name': cols[1].text.strip(),
                'Total H-1B Visas Filling': cols[2].text.strip(),
                'Average Salary': cols[3].text.strip()
            }
            companies.append(company)
    return companies


def _parse_numeric(df):
    """Add Salary_Num and Visas_Num columns to df."""
    df = df.copy()
    df['Salary_Num'] = df['Average Salary'].replace(r'[$,]', '', regex=True).astype(float)
    df['Visas_Num'] = df['Total H-1B Visas Filling'].replace(r'[,]', '', regex=True).astype(float)
    return df


def analyze_data(df):
    print("\n--- Data Analysis ---")
    print(df.describe())

    df = _parse_numeric(df)
    df['Salary_Num'].plot(kind='hist', bins=20)
    plt.title('H1B Company Average Salary Distribution')
    plt.xlabel('Average Salary')
    plt.ylabel('Company Count')
    plt.tight_layout()
    os.makedirs('docs', exist_ok=True)
    plt.savefig('docs/salary_distribution.png')
    plt.close()


def detect_anomalies(df):
    """Detect statistical anomalies in salary and visa count data.

    Uses z-scores to flag outliers and compares with the previous day's
    archived data to surface significant daily changes. Writes a plain-text
    report and, when running inside GitHub Actions, appends a Markdown
    summary to the step summary.
    """
    print("\n--- Anomaly Detection ---")
    df = _parse_numeric(df)

    # Z-score detection
    for col, name in [('Salary_Num', 'Salary'), ('Visas_Num', 'Visas')]:
        mean = df[col].mean()
        std = df[col].std()
        df[f'{name}_ZScore'] = (df[col] - mean) / std

    threshold = 2.5
    anomalies = df[
        (df['Salary_ZScore'].abs() > threshold) |
        (df['Visas_ZScore'].abs() > threshold)
    ][['Company Name', 'Average Salary', 'Total H-1B Visas Filling',
       'Salary_ZScore', 'Visas_ZScore']].copy()

    # Cross-day salary change detection
    daily_changes = pd.DataFrame()
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    prev_path = f'data/h1b_companies_{yesterday}.csv'
    if os.path.exists(prev_path):
        prev = _parse_numeric(pd.read_csv(prev_path))
        merged = df.merge(
            prev[['Company Name', 'Salary_Num']].rename(
                columns={'Salary_Num': 'Prev_Salary'}),
            on='Company Name', how='inner'
        )
        merged['Salary_Pct_Change'] = (
            (merged['Salary_Num'] - merged['Prev_Salary'])
            / merged['Prev_Salary'] * 100
        )
        daily_changes = merged[merged['Salary_Pct_Change'].abs() > 10][
            ['Company Name', 'Prev_Salary', 'Salary_Num', 'Salary_Pct_Change']
        ].copy()

    # Plain-text report
    today = datetime.now().strftime('%Y-%m-%d')
    report_path = f'data/anomalies_{today}.txt'
    with open(report_path, 'w') as f:
        f.write(f"H1B Anomaly Report — {today}\n{'='*50}\n\n")
        f.write(f"Companies analyzed : {len(df)}\n")
        f.write(f"Outliers (|z| > {threshold}): {len(anomalies)}\n\n")

        if not anomalies.empty:
            f.write("STATISTICAL OUTLIERS:\n")
            for _, r in anomalies.iterrows():
                f.write(
                    f"  {r['Company Name']:50s}  "
                    f"salary={r['Average Salary']:>10s} (z={r['Salary_ZScore']:+.2f})  "
                    f"visas={r['Total H-1B Visas Filling']:>10s} (z={r['Visas_ZScore']:+.2f})\n"
                )

        if not daily_changes.empty:
            f.write("\nDAILY SALARY CHANGES > 10%:\n")
            for _, r in daily_changes.iterrows():
                f.write(
                    f"  {r['Company Name']:50s}  "
                    f"${r['Prev_Salary']:>10,.0f} → ${r['Salary_Num']:>10,.0f}  "
                    f"({r['Salary_Pct_Change']:+.1f}%)\n"
                )

    # GitHub Actions step summary (no-op outside Actions)
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with open(summary_path, 'a') as f:
            f.write(f"\n## Anomaly Detection — {today}\n")
            f.write(f"- Companies analyzed: **{len(df)}**\n")
            f.write(f"- Statistical outliers: **{len(anomalies)}**\n")
            f.write(f"- Daily salary changes > 10%%: **{len(daily_changes)}**\n")
            if not anomalies.empty:
                f.write("\n| Company | Salary | Salary Z | Visas | Visas Z |\n")
                f.write("|---------|--------|:--------:|-------|:-------:|\n")
                for _, r in anomalies.iterrows():
                    f.write(
                        f"| {r['Company Name']} | {r['Average Salary']} | "
                        f"{r['Salary_ZScore']:+.2f} | {r['Total H-1B Visas Filling']} | "
                        f"{r['Visas_ZScore']:+.2f} |\n"
                    )

    print(f"Anomaly report saved to {report_path}")
    print(f"Outliers found: {len(anomalies)}")
    return anomalies


def build_prediction_model(df):
    """Score and cluster companies by H1B attractiveness.

    Computes a composite H1B attractiveness score (60 % salary weight +
    40 % visa-volume weight) and groups companies into four clusters using
    k-means. Results are saved to data/h1b_predictions.csv and visualised
    in docs/h1b_scores.png.
    """
    print("\n--- Prediction Model ---")
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.cluster import KMeans

    df = _parse_numeric(df)

    features = df[['Salary_Num', 'Visas_Num']].values
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(features)

    # Composite attractiveness score
    df['H1B_Score'] = 0.6 * scaled[:, 0] + 0.4 * scaled[:, 1]
    df['Score_Rank'] = df['H1B_Score'].rank(ascending=False).astype(int)

    # Cluster companies into 4 tiers
    km = KMeans(n_clusters=4, random_state=42, n_init=10)
    df['Cluster'] = km.fit_predict(scaled)

    # Label each cluster by ascending median salary
    sorted_clusters = (
        df.groupby('Cluster')['Salary_Num']
        .median()
        .sort_values()
        .index
        .tolist()
    )
    tier_labels = ['Budget Sponsor', 'Mid Tier', 'High Salary', 'Elite Sponsor']
    cluster_map = dict(zip(sorted_clusters, tier_labels))
    df['Category'] = df['Cluster'].map(cluster_map)

    # Save predictions
    out_cols = [
        'Rank', 'Company Name', 'Total H-1B Visas Filling',
        'Average Salary', 'H1B_Score', 'Score_Rank', 'Category'
    ]
    df[out_cols].to_csv('data/h1b_predictions.csv', index=False)

    # Horizontal bar chart — top 20 by score
    top20 = df.nlargest(20, 'H1B_Score').sort_values('H1B_Score')
    palette = {
        'Budget Sponsor': '#d9534f',
        'Mid Tier':       '#f0ad4e',
        'High Salary':    '#5bc0de',
        'Elite Sponsor':  '#5cb85c',
    }
    bar_colors = [palette.get(c, 'steelblue') for c in top20['Category']]

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.barh(top20['Company Name'], top20['H1B_Score'], color=bar_colors)
    ax.set_xlabel('H1B Attractiveness Score')
    ax.set_title('Top 20 Companies by H1B Attractiveness\n(60% Salary · 40% Visa Volume)')

    legend_elements = [Patch(facecolor=v, label=k) for k, v in palette.items()]
    ax.legend(handles=legend_elements, loc='lower right')

    plt.tight_layout()
    os.makedirs('docs', exist_ok=True)
    plt.savefig('docs/h1b_scores.png')
    plt.close()

    print("Predictions saved to data/h1b_predictions.csv")
    print("Top 5 by H1B Attractiveness Score:")
    for _, r in df.nlargest(5, 'H1B_Score').iterrows():
        print(
            f"  {int(r['Score_Rank']):>3}. {r['Company Name']:<50s} "
            f"[{r['Category']}]  score={r['H1B_Score']:.3f}"
        )

    return df[['Company Name', 'H1B_Score', 'Score_Rank', 'Category']]


def daily_task():
    print("Starting daily task...")
    companies = scrape_h1b_jobs()
    if companies:
        df = pd.DataFrame(companies)
        os.makedirs('data', exist_ok=True)

        # Save current data and a dated archive for cross-day comparison
        today = datetime.now().strftime('%Y-%m-%d')
        df.to_csv('data/h1b_companies.csv', index=False)
        df.to_csv(f'data/h1b_companies_{today}.csv', index=False)

        analyze_data(df)
        detect_anomalies(df)
        build_prediction_model(df)

        print(f"\n{len(df)} records saved.")
    else:
        print("No data was scraped.")


if __name__ == "__main__":
    daily_task()
