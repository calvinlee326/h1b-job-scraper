import requests # to make HTTP requests
from bs4 import BeautifulSoup # to parse HTML content
import pandas as pd # to handle data
import matplotlib.pyplot as plt # to create plots


headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def scrape_h1b_jobs():
    url = "https://h1bdata.info/topcompanies.php"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to retrieve data from {url}")
        return[]
    
    soup = BeautifulSoup(response.text, "html.parser")
    companies = []
    
    table = soup.find("table", {"class": "table"})
    
    if not table:
        print("Table not found on the page.")
        return []
    
    # Extract company names from the table
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

def analyze_data(df):
    print("\n--- Data Analysis ---")
    print(df.describe())
    
    # Calculate the average salary by company
    df['Average Salary'] = df['Average Salary'].replace(r'[$,]', '', regex=True).astype(float)
    df['Average Salary'].plot(kind='hist', bins=20)
    plt.title('H1B Company Average Salary Distribution')
    plt.xlabel('Average Salary')
    plt.ylabel('Company Count')
    plt.tight_layout()
    
    plt.savefig('salary_distribution.png')
    plt.close()
    # plt.show()
    
def daily_task():
    print("Starting daily task...")
    companies = scrape_h1b_jobs()
    if companies:
        df = pd.DataFrame(companies)
        df.to_csv("h1b_companies.csv", index=False)
        analyze_data(df)
        print(f"{len(df)} counts data saved to h1b_companies.csv")
    else:
        print("No data was scraped.")
            
if __name__ == "__main__":
    daily_task()
    
    
        

