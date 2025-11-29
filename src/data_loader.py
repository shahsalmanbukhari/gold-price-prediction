"""
Gold Data Loader Module
Downloads historical gold price data from multiple sources
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import requests
import os
import numpy as np


class GoldDataDownloader:
    """Download and manage gold price data from various sources"""

    def __init__(self, output_dir='data/raw'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def download_usd_pkr_exchange_rate(self, years=5):
        """
        Download USD/PKR exchange rate from Yahoo Finance

        Args:
            years (int): Number of years of historical data

        Returns:
            pd.DataFrame: Exchange rate data
        """
        print(f"\n{'='*60}")
        print(f"Downloading USD/PKR exchange rate...")
        print(f"{'='*60}")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)

        try:
            # Download USD/PKR exchange rate (PKR=X)
            exchange = yf.download('PKR=X', start=start_date, end=end_date, progress=False)

            if exchange.empty:
                print("⚠ No exchange rate data received, using constant rate")
                return None

            exchange = exchange.reset_index()
            exchange.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
            exchange = exchange[['Date', 'Close']].copy()
            exchange.columns = ['Date', 'USD_PKR_Rate']

            # Save to file
            filepath = os.path.join(self.output_dir, 'usd_pkr_exchange_rate.csv')
            exchange.to_csv(filepath, index=False)

            print(f"✓ Successfully downloaded {len(exchange)} exchange rate records")
            print(f"✓ Date range: {exchange['Date'].min()} to {exchange['Date'].max()}")
            print(f"✓ Latest rate: {exchange['USD_PKR_Rate'].iloc[-1]:,.2f} PKR per USD")
            print(f"✓ Saved to: {filepath}")

            return exchange

        except Exception as e:
            print(f"✗ Error downloading exchange rate: {e}")
            return None

    def download_yahoo_finance(self, years=5):
        """
        Download gold futures data from Yahoo Finance (GC=F) with USD and PKR prices

        Args:
            years (int): Number of years of historical data

        Returns:
            pd.DataFrame: Gold price data with USD and PKR prices
        """
        print(f"\n{'='*60}")
        print(f"Downloading {years} years of gold data from Yahoo Finance...")
        print(f"{'='*60}")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)

        try:
            # Download gold futures data (GC=F)
            gold = yf.download('GC=F', start=start_date, end=end_date, progress=False)

            if gold.empty:
                print("✗ No data received from Yahoo Finance")
                return None

            gold = gold.reset_index()

            # Rename columns for consistency
            gold.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']

            # USD prices (original)
            gold['Open_USD_per_oz'] = gold['Open']
            gold['High_USD_per_oz'] = gold['High']
            gold['Low_USD_per_oz'] = gold['Low']
            gold['Close_USD_per_oz'] = gold['Close']

            # Download USD/PKR exchange rate
            exchange_rate_df = self.download_usd_pkr_exchange_rate(years)

            if exchange_rate_df is not None:
                # Merge exchange rate with gold data
                gold['Date'] = pd.to_datetime(gold['Date'])
                exchange_rate_df['Date'] = pd.to_datetime(exchange_rate_df['Date'])
                gold = pd.merge(gold, exchange_rate_df, on='Date', how='left')

                # Forward fill missing exchange rates
                gold['USD_PKR_Rate'] = gold['USD_PKR_Rate'].fillna(method='ffill').fillna(method='bfill')

                # If still missing, use default
                if gold['USD_PKR_Rate'].isnull().any():
                    gold['USD_PKR_Rate'].fillna(280, inplace=True)

                print(f"✓ Merged exchange rate data")
            else:
                # Use approximate constant rate if download fails
                print(f"⚠ Using constant exchange rate: 280 PKR/USD")
                gold['USD_PKR_Rate'] = 280

            # Convert to PKR using actual exchange rates
            gold['Open_PKR_per_oz'] = gold['Open'] * gold['USD_PKR_Rate']
            gold['High_PKR_per_oz'] = gold['High'] * gold['USD_PKR_Rate']
            gold['Low_PKR_per_oz'] = gold['Low'] * gold['USD_PKR_Rate']
            gold['Close_PKR_per_oz'] = gold['Close'] * gold['USD_PKR_Rate']

            # Convert to Pakistani units (tola)
            # 1 tola = 0.375 troy ounces (11.664 grams)
            gold['Open_PKR_per_tola'] = gold['Open_PKR_per_oz'] * 0.375
            gold['High_PKR_per_tola'] = gold['High_PKR_per_oz'] * 0.375
            gold['Low_PKR_per_tola'] = gold['Low_PKR_per_oz'] * 0.375
            gold['Close_PKR_per_tola'] = gold['Close_PKR_per_oz'] * 0.375

            # 1 troy ounce = 31.1035 grams
            gold['Close_PKR_per_gram'] = gold['Close_PKR_per_oz'] / 31.1035
            gold['Close_USD_per_gram'] = gold['Close_USD_per_oz'] / 31.1035

            # Save to file
            filepath = os.path.join(self.output_dir, 'gold_prices_usd_pkr.csv')
            gold.to_csv(filepath, index=False)

            print(f"✓ Successfully downloaded {len(gold)} records")
            print(f"✓ Date range: {gold['Date'].min()} to {gold['Date'].max()}")
            print(f"✓ Saved to: {filepath}")
            print(f"✓ Latest USD price: ${gold['Close_USD_per_oz'].iloc[-1]:,.2f} per oz")
            print(f"✓ Latest PKR price: PKR {gold['Close_PKR_per_tola'].iloc[-1]:,.2f} per tola")
            print(f"✓ Latest exchange rate: {gold['USD_PKR_Rate'].iloc[-1]:,.2f} PKR/USD")

            return gold

        except Exception as e:
            print(f"✗ Error downloading from Yahoo Finance: {e}")
            return None

    def create_sample_data(self, years=5):
        """
        Generate synthetic gold price data with USD and PKR prices

        Args:
            years (int): Number of years of data to generate

        Returns:
            pd.DataFrame: Synthetic gold price data with USD and PKR
        """
        print(f"\n{'='*60}")
        print("Generating synthetic gold price data (USD + PKR)...")
        print(f"{'='*60}")

        # Generate dates (daily data for specified years)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        n_days = len(dates)

        # Generate USD/PKR exchange rate (realistic trend)
        base_rate = 160  # Starting rate in 2020
        rate_trend = np.linspace(0, 120, n_days)  # Upward trend to ~280
        rate_seasonality = 10 * np.sin(np.linspace(0, years*2*np.pi, n_days))
        rate_noise = np.random.normal(0, 2, n_days)
        usd_pkr_rate = base_rate + rate_trend + rate_seasonality + rate_noise
        usd_pkr_rate = np.maximum(usd_pkr_rate, 100)  # Minimum rate

        # Generate USD gold price (per troy ounce)
        base_price_usd = 1800  # Base price in USD (realistic for 2020)
        trend_usd = np.linspace(0, 400, n_days)  # Upward trend
        seasonality_usd = 100 * np.sin(np.linspace(0, years*2*np.pi, n_days))
        random_walk_usd = np.cumsum(np.random.normal(0, 10, n_days))
        daily_noise_usd = np.random.normal(0, 20, n_days)

        close_price_usd = base_price_usd + trend_usd + seasonality_usd + random_walk_usd + daily_noise_usd
        close_price_usd = np.maximum(close_price_usd, 1000)  # Minimum USD price

        # Create OHLC for USD
        open_usd = close_price_usd + np.random.normal(0, 10, n_days)
        high_usd = close_price_usd + np.abs(np.random.normal(15, 10, n_days))
        low_usd = close_price_usd - np.abs(np.random.normal(15, 10, n_days))

        # Convert to PKR (per ounce)
        open_pkr_oz = open_usd * usd_pkr_rate
        high_pkr_oz = high_usd * usd_pkr_rate
        low_pkr_oz = low_usd * usd_pkr_rate
        close_pkr_oz = close_price_usd * usd_pkr_rate

        # Convert to tola (1 tola = 0.375 oz)
        df = pd.DataFrame({
            'Date': dates,
            'USD_PKR_Rate': usd_pkr_rate,
            'Open_USD_per_oz': open_usd,
            'High_USD_per_oz': high_usd,
            'Low_USD_per_oz': low_usd,
            'Close_USD_per_oz': close_price_usd,
            'Open_PKR_per_oz': open_pkr_oz,
            'High_PKR_per_oz': high_pkr_oz,
            'Low_PKR_per_oz': low_pkr_oz,
            'Close_PKR_per_oz': close_pkr_oz,
            'Open_PKR_per_tola': open_pkr_oz * 0.375,
            'High_PKR_per_tola': high_pkr_oz * 0.375,
            'Low_PKR_per_tola': low_pkr_oz * 0.375,
            'Close_PKR_per_tola': close_pkr_oz * 0.375,
            'Volume': np.random.randint(5000, 50000, n_days)
        })

        # Ensure High >= Open,Close and Low <= Open,Close
        df['High_USD_per_oz'] = df[['Open_USD_per_oz', 'High_USD_per_oz', 'Close_USD_per_oz']].max(axis=1)
        df['Low_USD_per_oz'] = df[['Open_USD_per_oz', 'Low_USD_per_oz', 'Close_USD_per_oz']].min(axis=1)
        df['High_PKR_per_tola'] = df[['Open_PKR_per_tola', 'High_PKR_per_tola', 'Close_PKR_per_tola']].max(axis=1)
        df['Low_PKR_per_tola'] = df[['Open_PKR_per_tola', 'Low_PKR_per_tola', 'Close_PKR_per_tola']].min(axis=1)

        # Add per gram prices
        df['Close_PKR_per_gram'] = df['Close_PKR_per_tola'] / 11.664
        df['Close_USD_per_gram'] = df['Close_USD_per_oz'] / 31.1035

        # Save to file
        filepath = os.path.join(self.output_dir, 'gold_prices_usd_pkr_sample.csv')
        df.to_csv(filepath, index=False)

        print(f"✓ Generated {len(df)} records")
        print(f"✓ Date range: {df['Date'].min()} to {df['Date'].max()}")
        print(f"✓ Saved to: {filepath}")
        print(f"✓ USD price range: ${df['Close_USD_per_oz'].min():,.2f} - ${df['Close_USD_per_oz'].max():,.2f} per oz")
        print(f"✓ PKR price range: PKR {df['Close_PKR_per_tola'].min():,.2f} - {df['Close_PKR_per_tola'].max():,.2f} per tola")
        print(f"✓ Exchange rate range: {df['USD_PKR_Rate'].min():,.2f} - {df['USD_PKR_Rate'].max():,.2f}")

        return df

    def download_all(self, use_sample=False, years=5):
        """
        Main method to download gold price data

        Args:
            use_sample (bool): If True, generate synthetic data instead of downloading
            years (int): Number of years of historical data

        Returns:
            pd.DataFrame: Gold price data
        """
        print("\n" + "="*60)
        print("GOLD DATA DOWNLOADER - Stage 1")
        print("="*60)

        if use_sample:
            df = self.create_sample_data(years=years)
        else:
            df = self.download_yahoo_finance(years=years)

            # Fallback to sample data if download fails
            if df is None:
                print("\n⚠ Real data download failed. Generating sample data...")
                df = self.create_sample_data(years=years)

        print("\n" + "="*60)
        print("DOWNLOAD COMPLETE")
        print("="*60)

        return df


def load_raw_data(filename='gold_prices_yahoo.csv'):
    """
    Load raw gold price data from file

    Args:
        filename (str): Name of the CSV file in data/raw/

    Returns:
        pd.DataFrame: Raw gold price data
    """
    filepath = os.path.join('data/raw', filename)

    if not os.path.exists(filepath):
        print(f"✗ File not found: {filepath}")
        print("Run data download first!")
        return None

    df = pd.read_csv(filepath)
    df['Date'] = pd.to_datetime(df['Date'])

    print(f"✓ Loaded {len(df)} records from {filepath}")
    return df


if __name__ == "__main__":
    # Example usage
    downloader = GoldDataDownloader()

    # Try to download real data, fallback to sample if needed
    try:
        df = downloader.download_all(use_sample=False, years=5)
    except Exception as e:
        print(f"\n⚠ Error: {e}")
        print("Generating sample data instead...")
        df = downloader.download_all(use_sample=True, years=5)

    if df is not None:
        print("\n✓ Data collection Stage 1 complete!")
        print(f"✓ Next step: Run preprocessing.py")

