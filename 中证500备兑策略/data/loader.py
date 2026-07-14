import pandas as pd

'''
load underlying data and option data
'''
FILE_PATH_UNDERLYING = "500ETF/510500_underlying.csv"
FILE_PATH_OPTION = "500ETF/510500_option_prices.csv"

def load_underlying_data(FILE_PATH_UNDERLYING):
    df = pd.read_csv(FILE_PATH_UNDERLYING)
    return df

def load_option_data(FILE_PATH_OPTION):
    df = pd.read_csv(FILE_PATH_OPTION)
    return df

if __name__ == "__main__":
    df_underlying = load_underlying_data(FILE_PATH_UNDERLYING)
    df_option = load_option_data(FILE_PATH_OPTION)
    print(df_underlying.shape)
    print(df_option.shape)