"""
Data Preprocessing Module
Handles data cleaning, missing value imputation, and outlier detection
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns


class GoldDataPreprocessor:
    """Preprocess and clean gold price data"""

    def __init__(self, input_dir='data/raw', output_dir='data/processed'):
        self.input_dir = input_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.cleaning_report = []

    def load_data(self, filename='gold_prices_usd_pkr.csv'):
        """Load raw data from file (USD + PKR)"""
        filepath = os.path.join(self.input_dir, filename)

        if not os.path.exists(filepath):
            # Try alternative filenames
            for alt_name in ['gold_prices_usd_pkr_sample.csv', 'gold_prices_yahoo.csv', 'gold_prices_sample.csv']:
                alt_path = os.path.join(self.input_dir, alt_name)
                if os.path.exists(alt_path):
                    filepath = alt_path
                    break

        print(f"\n{'='*60}")
        print(f"Loading data from: {filepath}")
        print(f"{'='*60}")

        df = pd.read_csv(filepath)
        df['Date'] = pd.to_datetime(df['Date'])

        print(f"✓ Loaded {len(df)} records")
        print(f"✓ Date range: {df['Date'].min()} to {df['Date'].max()}")
        print(f"✓ Columns: {list(df.columns)}")

        # Check if USD data exists
        has_usd = 'Close_USD_per_oz' in df.columns or 'Close_USD_per_gram' in df.columns
        has_pkr = 'Close_PKR_per_tola' in df.columns
        has_rate = 'USD_PKR_Rate' in df.columns

        print(f"✓ USD data present: {has_usd}")
        print(f"✓ PKR data present: {has_pkr}")
        print(f"✓ Exchange rate present: {has_rate}")

        return df

    def check_missing_values(self, df):
        """Check for missing values and gaps in dates"""
        print(f"\n{'='*60}")
        print("MISSING VALUE ANALYSIS")
        print(f"{'='*60}")

        # Check for NaN values
        missing = df.isnull().sum()
        if missing.sum() > 0:
            print("\n⚠ Missing values found:")
            for col, count in missing[missing > 0].items():
                pct = (count / len(df)) * 100
                print(f"  - {col}: {count} ({pct:.2f}%)")
                self.cleaning_report.append(f"Missing values in {col}: {count} ({pct:.2f}%)")
        else:
            print("✓ No missing values in data")

        # Check for date gaps (weekends/holidays)
        df_sorted = df.sort_values('Date').reset_index(drop=True)
        date_diffs = df_sorted['Date'].diff()

        # Find gaps > 3 days (normal weekend is 2 days)
        large_gaps = date_diffs[date_diffs > pd.Timedelta(days=3)]

        if len(large_gaps) > 0:
            print(f"\n⚠ Found {len(large_gaps)} date gaps > 3 days:")
            for idx in large_gaps.head(10).index:
                prev_date = df_sorted.loc[idx-1, 'Date']
                curr_date = df_sorted.loc[idx, 'Date']
                gap_days = (curr_date - prev_date).days
                print(f"  - Gap of {gap_days} days: {prev_date.date()} to {curr_date.date()}")
            if len(large_gaps) > 10:
                print(f"  ... and {len(large_gaps) - 10} more gaps")
            self.cleaning_report.append(f"Found {len(large_gaps)} date gaps > 3 days")
        else:
            print("✓ No significant date gaps found")

        return df_sorted

    def detect_outliers(self, df, columns=None, method='iqr', threshold=3):
        """
        Detect outliers in price data (supports multiple columns)

        Args:
            df: DataFrame
            columns: List of columns to check (or single column name)
            method: 'iqr' or 'zscore'
            threshold: Number of standard deviations (for zscore) or IQR multiplier
        """
        if columns is None:
            columns = ['Close_PKR_per_tola']
            if 'Close_USD_per_oz' in df.columns:
                columns.append('Close_USD_per_oz')
        elif isinstance(columns, str):
            columns = [columns]

        all_outlier_indices = []

        for column in columns:
            print(f"\n{'='*60}")
            print(f"OUTLIER DETECTION - {column}")
            print(f"{'='*60}")

            if column not in df.columns:
                print(f"⚠ Column {column} not found. Skipping.")
                continue

            outlier_indices = []

            if method == 'zscore':
                # Z-score method
                z_scores = np.abs((df[column] - df[column].mean()) / df[column].std())
                outlier_indices = df[z_scores > threshold].index.tolist()
                print(f"Method: Z-score (threshold={threshold})")

            elif method == 'iqr':
                # IQR method
                Q1 = df[column].quantile(0.25)
                Q3 = df[column].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - threshold * IQR
                upper_bound = Q3 + threshold * IQR
                outlier_indices = df[(df[column] < lower_bound) | (df[column] > upper_bound)].index.tolist()
                print(f"Method: IQR (multiplier={threshold})")
                print(f"  - Q1: {Q1:,.2f}")
                print(f"  - Q3: {Q3:,.2f}")
                print(f"  - IQR: {IQR:,.2f}")
                print(f"  - Bounds: [{lower_bound:,.2f}, {upper_bound:,.2f}]")

            if len(outlier_indices) > 0:
                print(f"\n⚠ Found {len(outlier_indices)} potential outliers ({len(outlier_indices)/len(df)*100:.2f}%)")
                for idx in outlier_indices[:5]:
                    print(f"  - Date: {df.loc[idx, 'Date'].date()}, {column}: {df.loc[idx, column]:,.2f}")
                if len(outlier_indices) > 5:
                    print(f"  ... and {len(outlier_indices) - 5} more")
                self.cleaning_report.append(f"Found {len(outlier_indices)} outliers in {column} using {method} method")
                all_outlier_indices.extend(outlier_indices)
            else:
                print("✓ No significant outliers detected")

        # Return unique outlier indices
        all_outlier_indices = list(set(all_outlier_indices))
        return df, all_outlier_indices

    def handle_missing_values(self, df, method='ffill'):
        """
        Handle missing values in the dataset

        Args:
            df: DataFrame
            method: 'ffill' (forward fill), 'bfill' (backward fill), 'interpolate', or 'drop'
        """
        print(f"\n{'='*60}")
        print(f"HANDLING MISSING VALUES - Method: {method}")
        print(f"{'='*60}")

        initial_count = len(df)
        initial_missing = df.isnull().sum().sum()

        if initial_missing == 0:
            print("✓ No missing values to handle")
            return df

        if method == 'drop':
            df = df.dropna()
            print(f"✓ Dropped {initial_count - len(df)} rows with missing values")

        elif method == 'ffill':
            df = df.fillna(method='ffill')
            print(f"✓ Forward filled missing values")
            self.cleaning_report.append(f"Forward filled {initial_missing} missing values")

        elif method == 'bfill':
            df = df.fillna(method='bfill')
            print(f"✓ Backward filled missing values")
            self.cleaning_report.append(f"Backward filled {initial_missing} missing values")

        elif method == 'interpolate':
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            df[numeric_cols] = df[numeric_cols].interpolate(method='linear')
            print(f"✓ Interpolated missing values")
            self.cleaning_report.append(f"Interpolated {initial_missing} missing values")

        # Check if any missing values remain
        remaining_missing = df.isnull().sum().sum()
        if remaining_missing > 0:
            print(f"⚠ {remaining_missing} missing values remain after {method}")
            # Drop remaining missing values
            df = df.dropna()
            print(f"✓ Dropped {remaining_missing} remaining rows with missing values")
        else:
            print(f"✓ All missing values handled successfully")

        return df

    def handle_outliers(self, df, outlier_indices, method='cap'):
        """
        Handle outliers in the dataset

        Args:
            df: DataFrame
            outlier_indices: List of indices with outliers
            method: 'cap' (winsorize), 'remove', or 'keep'
        """
        if len(outlier_indices) == 0:
            print("✓ No outliers to handle")
            return df

        print(f"\n{'='*60}")
        print(f"HANDLING OUTLIERS - Method: {method}")
        print(f"{'='*60}")

        if method == 'remove':
            df = df.drop(outlier_indices)
            df = df.reset_index(drop=True)
            print(f"✓ Removed {len(outlier_indices)} outlier records")
            self.cleaning_report.append(f"Removed {len(outlier_indices)} outliers")

        elif method == 'cap':
            # Cap outliers at 1st and 99th percentile
            numeric_cols = ['Open_PKR_per_tola', 'High_PKR_per_tola', 'Low_PKR_per_tola', 'Close_PKR_per_tola']
            for col in numeric_cols:
                if col in df.columns:
                    p1 = df[col].quantile(0.01)
                    p99 = df[col].quantile(0.99)
                    df[col] = df[col].clip(lower=p1, upper=p99)
            print(f"✓ Capped outliers at 1st and 99th percentiles")
            self.cleaning_report.append(f"Capped outliers at percentile bounds")

        elif method == 'keep':
            print("✓ Keeping outliers (no action taken)")
            self.cleaning_report.append("Outliers kept in dataset")

        return df

    def add_daily_returns(self, df):
        """Calculate daily returns and percentage changes for USD and PKR"""
        print(f"\n{'='*60}")
        print("CALCULATING DAILY RETURNS")
        print(f"{'='*60}")

        # PKR daily returns
        if 'Close_PKR_per_tola' in df.columns:
            df['Daily_Return_PKR'] = df['Close_PKR_per_tola'].pct_change() * 100
            df['Price_Change_PKR'] = df['Close_PKR_per_tola'].diff()
            print("✓ Added Daily_Return_PKR (%) and Price_Change_PKR columns")

        # USD daily returns
        if 'Close_USD_per_oz' in df.columns:
            df['Daily_Return_USD'] = df['Close_USD_per_oz'].pct_change() * 100
            df['Price_Change_USD'] = df['Close_USD_per_oz'].diff()
            print("✓ Added Daily_Return_USD (%) and Price_Change_USD columns")

        # Exchange rate changes
        if 'USD_PKR_Rate' in df.columns:
            df['Exchange_Rate_Change'] = df['USD_PKR_Rate'].pct_change() * 100
            print("✓ Added Exchange_Rate_Change (%) column")

        # Backward compatibility
        if 'Daily_Return_PKR' in df.columns:
            df['Daily_Return'] = df['Daily_Return_PKR']
            df['Price_Change'] = df['Price_Change_PKR']

        return df

    def validate_data(self, df):
        """Perform final data validation checks"""
        print(f"\n{'='*60}")
        print("DATA VALIDATION")
        print(f"{'='*60}")

        issues = []

        # Check for negative prices
        price_cols = [col for col in df.columns if 'PKR' in col or 'USD' in col]
        for col in price_cols:
            if col in df.columns:
                neg_count = (df[col] < 0).sum()
                if neg_count > 0:
                    issues.append(f"Negative values in {col}: {neg_count}")

        # Check for duplicate dates
        dup_dates = df['Date'].duplicated().sum()
        if dup_dates > 0:
            issues.append(f"Duplicate dates: {dup_dates}")

        # Check data types
        if df['Date'].dtype != 'datetime64[ns]':
            issues.append("Date column is not datetime type")

        # Check for chronological order
        if not df['Date'].is_monotonic_increasing:
            issues.append("Dates are not in chronological order")

        if len(issues) > 0:
            print("⚠ Validation issues found:")
            for issue in issues:
                print(f"  - {issue}")
            return False
        else:
            print("✓ All validation checks passed")
            return True

    def generate_summary_stats(self, df):
        """Generate summary statistics for the cleaned data"""
        print(f"\n{'='*60}")
        print("SUMMARY STATISTICS")
        print(f"{'='*60}")

        print(f"\nDataset Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        print(f"Date Range: {df['Date'].min().date()} to {df['Date'].max().date()}")
        print(f"Duration: {(df['Date'].max() - df['Date'].min()).days} days")

        if 'Close_PKR_per_tola' in df.columns:
            print(f"\nPrice Statistics (PKR per tola):")
            print(f"  - Mean: {df['Close_PKR_per_tola'].mean():,.2f}")
            print(f"  - Median: {df['Close_PKR_per_tola'].median():,.2f}")
            print(f"  - Std Dev: {df['Close_PKR_per_tola'].std():,.2f}")
            print(f"  - Min: {df['Close_PKR_per_tola'].min():,.2f}")
            print(f"  - Max: {df['Close_PKR_per_tola'].max():,.2f}")

        if 'Daily_Return' in df.columns:
            print(f"\nDaily Returns (%):")
            print(f"  - Mean: {df['Daily_Return'].mean():.4f}")
            print(f"  - Std Dev: {df['Daily_Return'].std():.4f}")
            print(f"  - Min: {df['Daily_Return'].min():.4f}")
            print(f"  - Max: {df['Daily_Return'].max():.4f}")

    def save_cleaned_data(self, df, filename='merged_clean.csv'):
        """Save cleaned data to file"""
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False)
        print(f"\n✓ Saved cleaned data to: {filepath}")

        # Also save with old filename for backward compatibility
        if filename == 'merged_clean.csv':
            compat_path = os.path.join(self.output_dir, 'gold_prices_clean.csv')
            df.to_csv(compat_path, index=False)
            print(f"✓ Also saved as: {compat_path} (backward compatibility)")

        # Save cleaning report
        report_path = os.path.join(self.output_dir, 'cleaning_report.txt')
        with open(report_path, 'w') as f:
            f.write("GOLD PRICE DATA - CLEANING REPORT\n")
            f.write("="*60 + "\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Final dataset shape: {df.shape}\n")
            f.write(f"Date range: {df['Date'].min()} to {df['Date'].max()}\n\n")
            f.write("Cleaning steps performed:\n")
            for i, step in enumerate(self.cleaning_report, 1):
                f.write(f"{i}. {step}\n")

        print(f"✓ Saved cleaning report to: {report_path}")

        return filepath

    def preprocess_pipeline(self, filename='gold_prices_usd_pkr.csv',
                           missing_method='ffill',
                           outlier_method='keep'):
        """
        Complete preprocessing pipeline for USD + PKR data

        Args:
            filename: Input CSV filename
            missing_method: Method to handle missing values ('ffill', 'bfill', 'interpolate', 'drop')
            outlier_method: Method to handle outliers ('cap', 'remove', 'keep')
        """
        print("\n" + "="*60)
        print("GOLD DATA PREPROCESSING (USD + PKR) - Stage 2")
        print("="*60)

        # Load data
        df = self.load_data(filename)

        # Check missing values and date gaps
        df = self.check_missing_values(df)

        # Detect outliers in both USD and PKR prices
        outlier_cols = []
        if 'Close_PKR_per_tola' in df.columns:
            outlier_cols.append('Close_PKR_per_tola')
        if 'Close_USD_per_oz' in df.columns:
            outlier_cols.append('Close_USD_per_oz')

        df, outlier_indices = self.detect_outliers(df, columns=outlier_cols, method='iqr')

        # Handle missing values
        df = self.handle_missing_values(df, method=missing_method)

        # Handle outliers
        df = self.handle_outliers(df, outlier_indices, method=outlier_method)

        # Add daily returns
        df = self.add_daily_returns(df)

        # Sort by date
        df = df.sort_values('Date').reset_index(drop=True)

        # Validate data
        self.validate_data(df)

        # Generate summary statistics
        self.generate_summary_stats(df)

        # Save cleaned data
        output_path = self.save_cleaned_data(df)

        print("\n" + "="*60)
        print("PREPROCESSING COMPLETE")
        print("="*60)
        print(f"✓ Cleaned dataset ready at: {output_path}")

        return df


if __name__ == "__main__":
    # Run preprocessing pipeline
    preprocessor = GoldDataPreprocessor()

    try:
        df_clean = preprocessor.preprocess_pipeline(
            filename='gold_prices_yahoo.csv',
            missing_method='ffill',
            outlier_method='keep'
        )
        print("\n✓ Preprocessing Stage 2 complete!")
        print("✓ Next step: Run features.py for feature engineering")
    except Exception as e:
        print(f"\n✗ Error during preprocessing: {e}")
        print("Trying with sample data...")
        df_clean = preprocessor.preprocess_pipeline(
            filename='gold_prices_sample.csv',
            missing_method='ffill',
            outlier_method='keep'
        )

